# Banco de Dados — PostgreSQL + pgVector

## O que faz

Armazena os embeddings vetoriais dos PDFs ingeridos e o cache de perguntas/respostas. Executado via Docker com a extensão pgVector habilitada.

## Localização dos arquivos

```
docker-compose.yml    # Define o container PostgreSQL + pgVector
scripts/init.sql      # Schema de referência (documentação; não executado pelo app)
```

## Inicialização

```bash
docker compose up -d
```

Porta exposta: `5433` (mapeada para `5432` interno).

## String de conexão

```env
# .env — formato SQLAlchemy (usado pelo LangChain/SQLAlchemy)
DATABASE_URL=postgresql+psycopg://postgres:senha@localhost:5433/ragdb

# Formato psycopg (usado pelo psycopg.connect diretamente)
# frontEnd.py remove o "+psycopg" automaticamente:
PSYCOPG_URL=postgresql://postgres:senha@localhost:5433/ragdb
```

> `psycopg.connect()` não aceita o prefixo `+psycopg` do SQLAlchemy. O `frontEnd.py` faz a conversão via `.replace("postgresql+psycopg://", "postgresql://")`.

## Tabelas

### `langchain_pg_collection` (criada automaticamente pelo LangChain)

```sql
CREATE TABLE langchain_pg_collection (
    name      VARCHAR,
    cmetadata JSONB,
    uuid      UUID PRIMARY KEY
);
```

Armazena as coleções de vetores. O nome da coleção é definido por `COLLECTION_NAME` no `.env` (default: `documentos_rag`).

### `langchain_pg_embedding` (criada automaticamente pelo LangChain)

```sql
CREATE TABLE langchain_pg_embedding (
    id            VARCHAR PRIMARY KEY,   -- VARCHAR, não UUID!
    collection_id UUID REFERENCES langchain_pg_collection(uuid),
    embedding     vector,
    document      VARCHAR,
    cmetadata     JSONB                  -- cmetadata, não metadata!
);
```

> **Atenção crítica:** `langchain_postgres >= 0.0.12` cria `id` como `VARCHAR`. Se a tabela foi criada com `id UUID`, ocorre erro `DatatypeMismatch`. Solução: dropar as tabelas e deixar o LangChain recriar.

### `search_cache` (criada pelo app na inicialização)

```sql
CREATE TABLE search_cache (
    id            SERIAL PRIMARY KEY,
    pergunta      TEXT NOT NULL,
    resposta      TEXT NOT NULL,
    chunks        JSONB,
    data_consulta TIMESTAMP DEFAULT NOW(),
    tipo          VARCHAR DEFAULT 'rag'
);
```

Ver [cachereadme.md](../cache/cachereadme.md) para detalhes do campo `chunks`.

## Metadados dos chunks (`cmetadata`)

Cada chunk gravado pelo LangChain contém:

```json
{
  "source": "/tmp/tmpXXXXXX.pdf",
  "page": 3,
  "original_name": "Contrato2024.pdf"
}
```

> O campo no banco é `cmetadata` (não `metadata`). Queries diretas devem usar `cmetadata->>'source'`, `cmetadata->>'original_name'`, etc.

## Queries usadas pelo app

### Listar PDFs gravados

```sql
SELECT DISTINCT
    cmetadata->>'source'        AS source,
    cmetadata->>'original_name' AS nome
FROM langchain_pg_embedding
WHERE collection_id = (
    SELECT uuid FROM langchain_pg_collection WHERE name = %s
)
ORDER BY source;
```

### Apagar um PDF pelo source

```sql
DELETE FROM langchain_pg_embedding
WHERE collection_id = (
    SELECT uuid FROM langchain_pg_collection WHERE name = %s
)
AND cmetadata->>'source' = %s;
```

### Apagar todos os PDFs da coleção

```sql
DELETE FROM langchain_pg_embedding
WHERE collection_id = (
    SELECT uuid FROM langchain_pg_collection WHERE name = %s
);
```

## Remover tudo e recomeçar

```bash
docker compose down -v   # Para o container e apaga o volume (todos os dados)
docker compose up -d     # Recria o container limpo
```

## Observações importantes

| Ponto                | Detalhe                                                             |
|----------------------|---------------------------------------------------------------------|
| `id` na embedding    | Deve ser `VARCHAR`, não `UUID`                                      |
| Campo de metadados   | `cmetadata` (não `metadata`)                                        |
| Troca de provider    | Embeddings OpenAI ≠ Gemini — reingerir todos os PDFs ao trocar      |
| Porta                | `5433` externa → `5432` interna no Docker                           |
| Prefixo da URL       | Remover `+psycopg` ao usar `psycopg.connect()` diretamente          |
