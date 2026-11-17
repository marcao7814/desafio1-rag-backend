# Hospedar o Sistema EAD numa VPS Hostinger

> Guia específico para **este** projeto (Flask + PostgreSQL + Docker Compose com os serviços `db`/`init`/`web` já existentes em `docker-compose.yml`), não um template genérico. Cobre o que precisa mudar antes de ir para produção e o passo a passo de deploy numa VPS Hostinger com Docker.

## 0. Pré-requisitos

- VPS Hostinger (plano com Docker pré-instalado ou Ubuntu/Debian puro — o passo B instala o Docker do zero).
- Domínio apontando para a VPS (ou um subdomínio, ex. `ead.seudominio.com`).
- Acesso SSH root à VPS.
- Este projeto **ainda não é um repositório git** (`git init` nunca foi rodado) — o passo C cobre as duas formas de levar o código até a VPS.

---

## 1. Preparar o projeto para produção

O estado atual (ambiente de desenvolvimento local) tem três coisas que **não devem ir para produção como estão**:

### 1.1 Servidor de desenvolvimento → Gunicorn

O [Dockerfile](../../Dockerfile) atual roda o servidor embutido do Flask (`flask run`), que não é apto para produção (single-threaded, sem gestão de workers/crash recovery):

```dockerfile
CMD ["python", "-m", "flask", "--app", "app/web.py", "run", "--host", "0.0.0.0", "--port", "5000"]
```

**Troque por Gunicorn:**

1. Adicione ao [requirements.txt](../../requirements.txt):
   ```
   gunicorn
   ```
2. Troque o `CMD` do `Dockerfile` para:
   ```dockerfile
   CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "3", "app.web:app"]
   ```
   (`app.web:app` aponta para o objeto `app = Flask(...)` definido em `app/web.py`.)

### 1.2 Credenciais hardcoded → `.env`

O [docker-compose.yml](../../docker-compose.yml) atual tem `POSTGRES_PASSWORD: "7878"` e `SECRET_KEY: ead-secret-2026` **escritos direto no arquivo** — aceitável em dev local, inaceitável em produção (fica versionado/visível). Troque os serviços `db`, `init` e `web` para usar `env_file: .env` em vez de valores fixos, e gere valores fortes:

```bash
# Gerar uma SECRET_KEY forte
python3 -c "import secrets; print(secrets.token_hex(32))"

# Gerar uma senha forte para o Postgres
python3 -c "import secrets; print(secrets.token_urlsafe(24))"
```

Crie um `.env` de produção (nunca commitar — já está no `.gitignore`):
```env
DB_HOST=db
DB_PORT=5432
DB_NAME=ead_db
DB_USER=postgres
DB_PASSWORD=<senha gerada acima>
SECRET_KEY=<secret key gerada acima>
```

### 1.3 Proxy reverso + SSL (nginx + Certbot)

`web` expõe a porta `5000` direto — em produção ela deve ficar **atrás de um nginx** com HTTPS, nunca exposta publicamente sem TLS. Isso é feito com um serviço `nginx` adicional no Compose (passo 4) e Certbot para o certificado (passo 6).

### 1.4 Volumes que já estão corretos

- `pgdata` (dados do Postgres) e `./uploads:/app/uploads` (PDFs/MP4 enviados pelos professores) já são persistidos pelo `docker-compose.yml` atual — nada a mudar aqui, só garantir que o diretório `uploads/` na VPS tenha espaço em disco suficiente (vídeos MP4 podem ser grandes).

---

## 2. Apontar o DNS

No painel da Hostinger (ou onde o domínio estiver registrado), crie um registro **A**:

| Campo | Valor |
|---|---|
| Tipo | A |
| Host | `@` (domínio raiz) ou `ead` (subdomínio) |
| Aponta para | IP público da VPS |
| TTL | Padrão (300–3600s) |

Propagação pode levar de minutos a algumas horas.

---

## 3. Preparar a VPS via SSH

```bash
ssh root@<IP_DA_VPS>

# Atualizar o sistema
apt update && apt upgrade -y
apt install -y curl git ufw

# Instalar Docker Engine + Compose plugin
curl -fsSL https://get.docker.com | sh

# Firewall básico
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
```

---

## 4. Enviar o código para a VPS

Como o projeto **ainda não tem repositório git**, escolha uma das duas opções:

### Opção A — SCP/rsync (mais simples agora, não exige criar repositório)

A partir da sua máquina Windows (fora da VPS), via `rsync` (WSL/Git Bash) ou `scp`:

```bash
# rsync (recomendado — reenvio incremental, ignora uploads locais de teste)
rsync -avz --exclude 'uploads/*' --exclude '.env' \
  "/c/Projetos ia 03-2026/projeto EAD/" root@<IP_DA_VPS>:/opt/ead/
```

Depois, crie o `.env` de produção **diretamente na VPS** (nunca envie o `.env` local, que tem credenciais de dev):
```bash
ssh root@<IP_DA_VPS>
nano /opt/ead/.env   # cole os valores gerados no passo 1.2
```

