# Estudo Hostinger — VPS, Docker, Python, PostgreSQL e Publicação na Internet

> Fonte: interação direta com o **Agente de IA da Hostinger** (chat do site https://www.hostinger.com/br, 2026-11-14) complementada com boas práticas gerais de administração de servidores Linux.

---

## 1. Servidor VPS

### 1.1 O que é

O VPS (*Virtual Private Server*) da Hostinger é um servidor virtual **autogerenciado**: diferente da hospedagem compartilhada, aqui você tem **acesso root completo** e é responsável por administrar o sistema operacional, firewall, serviços (Docker, banco de dados, etc.) e segurança. Em compensação, tem controle total sobre o ambiente — pode instalar qualquer stack (Python, Node.js, Docker, Postgres, etc.).

### 1.2 Criar e acessar o VPS

1. Escolher um plano de VPS com **Ubuntu LTS** (distribuição recomendada por estabilidade e suporte longo).
2. No painel (hPanel), obter:
   - IP público do servidor;
   - usuário administrativo (`root`);
   - senha ou chave SSH;
   - sistema operacional instalado.
3. Conectar via SSH:

```bash
ssh root@IP_DO_VPS
```

4. Atualizar o sistema:

```bash
apt update && apt upgrade -y
```

5. Criar um usuário administrativo separado (boa prática — evitar operar como `root` no dia a dia):

```bash
adduser deploy
usermod -aG sudo deploy
```

A partir daqui, prefira acessar o servidor com o usuário `deploy` em vez de `root`.

### 1.3 Segurança inicial do servidor

```bash
timedatectl set-timezone America/Sao_Paulo
hostnamectl set-hostname meu-servidor
apt install ufw fail2ban -y
```

Liberar somente as portas necessárias:

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

**Recomendações:**
- Usar autenticação por **chave SSH** (não só senha).
- Desativar o login SSH direto do `root` (`PermitRootLogin no` em `/etc/ssh/sshd_config`).
- Nunca expor o PostgreSQL publicamente (porta 5432 fechada para a internet).
- Manter o Ubuntu sempre atualizado (`apt update && apt upgrade`).
- Fazer backups externos do banco e dos arquivos (fora do próprio VPS).
- Armazenar senhas e segredos em variáveis de ambiente — nunca no código versionado.

### 1.4 Painel hPanel — Docker Manager

Além da linha de comando, a Hostinger oferece o **Docker Manager** direto no painel, com deploy visual de containers:

1. Abrir **VPS**.
2. Clicar em **Manage**.
3. Abrir **Docker Manager**.
4. Selecionar **Compose**.
5. Escolher uma das opções:
   - Compose a partir de uma URL;
   - Compose manual (colar o `docker-compose.yml`);
   - Deploy com um clique (templates prontos, ex.: Postgres, n8n, etc.).

Isso é um diferencial da Hostinger para quem não quer operar 100% via terminal.

---

## 2. Docker — instalação e parâmetros

### 2.1 Instalação no Ubuntu (via terminal)

Remover versões antigas (evita conflito com pacotes legados do Ubuntu):

```bash
apt remove docker docker-engine docker.io containerd runc
```

Instalar pré-requisitos:

```bash
apt install ca-certificates curl gnupg -y
```

Adicionar o repositório oficial do Docker e instalar o Docker Engine + plugin de Compose:

```bash
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt update
apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y
```

Verificar instalação:

```bash
docker --version
docker compose version
```

Permitir que o usuário `deploy` use Docker sem `sudo`:

```bash
usermod -aG docker deploy
```

> Saia e entre novamente na sessão SSH para a alteração de grupo ter efeito.

### 2.2 Docker Manager da Hostinger (via painel)

Mesmo fluxo descrito em [1.4](#14-painel-hpanel--docker-manager) — útil para quem prefere interface gráfica ao invés de editar `docker-compose.yml` manualmente via SSH.

### 2.3 Parâmetros principais do Docker Compose

Para cada serviço de um `docker-compose.yml`, os parâmetros essenciais são:

| Parâmetro | Descrição |
|---|---|
| **Nome do projeto** | Identificador do conjunto de containers (`COMPOSE_PROJECT_NAME`). |
| **Nome do container** (`container_name`) | Nome único do serviço, usado em `docker logs`, `docker exec`, etc. |
| **Imagem** (`image`) | Imagem Docker utilizada (ex.: `python:3.12-slim`, `postgres:16`). |
| **Portas** (`ports`) | Mapeamento `HOST:CONTAINER`, ex.: `"8000:8000"`. |
| **Volumes** (`volumes`) | Armazenamento persistente, ex.: `pgdata:/var/lib/postgresql/data`. |
| **Variáveis de ambiente** (`environment` / `env_file`) | Senhas, portas, configurações — nunca hardcoded na imagem. |
| **Política de reinício** (`restart`) | `always` \| `unless-stopped` \| `on-failure` \| `no`. |
| **Rede** (`networks`) | Rede interna entre os containers (app ↔ banco), isolada da internet. |
| **depends_on** | Ordem de inicialização entre serviços (ex.: app depende do Postgres). |
| **healthcheck** | Verificação de saúde do container (reinício automático se falhar). |

**Exemplo de `docker-compose.yml` para app Python + PostgreSQL:**

```yaml
services:
  app:
    build: .
    container_name: meu-app
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://app_user:SENHA_FORTE@postgres:5432/app_db
    depends_on:
      - postgres
    networks:
      - rede-interna

  postgres:
    image: postgres:16
    container_name: meu-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: app_user
      POSTGRES_PASSWORD: SENHA_FORTE
      POSTGRES_DB: app_db
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - rede-interna
    # Sem "ports" publicada propositalmente — o Postgres não deve ser acessível pela internet

volumes:
  pgdata:

networks:
  rede-interna:
```

Para uma aplicação Python típica em produção, a composição ideal é:
1. Um container da aplicação;
2. Um container PostgreSQL;
3. Opcionalmente, um proxy reverso (Nginx ou Caddy);
4. Volume(s) para persistir o banco;
5. Uma rede interna entre os containers — **o PostgreSQL nunca deve ter a porta publicada para a internet** (sem `ports:` mapeado para o host).

**Comandos úteis do dia a dia:**

```bash
docker ps
docker logs NOME_DO_CONTAINER
docker compose ps
docker compose logs -f
docker compose restart
docker compose down
docker compose up -d --build
```

---

## 3. Python — instalação e uso

### 3.1 Instalação no VPS (direto no Ubuntu)

```bash
apt install python3 python3-pip python3-venv python3-dev build-essential -y
```

Verificar:

```bash
python3 --version
pip3 --version
```

Criar a pasta do projeto:

```bash
mkdir -p /opt/meu-projeto
cd /opt/meu-projeto
```

Criar e ativar um ambiente virtual (**isola as dependências do projeto do Python global do sistema**):

```bash
python3 -m venv venv
source venv/bin/activate
```

Atualizar o instalador de pacotes e instalar dependências:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> Não instalar pacotes globalmente sem necessidade — o ambiente virtual evita conflito de versões entre projetos diferentes no mesmo servidor.

### 3.2 Framework e servidor de produção

Frameworks Python comuns: **Flask**, **Django**, **FastAPI**.

Em produção, **nunca** usar o servidor de desenvolvimento embutido do framework (`flask run`, `python manage.py runserver`, `uvicorn --reload`). Usar um servidor WSGI/ASGI de produção:

| Framework | Servidor de produção |
|---|---|
| Flask / Django (WSGI) | **Gunicorn** |
| FastAPI (ASGI) | **Uvicorn** (ou Gunicorn com worker ASGI, ex.: `uvicorn.workers.UvicornWorker`) |

A aplicação deve escutar em uma porta interna, não na 80/443 diretamente:

```text
0.0.0.0:8000
```

O proxy reverso (Nginx/Caddy) é quem recebe as requisições públicas (80/443) e as encaminha para essa porta interna.

**Exemplo — Gunicorn:**
```bash
gunicorn --workers 3 --bind 0.0.0.0:8000 app:app
```

**Exemplo — Uvicorn (FastAPI):**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 3
```

### 3.3 Configurações importantes via variáveis de ambiente

Nunca hardcodar no código-fonte. Definir via variáveis de ambiente (`.env`, `env_file` no Compose, ou `systemd` `Environment=`):

- ambiente de produção (`ENV=production`);
- chave secreta da aplicação (`SECRET_KEY`);
- URL de conexão do banco (`DATABASE_URL`);
- usuário e senha do PostgreSQL;
- modo de depuração **desativado** (`DEBUG=False`);
- domínio(s) autorizado(s) (`ALLOWED_HOSTS`);
- origem permitida para CORS;
- caminho de arquivos estáticos;
- nível de log.

> **Nunca** deixar `DEBUG` ativado em produção — expõe stack trace, variáveis internas e caminhos do servidor (information disclosure).

---

## 4. PostgreSQL — instalação e uso

### 4.1 PostgreSQL direto no Ubuntu

```bash
apt install postgresql postgresql-contrib -y
```

Verificar o serviço:

```bash
systemctl status postgresql
```

Acessar o console administrativo:

```bash
sudo -u postgres psql
```

Criar um usuário e um banco **exclusivos da aplicação** (nunca usar o superusuário `postgres` na aplicação):

```sql
CREATE USER app_user WITH PASSWORD 'SENHA_FORTE';
CREATE DATABASE app_db OWNER app_user;
```

Sair do console:

```sql
\q
```

String de conexão usada pela aplicação:

```text
postgresql://app_user:SENHA_FORTE@localhost:5432/app_db
```

### 4.2 PostgreSQL via Docker

Ao rodar o Postgres em container, configurar:

- **volume persistente** apontando para `/var/lib/postgresql/data` (sem isso, os dados são perdidos ao recriar o container);
- nome do banco (`POSTGRES_DB`);
- usuário (`POSTGRES_USER`);
- senha (`POSTGRES_PASSWORD`);
- política de reinício (`restart: unless-stopped`);
- rede interna (sem publicar a porta 5432 para fora);
- rotina de backup externo.

Dentro do Docker Compose, a aplicação acessa o banco **pelo nome do serviço** definido no `docker-compose.yml`, não por `localhost`:

```text
host=postgres port=5432 database=app_db user=app_user password=SENHA_FORTE
```

### 4.3 Migrações e backups

Usar a ferramenta de migração do próprio framework:
- **Django migrations** (Django);
- **Alembic** (SQLAlchemy / FastAPI);
- ferramenta equivalente de outros frameworks.

Backup regular com `pg_dump`:

```bash
pg_dump -U app_user -h localhost app_db > backup.sql
```

> O backup deve ser copiado para **outro local** (outro servidor, storage externo, S3, etc.). Um arquivo armazenado apenas no mesmo VPS não é uma estratégia de recuperação de desastres — se o VPS falhar, o backup se perde junto.

---

## 5. Disponibilizar o projeto Python na internet (endereço HTTP)

### 5.1 Domínio e DNS

1. Registrar ou usar um domínio existente.
2. Criar um registro DNS do tipo `A`:
   - nome: `@`;
   - valor: IP público do VPS.
3. Opcionalmente, criar outro registro:
   - nome: `www`;
   - valor: IP público do VPS.

> A propagação de DNS pode levar de minutos a algumas horas.

### 5.2 Proxy reverso

Fluxo recomendado de uma requisição:

```text
Internet → domínio → Nginx/Caddy → aplicação Python (Gunicorn/Uvicorn) → PostgreSQL
```

O proxy reverso deve:
- escutar nas portas 80 (HTTP) e 443 (HTTPS);
- encaminhar (`proxy_pass`) para a aplicação Python na porta interna (ex.: 8000);
- preservar os cabeçalhos HTTP originais (`Host`, `X-Forwarded-For`, `X-Forwarded-Proto`);
- servir arquivos estáticos diretamente (mais eficiente que deixar isso para o Python);
- limitar o tamanho de requisições, se necessário;
- habilitar HTTPS (TLS).

**Exemplo mínimo de Nginx:**
```nginx
server {
    listen 80;
    server_name seu-dominio.com www.seu-dominio.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> Nunca expor o servidor de desenvolvimento Python (`runserver`, `flask run`) diretamente à internet.

### 5.3 Serviço persistente (manter a aplicação sempre rodando)

**Se a aplicação roda direto no Ubuntu (sem Docker):** usar `systemd` para:
- iniciar a aplicação automaticamente no boot;
- reiniciá-la em caso de falha;
- definir usuário e diretório de execução;
- carregar variáveis de ambiente;
- registrar logs (`journalctl`).

**Exemplo de unit `systemd`** (`/etc/systemd/system/meu-app.service`):
```ini
[Unit]
Description=Meu App Python
After=network.target

[Service]
User=deploy
WorkingDirectory=/opt/meu-projeto
EnvironmentFile=/opt/meu-projeto/.env
ExecStart=/opt/meu-projeto/venv/bin/gunicorn --workers 3 --bind 0.0.0.0:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now meu-app
```

**Se a aplicação roda em Docker:** usar:
- `restart: unless-stopped`;
- `healthcheck`;
- logs rotacionados (`logging` driver no Compose);
- volume persistente;
- rede interna isolada.

### 5.4 HTTP e HTTPS

O endereço HTTP inicial será:

```text
http://seu-dominio.com
```

Para produção, o correto é usar **HTTPS**:

```text
https://seu-dominio.com
```

Configurar um certificado TLS gratuito no proxy reverso (ex.: **Let's Encrypt** via `certbot`) e redirecionar todo tráfego HTTP para HTTPS:

```bash
apt install certbot python3-certbot-nginx -y
certbot --nginx -d seu-dominio.com -d www.seu-dominio.com
```

> Nunca enviar senhas, tokens ou dados de usuários por HTTP puro (sem TLS).

---

## 6. Resumo — ciclo completo de implantação

1. Desenvolver o projeto Python localmente.
2. Definir o arquivo de dependências (`requirements.txt`).
3. Criar a imagem Docker da aplicação (`Dockerfile`) — ou preparar o ambiente direto no Ubuntu.
4. Configurar variáveis de ambiente (segredos, URL do banco, etc.).
5. Configurar PostgreSQL e volumes persistentes.
6. Publicar o código/imagem no VPS (git clone, scp, registry de imagens, etc.).
7. Fazer o deploy — via `docker compose up -d` ou pelo **Docker Manager** do hPanel.
8. Verificar logs (`docker compose logs -f` ou `journalctl`).
9. Testar a aplicação internamente (`curl http://127.0.0.1:8000`).
10. Configurar domínio (DNS) e proxy reverso (Nginx/Caddy).
11. Ativar HTTPS (Let's Encrypt).
12. Configurar backups externos e monitoramento.

### Arquitetura final recomendada

```text
VPS Hostinger
├── Firewall (ufw) + fail2ban
├── Proxy reverso (Nginx/Caddy) — portas 80/443, TLS
├── Docker
│   ├── Container da aplicação Python (Gunicorn/Uvicorn, porta interna 8000)
│   ├── Container PostgreSQL (porta interna 5432, sem exposição externa)
│   ├── Volume persistente do PostgreSQL
│   └── Rede privada Docker (app ↔ banco)
└── Backups externos (fora do VPS)
```

**Princípio central:** separar aplicação, banco de dados e proxy em camadas distintas, mantendo o PostgreSQL **inacessível diretamente pela internet** — toda comunicação externa passa obrigatoriamente pelo proxy reverso.
