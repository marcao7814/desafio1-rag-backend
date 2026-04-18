"""
db.py — Camada de acesso ao banco de dados (sem dependências Streamlit).
Todas as funções levantam exceções em caso de erro em vez de chamar st.error().
"""

import json
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
COLLECTION   = os.getenv("COLLECTION_NAME", "documentos_rag")

PSYCOPG_URL = (
    DATABASE_URL
    .replace("postgresql+psycopg://", "postgresql://")
    .replace("postgres+psycopg://", "postgresql://")
)


# ── Inicialização ─────────────────────────────────────────────────────────────

def criar_tabela_cache():
    """Cria/migra as tabelas de cache e aprovação manual."""
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    id            SERIAL PRIMARY KEY,
                    pergunta      TEXT NOT NULL,
                    resposta      TEXT NOT NULL,
                    chunks        JSONB,
                    data_consulta TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("ALTER TABLE search_cache ADD COLUMN IF NOT EXISTS chunks JSONB")
            cur.execute("ALTER TABLE search_cache ADD COLUMN IF NOT EXISTS tipo VARCHAR DEFAULT 'rag'")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS verification_cache (
                    id               SERIAL PRIMARY KEY,
                    arquivo          TEXT NOT NULL,
                    modo             VARCHAR(10) NOT NULL,
                    criterio         TEXT NOT NULL,
                    ocorrencias      JSONB NOT NULL,
                    status           VARCHAR(30) NOT NULL,
                    data_verificacao TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("ALTER TABLE verification_cache ALTER COLUMN status TYPE VARCHAR(30)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS aprovacao_manual (
                    id              SERIAL PRIMARY KEY,
                    verification_id INTEGER NOT NULL REFERENCES verification_cache(id) ON DELETE CASCADE,
                    chunk_indice    INTEGER NOT NULL,
                    observacao      TEXT,
                    tipo            VARCHAR(30) DEFAULT 'aprovado',
                    data_aprovacao  TIMESTAMP DEFAULT NOW(),
                    UNIQUE (verification_id, chunk_indice)
                )
            """)
            cur.execute("ALTER TABLE aprovacao_manual ADD COLUMN IF NOT EXISTS tipo VARCHAR(30) DEFAULT 'aprovado'")
        conn.commit()


# ── PDFs ─────────────────────────────────────────────────────────────────────

def listar_pdfs_no_banco() -> list[dict]:
    """Retorna lista de dicts {source, nome, chunks} dos PDFs gravados."""
    sql = """
        SELECT
            cmetadata->>'source'        AS source,
            cmetadata->>'original_name' AS nome,
            COUNT(*)                     AS chunks
        FROM langchain_pg_embedding
        WHERE collection_id = (
            SELECT uuid FROM langchain_pg_collection WHERE name = %s
        )
        GROUP BY source, nome
        ORDER BY source
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (COLLECTION,))
            rows = cur.fetchall()
    return [
        {
            "source": r[0],
            "nome":   r[1] or os.path.basename(r[0] or ""),
            "chunks": r[2],
        }
        for r in rows if r[0]
    ]


def deletar_pdf_do_banco(source: str) -> int:
    """Remove todos os chunks do PDF indicado. Retorna qtd removida."""
    sql = """
        DELETE FROM langchain_pg_embedding
        WHERE collection_id = (SELECT uuid FROM langchain_pg_collection WHERE name = %s)
          AND cmetadata->>'source' = %s
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (COLLECTION, source))
            deletados = cur.rowcount
        conn.commit()
    return deletados


def deletar_todos_pdfs() -> int:
    """Remove todos os chunks da coleção. Retorna qtd removida."""
    sql = """
        DELETE FROM langchain_pg_embedding
        WHERE collection_id = (SELECT uuid FROM langchain_pg_collection WHERE name = %s)
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (COLLECTION,))
            deletados = cur.rowcount
        conn.commit()
    return deletados


# ── Cache de perguntas ────────────────────────────────────────────────────────

def buscar_cache(pergunta: str, tipo: str = "rag") -> dict | None:
    """Busca pergunta no cache por tipo. Retorna dict ou None."""
    sql = """
        SELECT id, resposta, chunks, data_consulta
        FROM search_cache
        WHERE LOWER(TRIM(pergunta)) = LOWER(TRIM(%s)) AND tipo = %s
        ORDER BY data_consulta DESC
        LIMIT 1
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (pergunta, tipo))
            row = cur.fetchone()
    if row:
        return {
            "id":            row[0],
            "resposta":      row[1],
            "chunks":        row[2] or [],
            "data_consulta": row[3],
        }
    return None


def salvar_cache(
    pergunta: str,
    resposta: str,
    resultados: list = None,
    tipo: str = "rag",
) -> int:
    """Insere nova entrada no cache. Retorna o id gerado."""
    chunks_json = None
    if resultados and tipo == "rag":
        # resultados é list[(Document, float)]
        chunks_json = json.dumps([
            {
                "content":  doc.page_content,
                "score":    float(score),
                "metadata": doc.metadata,
            }
            for doc, score in resultados
        ], ensure_ascii=False)
    elif resultados and tipo == "web":
        # resultados é list[{"title", "url"}]
        chunks_json = json.dumps(resultados, ensure_ascii=False)

    sql = """
        INSERT INTO search_cache (pergunta, resposta, chunks, tipo)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (pergunta, resposta, chunks_json, tipo))
            novo_id = cur.fetchone()[0]
        conn.commit()
    return novo_id


