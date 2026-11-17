"""
auth.py - Autenticação (login) do sistema: hash de senha, rate limiting e
gestão de usuários no PostgreSQL.

Perfis de acesso: "adm" e "user" (coluna usuario.tipouser).
"""

import os
from datetime import datetime

import bcrypt
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
PSYCOPG_URL = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://") \
                          .replace("postgres+psycopg://", "postgresql://")

LIMITE_TENTATIVAS = 5
JANELA_MINUTOS = 15
BLOQUEIO_MINUTOS = 15

ADMIN_NOME = "Administrador"
ADMIN_EMAIL = "admin@gmail.com"
ADMIN_SENHA = "admin78"

# Hash fixo só para gastar o mesmo tempo de bcrypt quando o e-mail não existe —
# sem isso, a resposta de "e-mail inexistente" é mais rápida que a de "senha errada"
# e isso vaza quais e-mails estão cadastrados mesmo com mensagem de erro idêntica.
_HASH_FALSO = bcrypt.hashpw(b"hash-falso-tempo-constante", bcrypt.gensalt()).decode("utf-8")


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha_tempo_constante(senha: str, hash_armazenado: str | None) -> bool:
    return bcrypt.checkpw(senha.encode("utf-8"), (hash_armazenado or _HASH_FALSO).encode("utf-8"))


# ── Setup de tabelas ─────────────────────────────────────────────────────────

def criar_tabelas_auth():
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS usuario (
                    iduser    SERIAL PRIMARY KEY,
                    nome      VARCHAR(100) NOT NULL,
                    email     VARCHAR(100) UNIQUE NOT NULL,
                    senha     VARCHAR(200) NOT NULL,
                    tipouser  VARCHAR(20) NOT NULL CHECK (tipouser IN ('adm', 'user'))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS login_tentativa (
                    email            VARCHAR(100) PRIMARY KEY,
                    tentativas       INTEGER NOT NULL DEFAULT 0,
                    ultima_tentativa TIMESTAMP NOT NULL DEFAULT NOW(),
                    bloqueado_ate    TIMESTAMP
                )
            """)
        conn.commit()


def seed_admin():
    """Cria o usuário administrador padrão, se ainda não existir."""
    senha_hash = hash_senha(ADMIN_SENHA)
    sql = """
        INSERT INTO usuario (nome, email, senha, tipouser)
        SELECT %s, %s, %s, 'adm'
        WHERE NOT EXISTS (SELECT 1 FROM usuario WHERE email = %s)
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (ADMIN_NOME, ADMIN_EMAIL, senha_hash, ADMIN_EMAIL))
        conn.commit()


# ── Usuários ──────────────────────────────────────────────────────────────────

def buscar_usuario_por_email(email: str) -> dict | None:
    sql = "SELECT iduser, nome, email, senha, tipouser FROM usuario WHERE email = %s"
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
    if not row:
        return None
    return {"iduser": row[0], "nome": row[1], "email": row[2], "senha": row[3], "tipouser": row[4]}


def criar_usuario(nome: str, email: str, senha: str, tipouser: str = "user") -> int:
    senha_hash = hash_senha(senha)
    sql = """
        INSERT INTO usuario (nome, email, senha, tipouser)
        VALUES (%s, %s, %s, %s)
        RETURNING iduser
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (nome, email, senha_hash, tipouser))
            iduser = cur.fetchone()[0]
        conn.commit()
    return iduser


def listar_usuarios() -> list[dict]:
    sql = "SELECT iduser, nome, email, tipouser FROM usuario ORDER BY nome"
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [{"iduser": r[0], "nome": r[1], "email": r[2], "tipouser": r[3]} for r in rows]


def deletar_usuario(iduser: int) -> int:
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM usuario WHERE iduser = %s", (iduser,))
            n = cur.rowcount
        conn.commit()
    return n


# ── Rate limiting / bloqueio por e-mail ──────────────────────────────────────

def tempo_restante_bloqueio(email: str) -> int | None:
    """Retorna minutos restantes de bloqueio, ou None se não está bloqueado."""
    sql = """
        SELECT bloqueado_ate FROM login_tentativa
        WHERE email = %s AND bloqueado_ate > NOW()
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
            row = cur.fetchone()
    if not row:
        return None
    # bloqueado_ate vem do NOW() do Postgres (UTC) — compara contra UTC, não hora local.
    restante = row[0] - datetime.utcnow()
    minutos = int(restante.total_seconds() // 60) + 1
    return max(minutos, 1)


def registrar_login_falho(email: str):
    """UPSERT atômico: incrementa tentativas (ou reinicia se a janela expirou) e bloqueia se atingir o limite."""
    sql = f"""
        INSERT INTO login_tentativa (email, tentativas, ultima_tentativa, bloqueado_ate)
        VALUES (%s, 1, NOW(), NULL)
        ON CONFLICT (email) DO UPDATE SET
            tentativas = CASE
                WHEN login_tentativa.ultima_tentativa < NOW() - INTERVAL '{JANELA_MINUTOS} minutes'
                    THEN 1
                ELSE login_tentativa.tentativas + 1
            END,
            ultima_tentativa = NOW(),
            bloqueado_ate = CASE
                WHEN (CASE
                        WHEN login_tentativa.ultima_tentativa < NOW() - INTERVAL '{JANELA_MINUTOS} minutes'
                            THEN 1
                        ELSE login_tentativa.tentativas + 1
                      END) >= {LIMITE_TENTATIVAS}
                    THEN NOW() + INTERVAL '{BLOQUEIO_MINUTOS} minutes'
                ELSE login_tentativa.bloqueado_ate
            END
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (email,))
        conn.commit()


def registrar_login_sucesso(email: str):
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM login_tentativa WHERE email = %s", (email,))
        conn.commit()
