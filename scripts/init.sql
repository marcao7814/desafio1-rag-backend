-- =============================================================
-- Inicialização do banco de dados RAG
-- =============================================================

-- Habilitar extensão pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Habilitar geração de UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================
-- Tabela principal de documentos (usada pelo langchain_postgres)
-- IMPORTANTE: id é VARCHAR, não UUID — compatível com langchain_postgres >= 0.0.12
-- As tabelas são criadas automaticamente pelo langchain_postgres na primeira execução.
-- Esta declaração serve apenas como referência do schema esperado.
-- =============================================================

CREATE TABLE IF NOT EXISTS langchain_pg_collection (
    name      VARCHAR     NOT NULL,
    cmetadata JSONB,
    uuid      UUID        PRIMARY KEY DEFAULT uuid_generate_v4()
);

CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
    id            VARCHAR     PRIMARY KEY,
    collection_id UUID        REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
    embedding     vector,
    document      VARCHAR,
    cmetadata     JSONB
);
