# Guia Prático — Reescrever este login em outro projeto

Checklist + código de referência. Pressupõe um projeto novo em Python/Flask; se o
projeto novo for em outra stack, use isto como especificação funcional e adapte os
snippets (a lógica e a ordem das etapas continuam valendo).

## 0. Dependências

```
flask
flask-wtf
psycopg2-binary      # ou outro driver, se não for Postgres
bcrypt
python-dotenv
```

## 1. Variáveis de ambiente (`.env`, nunca commitado)

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=
DB_USER=
DB_PASSWORD=
SECRET_KEY=            # gerar com: python -c "import secrets; print(secrets.token_hex(32))"
SESSION_COOKIE_SECURE=0   # 0 em dev local (HTTP), 1 em produção (HTTPS)
```

## 2. Banco de dados

Rode o DDL de `02-banco-de-dados.md` (tabelas `usuario` + `login_tentativa` no mínimo).
Ajuste os valores do `CHECK (tipouser IN (...))` para os perfis do novo projeto.

## 3. Estrutura de arquivos sugerida (mesma separação do projeto original)

```
app/
├── auth/
│   └── seguranca.py        # hash_senha, verificar_senha_tempo_constante
├── banco/
│   ├── conexao.py          # get_conexao()
│   ├── usuarios.py         # buscar_usuario_por_email, criar_usuario, ...
│   └── login_tentativas.py # tempo_restante_bloqueio, registrar_login_falho/sucesso
├── templates/
│   └── login.html
└── web.py                  # rotas /login, /logout + decoradores
```

## 4. `app/banco/conexao.py`

```python
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()


def get_conexao():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        cursor_factory=RealDictCursor,
    )
```

## 5. `app/auth/seguranca.py`

```python
import bcrypt

# Hash fixo só para gastar o mesmo tempo de bcrypt quando o e-mail não existe —
# sem isso, a resposta de "e-mail inexistente" é mais rápida que a de "senha errada"
# e isso vaza quais e-mails estão cadastrados mesmo com mensagem de erro idêntica.
_HASH_FALSO = bcrypt.hashpw(b"hash-falso-tempo-constante", bcrypt.gensalt()).decode("utf-8")


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_senha_tempo_constante(senha: str, hash_armazenado: str | None) -> bool:
    return bcrypt.checkpw(senha.encode("utf-8"), (hash_armazenado or _HASH_FALSO).encode("utf-8"))
```

## 6. `app/banco/usuarios.py` (mínimo)

```python
from app.banco.conexao import get_conexao


def buscar_usuario_por_email(email: str):
    with get_conexao() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM usuario WHERE email = %s", (email,))
            return cur.fetchone()


def criar_usuario(nome, email, senha_hash, tipouser, telefone=None):
    with get_conexao() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usuario (nome, email, senha, tipouser, telefone)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING iduser
                """,
                (nome, email, senha_hash, tipouser, telefone),
            )
            iduser = cur.fetchone()["iduser"]
            conn.commit()
            return iduser
```

## 7. `app/banco/login_tentativas.py`

Copie o arquivo original tal como está (`app/banco/login_tentativas.py` neste
repositório) — a lógica de UPSERT atômico é o ponto mais fácil de introduzir uma
condição de corrida se reescrita manualmente. Ajuste só `LIMITE_TENTATIVAS`,
`JANELA_MINUTOS` e `BLOQUEIO_MINUTOS` se o novo projeto exigir outros valores.

## 8. Rotas em `app/web.py`

```python
from flask import Flask, render_template, request, session, redirect, url_for
from flask_wtf import CSRFProtect
from app.auth.seguranca import verificar_senha_tempo_constante
from app.banco.login_tentativas import tempo_restante_bloqueio, registrar_login_falho, registrar_login_sucesso
from app.banco.usuarios import buscar_usuario_por_email

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
app.config["WTF_CSRF_TIME_LIMIT"] = None
csrf = CSRFProtect(app)


@app.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    if os.getenv("SESSION_COOKIE_SECURE", "0") == "1":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def login_required(f):
    @wraps(f)
    def inner(*a, **kw):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return inner


def role_required(role):
    def dec(f):
        @wraps(f)
        def inner(*a, **kw):
            if session.get("usuario", {}).get("tipouser") != role:
                return redirect(url_for("index"))
            return f(*a, **kw)
        return inner
    return dec


@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        senha = request.form.get("senha", "")

        minutos = tempo_restante_bloqueio(email)
        if minutos:
            erro = f"Muitas tentativas de login. Tente novamente em {minutos} minuto(s)."
        else:
            usuario = buscar_usuario_por_email(email)
            senha_hash = usuario["senha"] if usuario else None
            # chamar fora do "and" — ver 03-seguranca.md item 2
            senha_confere = verificar_senha_tempo_constante(senha, senha_hash)
            if usuario and senha_confere:
                registrar_login_sucesso(email)
                session["usuario"] = {
                    "iduser": usuario["iduser"],
                    "nome": usuario["nome"],
                    "email": usuario["email"],
                    "tipouser": usuario["tipouser"],
                }
                return redirect(url_for("index"))
            registrar_login_falho(email)
            erro = "E-mail ou senha inválidos."
    return render_template("login.html", erro=erro)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
```

## 9. Template `login.html`

Copie `app/templates/login.html` deste projeto e ajuste só o título/branding — a lógica
(token CSRF no hidden input, limpar campos no load, Enter avança para o próximo campo)
não depende de nada específico do domínio EAD.

## 10. Script de inicialização (`scripts/init_db.py` equivalente)

1. Cria as tabelas com `CREATE TABLE IF NOT EXISTS` (idempotente).
2. Cria o usuário administrador padrão, gerando o hash em Python com `hash_senha()`
   antes do `INSERT` (nunca gere hash em SQL puro).
3. Se o projeto crescer e precisar adicionar colunas depois, use blocos
   `DO $$ ... EXCEPTION WHEN duplicate_column THEN NULL; END $$;` em vez de recriar a
   tabela — permite rodar o script de novo em produção sem apagar dados.

## 11. Checklist de validação antes de considerar a reescrita completa

- [ ] Login com e-mail/senha corretos redireciona para a área certa conforme o perfil.
- [ ] Login com senha errada mostra sempre a mesma mensagem genérica.
- [ ] Login com e-mail que não existe mostra a mesma mensagem genérica (e no mesmo
      tempo de resposta aproximado — teste medindo, não só visualmente).
- [ ] 5 tentativas erradas no mesmo e-mail bloqueiam por 15 min; a 6ª tentativa (mesmo
      com senha certa) mostra a mensagem de bloqueio sem consultar o banco de usuários.
- [ ] Depois do bloqueio expirar, login com senha certa funciona normalmente de novo.
- [ ] Login certo zera o contador de tentativas daquele e-mail.
- [ ] `/logout` limpa a sessão e qualquer rota protegida volta a exigir login.
- [ ] Rota protegida por `role_required` redireciona (não quebra) quando acessada por
      outro perfil.
- [ ] Submeter o formulário de login sem o token CSRF (ex.: via `curl -X POST` direto)
      é rejeitado.
- [ ] Em produção, cookie de sessão só é enviado sobre HTTPS (`SESSION_COOKIE_SECURE=1`)
      — testar que isso **não** quebra o login local em HTTP durante o desenvolvimento
      (deve ficar `0` em dev).
- [ ] Senha nunca aparece em texto puro em log, no banco, nem na resposta HTTP.
