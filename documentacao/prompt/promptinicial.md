# Prompt Inicial — Geração da Documentação

Gere a documentação técnica completa em Markdown de um sistema RAG com os detalhes abaixo.

---

## Stack

- Python 3.11, Streamlit, LangChain, PostgreSQL + pgVector, Docker
- Provedores LLM/Embeddings: OpenAI ou Gemini (configurável via `LLM_PROVIDER`)
- Busca na internet: `google-genai` SDK (não LangChain), modelo `gemini-2.5-flash` + Google Search grounding
- Geração de PDF: ReportLab

## Arquivos

```
src/frontEnd.py     — app Streamlit principal (4 seções)
src/ingest.py       — ingestão de PDFs; expõe ingerir(pdf_path, nome_original, pre_delete)
src/search.py       — busca vetorial; expõe buscar(query, k)
src/chat.py         — resposta RAG; expõe responder(pergunta)
src/web_search.py   — busca web; expõe buscar_na_web(pergunta) -> (str, list[dict])
scripts/init.sql    — schema de referência
ini.bat             — startup Windows: ativa venv, sobe Docker, abre Chrome, inicia Streamlit
```

## Variáveis de Ambiente (.env)

`LLM_PROVIDER`, `OPENAI_API_KEY`, `GOOGLE_API_KEY` (obrigatória para Gemini e busca web), `DATABASE_URL` (SQLAlchemy format), `COLLECTION_NAME` (default: `documentos_rag`)

## Modelos

| Provider | Embeddings                    | LLM                  |
|----------|-------------------------------|----------------------|
| OpenAI   | text-embedding-3-small        | gpt-5-nano           |
| Gemini   | models/gemini-embedding-001   | gemini-2.5-flash-lite|

Busca web: `gemini-2.5-flash` com `tools=[GoogleSearch()]`

## Interface — 4 Seções

1. **Gerenciar PDFs** — upload 1-5 PDFs, modo adicionar ou substituir tudo, listar/apagar individual ou todos
2. **Busca RAG** — pergunta sobre PDFs, cache automático (`tipo='rag'`), busca vetorial k=10, exibe chunks (score/arquivo/página), download PDF
3. **Busca na Internet** — pergunta livre, cache automático (`tipo='web'`), resposta do Gemini com grounding, exibe fontes como links, download PDF. Custo extra ~$0,035/busca além dos tokens.
4. **Histórico** — todas as consultas RAG e web, badge `[📄 RAG]` / `[🌐 Web]`, filtro por texto, chunks ou fontes expansíveis, download PDF, exclusão por registro

## Banco de Dados

Tabelas LangChain (automáticas):
- `langchain_pg_collection`: `name VARCHAR, cmetadata JSONB, uuid UUID PK`
- `langchain_pg_embedding`: `id VARCHAR PK` (não UUID!), `collection_id UUID`, `embedding vector`, `cmetadata JSONB` (não metadata!)

Tabela de cache (criada pelo app):
```sql
search_cache (id SERIAL PK, pergunta TEXT, resposta TEXT, chunks JSONB, data_consulta TIMESTAMP DEFAULT NOW(), tipo VARCHAR DEFAULT 'rag')
```
- `tipo='rag'` → chunks: `[{"content","score","metadata"}]`
- `tipo='web'` → chunks: `[{"title","url"}]`

## Prompt RAG

```
CONTEXTO: {chunks concatenados}
REGRAS: responda só com base no CONTEXTO; se não estiver no contexto responda "Não tenho informações necessárias para responder sua pergunta."; nunca invente.
PERGUNTA DO USUÁRIO: {pergunta}
```

## Observações importantes

- `langchain_postgres >= 0.0.12` exige `id VARCHAR` (não UUID) — se criar com UUID, dropar e recriar
- `psycopg.connect()` não aceita prefixo `+psycopg` do SQLAlchemy — remover antes de conectar
- `cmetadata` (não `metadata`) é o nome da coluna de metadados do LangChain
- Embeddings de providers diferentes são incompatíveis — ao trocar, reingerir todos os PDFs
- `GOOGLE_API_KEY` é necessária tanto para LLM Gemini quanto para busca web, independentemente do `LLM_PROVIDER`

---

Gere a documentação cobrindo: visão geral, objetivo, tecnologias, estrutura de arquivos, variáveis de ambiente, provedores, dependências (requirements.txt), instalação, uso (ini.bat e manual), detalhamento das 4 seções, schema do banco, arquitetura e fluxo (RAG e web), prompt RAG, documentação do módulo web_search.py com exemplo de uso, tabela de pacotes utilizados, e como remover dados do banco.
