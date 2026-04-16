# docker-compose.yml — Banco de Dados PostgreSQL + pgVector

## O que faz

Define e gerencia o container Docker com PostgreSQL 16 + extensão pgVector, usado como banco vetorial e de cache do sistema RAG.

## Localização

```
docker-compose.yml
scripts/init.sql     ← executado automaticamente na primeira criação do container
```

## Como iniciar

```bash
# Iniciar em background
docker compose up -d

# Ver logs
docker compose logs -f db

# Parar (mantém dados)
docker compose down

# Parar e apagar todos os dados
docker compose down -v
```

## Configuração do serviço

```yaml
services:
  db:
    image: pgvector/pgvector:pg16   # PostgreSQL 16 com pgVector pré-instalado
    container_name: rag_postgres
    restart: unless-stopped         # Reinicia automaticamente exceto se parado manualmente
    environment:
      POSTGRES_USER:     postgres
      POSTGRES_PASSWORD: 7878
      POSTGRES_DB:       ragdb
    ports:
      - "5433:5432"                 # Porta externa 5433 → interna 5432
    volumes:
      - pgdata:/var/lib/postgresql/data          # Persistência dos dados
      - ./scripts/init.sql:/docker-entrypoint-initdb.d/init.sql  # Schema inicial
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d ragdb"]
      interval: 10s
      timeout: 5s
      retries: 5
```

## Dados de conexão

| Campo      | Valor                                                                 |
|------------|-----------------------------------------------------------------------|
| Host       | `localhost`                                                           |
| Porta      | `5433` (externa) / `5432` (interna)                                   |
| Usuário    | `postgres`                                                            |
| Senha      | `7878`                                                                |
| Database   | `ragdb`                                                               |

### String de conexão (usada no `.env`)

```env
# Formato SQLAlchemy (LangChain / PGVector)
DATABASE_URL=postgresql+psycopg://postgres:7878@localhost:5433/ragdb

# Formato psycopg direto (psycopg.connect — usado internamente pelo frontEnd.py)
# O app converte automaticamente removendo o "+psycopg"
```

## Imagem utilizada

`pgvector/pgvector:pg16`

- PostgreSQL 16 oficial
- Extensão `vector` (pgVector) pré-compilada e instalada
- Não requer instalação manual da extensão

## Volume de dados

```yaml
volumes:
  pgdata:    # Volume nomeado gerenciado pelo Docker
```

Os dados sobrevivem a `docker compose down`. Apenas `docker compose down -v` remove o volume e apaga tudo.

## init.sql — Schema inicial

O arquivo `scripts/init.sql` é montado em `/docker-entrypoint-initdb.d/` e executado **apenas na primeira criação** do container (quando o volume `pgdata` está vazio).

### O que o init.sql faz

```sql
-- Habilita extensões necessárias
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Cria tabelas de referência do LangChain
-- (as tabelas reais são recriadas pelo langchain_postgres com o schema correto)
CREATE TABLE IF NOT EXISTS langchain_pg_collection (...);
CREATE TABLE IF NOT EXISTS langchain_pg_embedding  (...);
```

> **Atenção:** As tabelas do `init.sql` servem apenas como **referência de schema**. O `langchain_postgres` recria as tabelas com o schema correto na primeira execução. O campo `id` deve ser `VARCHAR` (não UUID) na tabela `langchain_pg_embedding`.

## Health check

O health check verifica se o PostgreSQL está aceitando conexões com `pg_isready`:

| Parâmetro  | Valor  |
|------------|--------|
| Intervalo  | 10s    |
| Timeout    | 5s     |
| Tentativas | 5      |

O `ini.bat` aguarda 5 segundos após `docker compose up -d` antes de iniciar o Streamlit, garantindo que o banco esteja pronto.

## Comandos úteis

```bash
# Verificar se o container está rodando
docker ps --filter name=rag_postgres

# Conectar ao banco via psql
docker exec -it rag_postgres psql -U postgres -d ragdb

# Ver tabelas criadas
docker exec -it rag_postgres psql -U postgres -d ragdb -c "\dt"

# Recriar container do zero (apaga todos os dados)
docker compose down -v && docker compose up -d
```