### Opção B — Git (melhor para atualizações futuras)

Se preferir manter o projeto versionado, primeiro inicialize o repositório localmente e suba para o GitHub/GitLab:
```bash
cd "C:/Projetos ia 03-2026/projeto EAD"
git init
git add .
git commit -m "Primeira versão do Sistema EAD"
git remote add origin https://github.com/<seu-usuario>/<seu-repo>.git
git push -u origin main
```
Depois, na VPS:
```bash
cd /opt
git clone https://github.com/<seu-usuario>/<seu-repo>.git ead
cd ead
nano .env   # cole os valores gerados no passo 1.2
```

---

## 5. Adicionar o nginx ao `docker-compose.yml`

Edite o `docker-compose.yml` **na VPS** (ou localmente antes de enviar) para:
1. Trocar `ports: ["5000:5000"]` do serviço `web` por `expose: ["5000"]` (não fica mais exposto direto ao mundo).
2. Trocar os valores fixos de `environment` por `env_file: .env` nos serviços `db`, `init` e `web`.
3. Adicionar o serviço `nginx`:

```yaml
services:
  db:
    image: postgres:16-alpine
    env_file: .env
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 5s
      timeout: 5s
      retries: 10

  init:
    build: .
    env_file: .env
    command: python scripts/init_db.py
    depends_on:
      db:
        condition: service_healthy

  web:
    build: .
    expose:
      - "5000"
    env_file: .env
    volumes:
      - ./uploads:/app/uploads
    depends_on:
      init:
        condition: service_completed_successfully
    restart: always

  nginx:
    image: nginx:alpine
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - certs_data:/etc/letsencrypt
    depends_on:
      - web

volumes:
  pgdata:
  certs_data:
```

> Note que `ports: ["5432:5432"]` do `db` também deve ser **removido** em produção — o banco não precisa ficar acessível fora da rede interna do Docker.

Crie o `nginx.conf` ao lado do `docker-compose.yml`:

```nginx
server {
    listen 80;
    server_name ead.seudominio.com;

    client_max_body_size 200M;  # professores enviam PDF/MP4 — ajuste conforme necessário

    location / {
        proxy_pass http://web:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 6. Subir a stack e emitir o certificado SSL

```bash
cd /opt/ead

docker compose up -d --build
docker compose ps   # confirme db (healthy), init (exited 0), web (up), nginx (up)

# Certificado SSL gratuito via Certbot
apt install -y certbot python3-certbot-nginx
certbot --nginx -d ead.seudominio.com
```

O Certbot edita o `nginx.conf` automaticamente para redirecionar HTTP → HTTPS e configura a renovação automática.

---

## 7. Verificação

1. Acesse `https://ead.seudominio.com/login`.
2. Faça login com o admin padrão criado pelo `init_db.py`: `admin@gmail.com` / `admin123`.
3. **Troque a senha do admin padrão imediatamente** (editar usuário no painel ADM) — essa credencial é pública neste repositório/documentação.
4. Teste um upload de PDF/vídeo numa aula para confirmar que o `client_max_body_size` do nginx está adequado.

---

## 8. Operação

**Logs em tempo real:**
```bash
docker compose logs -f web
```

**Redeploy após alterações no código** (repita o passo 4 para reenviar os arquivos, depois):
```bash
docker compose up -d --build --no-deps web
```

**Backup do banco:**
```bash
docker compose exec db pg_dump -U postgres ead_db > backup_$(date +%F).sql
```

**Limpeza de imagens antigas:**
```bash
docker image prune -f
```

---

## Checklist antes de considerar "pronto para produção"

- [ ] `Dockerfile` usando Gunicorn, não o servidor de dev do Flask
- [ ] `SECRET_KEY` e `POSTGRES_PASSWORD` gerados aleatoriamente, fora do `docker-compose.yml`, só no `.env` da VPS
- [ ] Porta `5432` do `db` não exposta publicamente
- [ ] `web` atrás do nginx, sem porta `5000` exposta direto
- [ ] HTTPS ativo via Certbot
- [ ] Senha do admin padrão (`admin@gmail.com`/`admin123`) trocada após o primeiro acesso
- [ ] `client_max_body_size` do nginx compatível com os uploads de vídeo
- [ ] Backup do banco configurado (ao menos manual, idealmente agendado via cron)
- [ ] `SESSION_COOKIE_SECURE=1` definido no `.env` assim que o HTTPS (passo 6) estiver ativo — o cookie de sessão só é marcado `Secure` quando essa variável está ligada

> Ver também `documentos/criados/specs.md` §4 e §6 — validação de upload (tipo/tamanho/path traversal), CSRF e IDOR no download já foram corrigidos no código; o que resta é garantir que as variáveis de produção acima (`SECRET_KEY`, `POSTGRES_PASSWORD`, `SESSION_COOKIE_SECURE`) sejam configuradas corretamente nesta VPS.
