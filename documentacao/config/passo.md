# Passo a Passo — Hospedar o Sistema EAD numa VPS Hostinger

> Guia executável baseado nos parâmetros definidos em [`hopedarHostinger.md`](./hopedarHostinger.md) (mesma pasta). Specs do projeto: Flask + PostgreSQL (pgvector) + Ollama + Docker Compose, serviços `db`/`ollama`/`init`/`web` em [`docker-compose.yml`](../../docker-compose.yml). Decisões já tomadas (ver [`config.md`](./config.md) para o histórico completo):
>
> - **Sem domínio próprio** — acesso via IP da VPS usando um domínio gratuito [sslip.io](https://sslip.io) (ex. IP `203.0.113.10` → `203-0-113-10.sslip.io`).
> - **Vários projetos na mesma VPS** — nginx compartilhado em [`infra-nginx/`](./infra-nginx/) (fora deste repositório na VPS), não um nginx por projeto.
> - **Envio do código via Git** — repositório já existe: `https://github.com/marcao7814/projeto-ead.git`.
> - **E-mail do Certbot**: `marcao7814@gmail.com`.

## Passo 0 — Pré-requisitos

- [ ] VPS Hostinger (Docker pré-instalado ou Ubuntu/Debian puro — o Passo 3 instala o Docker do zero).
- [ ] Acesso SSH root à VPS (IP público + senha ou chave).
- [x] Projeto já é um repositório git, com os ajustes de produção (Gunicorn, segredos em `.env`, sem nginx embutido) já commitados — ver Passo 1.

---

## Passo 1 — Preparar o projeto para produção (✅ já feito no repositório)

Não precisa repetir nada aqui — já está commitado e pushado:

- [`Dockerfile`](../../Dockerfile) roda Gunicorn (`gunicorn --bind 0.0.0.0:5000 --workers 3 app.web:app`), não o servidor de dev do Flask.
- [`docker-compose.yml`](../../docker-compose.yml) não tem segredo nenhum fixo — `db`, `init` e `web` usam `env_file: .env`. O `.env` de produção **ainda precisa ser criado na VPS** (ver Passo 4).
- `db` não publica a porta 5432.
- `web` não publica porta nenhuma (`expose: ["5000"]`, `container_name: ead-web`) — quem fala com ele é o nginx compartilhado, pela rede externa `proxy_net`.

---

## Passo 2 — DNS (não aplicável — usando sslip.io)

Sem domínio registrado, esse passo não existe: assim que soubermos o IP público da VPS (Passo 3), o domínio de acesso já existe automaticamente — `<IP-com-hifen>.sslip.io` — sem precisar criar registro DNS nem esperar propagação.

---

## Passo 3 — Preparar a VPS via SSH

```bash
ssh root@<IP_DA_VPS>

apt update && apt upgrade -y
apt install -y curl git ufw

# Docker Engine + Compose plugin
curl -fsSL https://get.docker.com | sh

# Firewall básico
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# Rede compartilhada entre o nginx da VPS e os containers "web" de cada projeto
docker network create proxy_net
```

---

## Passo 4 — Enviar o código e preparar a infraestrutura compartilhada

```bash
# Clona o projeto
cd /opt
git clone https://github.com/marcao7814/projeto-ead.git ead
cd ead

# Cria o .env de produção (não vem do git — está no .gitignore)
nano .env
```

Conteúdo do `.env` (pode reaproveitar os valores de dev ou gerar outros):
```env
DB_HOST=db
DB_PORT=5432
DB_NAME=ead_db
DB_USER=projetoead
DB_PASSWORD=ea500
SECRET_KEY=docker500
OLLAMA_HOST=http://ollama:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
SESSION_COOKIE_SECURE=0
```
(`SESSION_COOKIE_SECURE` começa em `0` e só vira `1` depois que o HTTPS do Passo 6 estiver funcionando.)

A infraestrutura de nginx compartilhado (`infra-nginx/`) não é específica deste projeto — copie para fora de `/opt/ead` na primeira vez que configurar a VPS:

```bash
cp -r /opt/ead/documentos/config/infra-nginx /opt/infra-nginx
```
(Em deploys futuros de **outros** projetos, `/opt/infra-nginx` já vai existir — só adicionar o `conf.d/<novo-projeto>.conf` dele, sem recopiar a pasta inteira. Ver [`infra-nginx/README.md`](./infra-nginx/README.md).)

Ajuste o domínio no vhost deste projeto, trocando `SEU-IP-COM-HIFEN.sslip.io` pelo IP real da VPS:
```bash
sed -i "s/SEU-IP-COM-HIFEN/<IP-com-hifen>/g" /opt/infra-nginx/conf.d/projeto-ead.conf
```

---

## Passo 5 — Subir o nginx compartilhado e a stack do projeto

```bash
# nginx compartilhado (uma vez por VPS)
cd /opt/infra-nginx
docker compose up -d nginx

# stack deste projeto
cd /opt/ead
docker compose up -d --build
docker compose ps   # db (healthy), ollama (up), init (exited 0), web (up)

# modelo de embeddings do RAG
docker compose exec ollama ollama pull nomic-embed-text
```

Nesse ponto o sistema já responde em `http://<IP-com-hifen>.sslip.io` (HTTP, ainda sem certificado).

---

## Passo 6 — Emitir o certificado HTTPS (Certbot, método webroot)

```bash
cd /opt/infra-nginx
docker compose run --rm certbot certonly \
  --webroot -w /var/www/certbot \
  -d <IP-com-hifen>.sslip.io \
  --email marcao7814@gmail.com --agree-tos --no-eff-email
```

Depois:
1. Em `/opt/infra-nginx/conf.d/projeto-ead.conf`, troque o bloco "PASSO 1" pelos dois blocos do "PASSO 2" (redirecionamento HTTP→HTTPS + servidor 443 com o certificado) — ver comentários no próprio arquivo.
2. `docker exec infra-nginx nginx -t && docker exec infra-nginx nginx -s reload`.
3. Em `/opt/ead/.env`, troque `SESSION_COOKIE_SECURE=0` para `SESSION_COOKIE_SECURE=1`.
4. `cd /opt/ead && docker compose up -d --force-recreate web` (recarrega o `.env`).

Renovação automática — ver seção "Renovação automática" em [`infra-nginx/README.md`](./infra-nginx/README.md).

---

## Passo 7 — Verificação pós-deploy

1. Acesse `https://<IP-com-hifen>.sslip.io/login`.
2. Entre com o admin padrão: `admin@gmail.com` / `admin123`.
3. **Troque essa senha imediatamente** no painel ADM — é uma credencial pública nesta documentação.
4. Teste upload de PDF/vídeo numa aula para validar o `client_max_body_size` do nginx.
5. Confirme que o cookie de sessão está marcado `Secure` (DevTools → Application → Cookies).

---

## Passo 8 — Operação contínua

```bash
# logs em tempo real
cd /opt/ead && docker compose logs -f web

# redeploy após alteração de código (sem migração nova no banco)
cd /opt/ead && git pull && docker compose up -d --build --no-deps web

# redeploy quando a mudança inclui alteração de schema (nova tabela/coluna em init_db.py)
# IMPORTANTE: "run" sem --build usa a imagem antiga em cache e pode pular a migração silenciosamente
cd /opt/ead && git pull && docker compose run --build --rm init && docker compose up -d --build --no-deps web

# backup do banco
docker compose exec db pg_dump -U projetoead ead_db > backup_$(date +%F).sql

# limpeza de imagens antigas
docker image prune -f
```

---

## Checklist final

- [x] Gunicorn no lugar do servidor de dev do Flask
- [x] `SECRET_KEY`/`DB_PASSWORD` fora do `docker-compose.yml`, só no `.env`
- [x] Porta `5432` não exposta publicamente
- [x] `web` sem porta pública própria, atrás do nginx compartilhado
- [x] HTTPS ativo via Certbot — `https://2-25-71-176.sslip.io`, válido até 2027-02-14
- [x] `SESSION_COOKIE_SECURE=1` no `.env` de produção — confirmado via login real (`Set-Cookie: ...; Secure`)
- [x] Senha do admin padrão trocada após o primeiro acesso
- [x] Backup do banco configurado — cron diário 2h30, `scripts/backup_db.sh`, retenção 14 dias
- [x] Renovação automática do certificado agendada via cron (diário às 3h)

> ✅ **Deploy concluído em 2026-11-16.** Sistema em produção: https://2-25-71-176.sslip.io — ver [`config.md`](./config.md) para o status atual e pendências.

> CSRF, path traversal no upload e IDOR no download de material já foram corrigidos no código-fonte (ver `documentos/criados/specs.md` §4/§6) — não exigem ação adicional neste deploy.
