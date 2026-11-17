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

---

## Projeto 2 — Sistema RAG, mesma VPS

Deploy concluído em 2026-11-17. Sistema no ar em **https://rag.2-25-71-176.sslip.io**, compartilhando a VPS com o EAD acima.

| Item verificado | Situação atual | Compatível? |
|---|---|---|
| Stack web | Flask 3 (`src/app.py`, objeto `app`) | ✅ |
| Banco de dados | PostgreSQL (`pgvector/pgvector:pg16`) via `psycopg[binary]`, container próprio `ragdb` | ✅ |
| LLM / Embeddings | Ollama **compartilhado** com o projeto EAD (`ead-ollama-1`), não um Ollama novo — ver decisão abaixo | ✅ |
| Containerização | `Dockerfile` (Python 3.12-slim) + `docker-compose.prod.yml` com serviços `ragdb`, `web` | ✅ |
| Servidor de produção | Gunicorn (`--workers 2 --timeout 300`, timeout alto por causa de LLM em CPU) | ✅ |
| Segredos | Fora do `docker-compose.prod.yml` — só no `.env` da VPS | ✅ |
| Porta do Postgres | Não publicada | ✅ |
| Proxy reverso / TLS | nginx compartilhado, HTTPS via Let's Encrypt (expira 2027-02-15) | ✅ |
| Repositório git | `github.com/marcao7814/desafio1-rag-backend` (público — sem deploy key necessária) | ✅ |
| Cookies de sessão | `Secure; HttpOnly; SameSite=Lax` confirmado em produção | ✅ |

### Decisão: reaproveitar o Ollama do EAD em vez de subir outro

A VPS tem só **2 vCPUs / 7.7 GB RAM**. Rodar um segundo Ollama (mais um Postgres, mais um Flask) do zero arriscava sobrecarregar a CPU compartilhada e derrubar o EAD, que já estava em produção. Optou-se por conectar o container `web` deste projeto à rede `ead_default` (externa) e falar diretamente com `ead-ollama-1` — só foi necessário baixar mais modelos (o EAD só tinha `nomic-embed-text`). Testado sob carga: uma pergunta RAG não derrubou o EAD, mas a geração em CPU é lenta.

### Ajustes de performance (CPU-only, 2 vCPUs)

A resposta do RAG começou em vários minutos por pergunta — inviável para uso real. Dois ajustes, nessa ordem:

1. **`k` de 15 para 6** chunks de contexto em `_buscar_rag` (`src/app.py`) — menos texto pro LLM processar. Caiu para ~53s.
2. **Modelo `llama3.2` (3B) → `llama3.2:1b`** — ~3x menor, bem mais rápido em CPU, à custa de respostas um pouco mais simples. Decisão explícita do usuário (optou por velocidade em vez de manter o 3B).

Se a demanda crescer, os próximos ajustes possíveis são: limitar `num_predict` (teto de tokens gerados) e, como último recurso, considerar uma API de nuvem (Gemini/OpenAI) só em produção, mantendo Ollama no dev local.

### ⚠️ Armadilha encontrada: colisão de nome de serviço entre projetos

Ao conectar o `web` deste projeto também na rede `ead_default` (só para alcançar o Ollama), o nome do **próprio** serviço de banco deste projeto (`db`) colidiu com o serviço `db` do EAD, que existe na mesma rede. O DNS interno do Docker resolveu `db` para o Postgres **do EAD**, não o deste projeto — só não corrompeu nada porque as senhas são diferentes e a conexão falhou por autenticação em vez de "funcionar" silenciosamente no banco errado. Correção: renomear o serviço para algo único (`ragdb`) e, pelo mesmo motivo, referenciar o Ollama pelo `container_name` exato (`ead-ollama-1`), nunca pelo alias genérico de serviço (`ollama`/`db`). **Lição para o próximo projeto nesta VPS:** nunca usar nomes de serviço genéricos (`db`, `web`, `app`, `cache`...) em um compose que se conecta a uma rede externa compartilhada — sempre prefixar com o nome do projeto.

## Pendências (Projeto RAG)

- [ ] Backup do banco — só manual até agora, sem cron (diferente do EAD).
- [ ] Renovação automática do certificado para `rag.2-25-71-176.sslip.io` — não adicionada ao cron ainda.
- [ ] Senha do admin padrão (`admin78`) ainda não trocada — é pública nesta documentação, trocar pelo painel "Usuários" do próprio sistema.
