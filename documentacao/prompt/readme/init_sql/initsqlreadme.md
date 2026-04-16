# init.sql — Schema de Referência do Banco

## O que faz

Script SQL executado automaticamente pelo Docker na **primeira criação** do container PostgreSQL. Habilita as extensões necessárias e cria as tabelas de referência do LangChain.

## Localização

```
scripts/init.sql
```

Montado no container em:
```
/docker-entrypoint-initdb.d/init.sql
```

## Quando é executado

Apenas uma vez: na **primeira inicialização** do container, quando o volume `pgdata` está vazio. Em inicializações subsequentes (`docker compose up -d` com volume existente), o script **não é executado novamente**.

Para forçar a reexecução, apague o volume:
```bash
docker compose down -v && docker compose up -d
```

## Conteúdo

### Extensões habilitadas

```sql
CREATE EXTENSION IF NOT EXISTS vector;       -- pgVector: suporte a embeddings
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- Geração de UUIDs
```

### Tabelas criadas (referência)

```sql
CREATE TABLE IF NOT EXISTS langchain_pg_collection (
    name      VARCHAR     NOT NULL,
    cmetadata JSONB,
    uuid      UUID        PRIMARY KEY DEFAULT uuid_generate_v4()
);

CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
    id            VARCHAR     PRIMARY KEY,          -- VARCHAR, não UUID!
    collection_id UUID        REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
    embedding     vector,
    document      VARCHAR,
    cmetadata     JSONB                             -- cmetadata, não metadata!
);
```

## Papel do init.sql vs. LangChain

| Responsabilidade       | init.sql                        | langchain_postgres               |
|------------------------|---------------------------------|----------------------------------|
| Extensão `vector`      | ✅ Habilita                     | —                                |
| Extensão `uuid-ossp`   | ✅ Habilita                     | —                                |
| Criação das tabelas    | Cria estrutura inicial          | **Recria com schema correto**    |
| Tipo do campo `id`     | `VARCHAR` (correto)             | `VARCHAR` (confirma)             |
| Campo `cmetadata`      | Define como `JSONB`             | Usa `cmetadata` (não `metadata`) |

> O `langchain_postgres >= 0.0.12` gerencia o schema das tabelas de embeddings de forma independente. Se houver conflito de schema (ex.: `id` como UUID), o LangChain lança erro `DatatypeMismatch`. Nesse caso, apague as tabelas e deixe o LangChain recriá-las.

## Pontos críticos documentados

### `id VARCHAR` (não UUID)

```sql
-- ✅ CORRETO — compatível com langchain_postgres >= 0.0.12
id VARCHAR PRIMARY KEY

-- ❌ ERRADO — causa DatatypeMismatch
id UUID PRIMARY KEY DEFAULT uuid_generate_v4()
```

### Campo de metadados: `cmetadata`

```sql
-- ✅ CORRETO
cmetadata JSONB

-- ❌ ERRADO — o LangChain espera "cmetadata", não "metadata"
metadata JSONB
```

### Consultas diretas ao banco

Ao consultar metadados diretamente via SQL (sem LangChain):

```sql
-- ✅ Correto
SELECT cmetadata->>'source' AS source FROM langchain_pg_embedding;

-- ❌ Errado
SELECT metadata->>'source' AS source FROM langchain_pg_embedding;
```

## Verificar estado após inicialização

```bash
# Conectar ao banco
docker exec -it rag_postgres psql -U postgres -d ragdb

# Verificar extensões
SELECT extname FROM pg_extension;

# Verificar tabelas
\dt

# Verificar schema da tabela de embeddings
\d langchain_pg_embedding
```