def listar_cache() -> list[dict]:
    """Retorna todos os registros do cache mais recentes primeiro."""
    sql = """
        SELECT id, pergunta, resposta, chunks, data_consulta, tipo
        FROM search_cache
        ORDER BY data_consulta DESC
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [
        {
            "id":            r[0],
            "pergunta":      r[1],
            "resposta":      r[2],
            "chunks":        r[3] or [],
            "data_consulta": r[4].strftime("%d/%m/%Y %H:%M") if r[4] else "",
            "tipo":          r[5] or "rag",
        }
        for r in rows
    ]


def deletar_cache_por_id(registro_id: int) -> int:
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM search_cache WHERE id = %s", (registro_id,))
            n = cur.rowcount
        conn.commit()
    return n


# ── Cache de verificações ─────────────────────────────────────────────────────

def salvar_verificacao_cache(
    arquivo: str, modo: str, criterio: str, ocorrencias: list
) -> int:
    """Salva verificação no cache. Retorna id gerado."""
    status = "aprovado" if not ocorrencias else "reprovado"
    sql = """
        INSERT INTO verification_cache (arquivo, modo, criterio, ocorrencias, status)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (arquivo, modo, criterio, json.dumps(ocorrencias, ensure_ascii=False), status),
            )
            novo_id = cur.fetchone()[0]
        conn.commit()
    return novo_id


def listar_verificacao_cache() -> list[dict]:
    sql = """
        SELECT id, arquivo, modo, criterio, ocorrencias, status, data_verificacao
        FROM verification_cache
        ORDER BY data_verificacao DESC
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [
        {
            "id":               r[0],
            "arquivo":          r[1],
            "modo":             r[2],
            "criterio":         r[3],
            "ocorrencias":      r[4] or [],
            "status":           r[5],
            "data_verificacao": r[6].strftime("%d/%m/%Y %H:%M") if r[6] else "",
        }
        for r in rows
    ]


def deletar_verificacao_cache_por_id(registro_id: int) -> int:
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM verification_cache WHERE id = %s", (registro_id,))
            n = cur.rowcount
        conn.commit()
    return n


# ── Aprovação manual ──────────────────────────────────────────────────────────

def listar_aprovacoes_manuais(verification_id: int) -> dict[int, str]:
    """Retorna {chunk_indice: tipo} das revisões manuais."""
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_indice, COALESCE(tipo,'aprovado') FROM aprovacao_manual WHERE verification_id = %s",
                (verification_id,),
            )
            rows = cur.fetchall()
    return {r[0]: r[1] for r in rows}


def aprovar_chunk_manual(
    verification_id: int,
    chunk_indice: int,
    observacao: str = "",
    tipo: str = "aprovado",
):
    """Registra revisão manual de um chunk."""
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO aprovacao_manual (verification_id, chunk_indice, observacao, tipo)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (verification_id, chunk_indice) DO UPDATE
                    SET observacao = EXCLUDED.observacao,
                        tipo = EXCLUDED.tipo,
                        data_aprovacao = NOW()
            """, (verification_id, chunk_indice, observacao, tipo))
        conn.commit()
    _atualizar_status_verificacao(verification_id)


def aprovar_por_mesmo_motivo(
    verification_id: int,
    chunk_indice: int,
    observacao: str,
    ocorrencias: list,
    tipo: str = "aprovado",
) -> int:
    """Aprova o chunk e todos com o mesmo motivo de reprovação. Retorna qtd."""
    def _chave(oc: dict):
        palavras = oc.get("palavras")
        if palavras:
            return ("exata", frozenset(p.lower() for p in palavras))
        motivo = (oc.get("motivo") or "").strip().lower()
        return ("llm", motivo) if motivo else None

    chave_ref = _chave(ocorrencias[chunk_indice])
    indices = [
        i for i, oc in enumerate(ocorrencias)
        if chave_ref is not None and _chave(oc) == chave_ref
    ]
    if chunk_indice not in indices:
        indices.append(chunk_indice)

    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            for idx in indices:
                cur.execute("""
                    INSERT INTO aprovacao_manual (verification_id, chunk_indice, observacao, tipo)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (verification_id, chunk_indice) DO UPDATE
                        SET observacao = EXCLUDED.observacao,
                            tipo = EXCLUDED.tipo,
                            data_aprovacao = NOW()
                """, (verification_id, idx, observacao, tipo))
        conn.commit()
    _atualizar_status_verificacao(verification_id)
    return len(indices)


def remover_aprovacao_manual(verification_id: int, chunk_indice: int):
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM aprovacao_manual WHERE verification_id = %s AND chunk_indice = %s",
                (verification_id, chunk_indice),
            )
        conn.commit()
    _atualizar_status_verificacao(verification_id)


def _atualizar_status_verificacao(verification_id: int):
    """Recalcula e grava o status da verificação."""
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ocorrencias FROM verification_cache WHERE id = %s",
                (verification_id,),
            )
            row = cur.fetchone()
            if not row:
                return
            n_ocs = len(row[0] or [])

            cur.execute(
                "SELECT COALESCE(tipo,'aprovado'), COUNT(*) FROM aprovacao_manual WHERE verification_id = %s GROUP BY tipo",
                (verification_id,),
            )
            contagens     = {r[0]: r[1] for r in cur.fetchall()}
            n_aprovados   = contagens.get("aprovado", 0)
            n_confirmados = contagens.get("reprovado_confirmado", 0)
            n_revisados   = n_aprovados + n_confirmados

            if n_ocs == 0:
                novo_status = "aprovado"
            elif n_aprovados >= n_ocs:
                novo_status = "aprovado manualmente"
            elif n_revisados >= n_ocs:
                novo_status = "reprovado confirmado"
            else:
                novo_status = "reprovado"

            cur.execute(
                "UPDATE verification_cache SET status = %s WHERE id = %s",
                (novo_status, verification_id),
            )
        conn.commit()
