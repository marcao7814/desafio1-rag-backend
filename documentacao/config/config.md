# Verificação de Compatibilidade — Sistema EAD × Hostinger VPS

> Checagem feita comparando o estado **atual** do projeto (código em `app/`, `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.env.example`) contra os requisitos levantados em [`documentos/A estudo Hostinger/estudohostinger.md`](../A%20estudo%20Hostinger/estudohostinger.md). O passo a passo de execução está em [`passo.md`](./passo.md).

## Resultado: ✅ Em produção

Deploy concluído em 2026-11-16. Sistema no ar em **https://2-25-71-176.sslip.io** (HTTPS real, redirecionamento automático a partir do HTTP), rodando na VPS Hostinger (IP `2.25.71.176`).

| Item verificado | Situação atual | Compatível? |
|---|---|---|
| Stack web | Flask 3 (`app/web.py`, objeto `app` no módulo) | ✅ |
| Banco de dados | PostgreSQL (`pgvector/pgvector:pg16`) via `psycopg2-binary` (`app/banco/conexao.py`) | ✅ |
| Containerização | `Dockerfile` (Python 3.12-slim) + `docker-compose.yml` com serviços `db`, `ollama`, `init`, `web` (nginx compartilhado — ver seção abaixo) | ✅ |
| Persistência de dados | Volumes `pgdata`, `ollama_data` (Postgres/Ollama) + `./uploads:/app/uploads` (PDF/MP4) | ✅ |
| Variáveis de ambiente | App já lê `DB_HOST/PORT/NAME/USER/PASSWORD`, `SECRET_KEY`, `SESSION_COOKIE_SECURE` via `os.getenv()` | ✅ |
| CSRF / upload seguro | `CSRFProtect` ativo, validação de extensão (`.pdf`/`.mp4`), `secure_filename`, IDOR check no download (`/uploads/<filename>`) | ✅ |
| Cookies de sessão | `HTTPONLY=True`, `SAMESITE=Lax`, `SECURE=1` ativo em produção — confirmado via teste de login real (`Set-Cookie: ...; Secure; HttpOnly; SameSite=Lax`) | ✅ |
| Servidor de produção | Gunicorn (`gunicorn --bind 0.0.0.0:5000 --workers 3 app.web:app`) | ✅ |
| Segredos | Fora do `docker-compose.yml` — só no `.env` da VPS (`DB_USER=projetoead`, `DB_PASSWORD=ea500`, `SECRET_KEY=docker500`) | ✅ |
| Porta do Postgres | Não publicada — só acessível pela rede interna do Docker | ✅ |
| Proxy reverso / TLS | nginx compartilhado (`infra-nginx`), HTTPS via Let's Encrypt (expira 2027-02-14), HTTP→HTTPS automático | ✅ |
| Repositório git | `github.com/marcao7814/projeto-ead` (privado), deploy via deploy key SSH dedicada na VPS | ✅ |
| Credencial padrão de admin | `admin@gmail.com`, senha padrão `admin123` trocada diretamente no banco de produção — login testado com a senha nova e confirmado que `admin123` não funciona mais | ✅ |

### Acesso à VPS

- IP: `2.25.71.176` (Ubuntu 26.04 LTS).
- Autenticação: chave SSH dedicada `~/.ssh/id_ead_vps` (gerada nesta máquina, sem senha, só essa chave está autorizada em `/root/.ssh/authorized_keys` da VPS) — a senha root original não foi salva em nenhum arquivo do projeto nem do git.
- Código em `/opt/ead` (clonado via deploy key SSH própria, `~/.ssh/github_deploy` na VPS — acesso só leitura ao repositório).
- Infra do nginx compartilhado em `/opt/infra-nginx`.

### Sem domínio registrado — usando sslip.io

Sem domínio próprio, o acesso é pelo IP público da VPS via [sslip.io](https://sslip.io): `2-25-71-176.sslip.io` resolve automaticamente para `2.25.71.176`, o que permitiu ao Certbot emitir certificado TLS real sem precisar de domínio comprado nem propagação de DNS.

### Vários projetos na mesma VPS — nginx compartilhado

O nginx roda fora deste repositório, em [`documentos/config/infra-nginx/`](./infra-nginx/) (cópia ativa em `/opt/infra-nginx` na VPS) — dono único das portas 80/443, roteando por domínio para cada projeto. Este projeto só expõe a porta interna (`expose: ["5000"]`, `container_name: ead-web`) na rede externa `proxy_net`. Para o próximo projeto: só criar um `conf.d/<projeto>.conf` novo em `infra-nginx/` e colocar o `web` dele na mesma rede — sem mexer neste repositório. Detalhes em [`infra-nginx/README.md`](./infra-nginx/README.md).

## Pendências

- [x] Senha do admin padrão trocada (direto no banco de produção, via `hash_senha` do próprio app) — a senha não fica registrada neste documento nem no git, por segurança.
- [x] Renovação automática do certificado agendada — cron diário às 3h (`crontab -l` na VPS), log em `/var/log/certbot-renew.log`.
- [x] Backup diário do banco agendado — cron às 2h30 rodando [`scripts/backup_db.sh`](../../scripts/backup_db.sh), dump comprimido em `/opt/backups/ead/` na VPS, retenção de 14 dias, log em `/var/log/ead-backup.log`. Testado manualmente e validado (dump `pg_dump` íntegro).

### ⚠️ Backup só existe na própria VPS

Os backups ficam em `/opt/backups/ead/` — **no mesmo servidor** que hospeda o sistema. Isso cobre erro humano (ex. apagar dado por engano), mas **não cobre perda total da VPS** (falha de hardware, exclusão da instância, etc.) — se a VPS for perdida, os backups vão junto. Para proteção real contra desastre, o ideal é copiar os backups periodicamente para um local externo (outro servidor, S3/object storage, etc.) — não configurado ainda, pode ser um próximo passo se quiser.
