# Índice de READMEs — Sistema RAG

READMEs individuais por item implementado. Cada arquivo documenta um componente de forma independente e autocontida.

---

## Código-fonte (`src/`)

| Componente | Arquivo | Descrição |
|---|---|---|
| Interface Web | [frontend/frontendreadme.md](frontend/frontendreadme.md) | App Streamlit — 4 seções, session_state, funções |
| Ingestão de PDFs | [ingest/ingestreadme.md](ingest/ingestreadme.md) | PyPDF → chunking → embeddings → pgVector |
| Busca Vetorial | [search/searchreadme.md](search/searchreadme.md) | Similaridade semântica no pgVector |
| Geração de Resposta RAG | [chat/chatreadme.md](chat/chatreadme.md) | Prompt + LLM sobre contexto dos PDFs |
| Busca na Internet | [web_search/web_searchreadme.md](web_search/web_searchreadme.md) | Gemini + Google Search grounding |

## Infraestrutura

| Componente | Arquivo | Descrição |
|---|---|---|
| Banco de Dados | [banco/bancoreadme.md](banco/bancoreadme.md) | PostgreSQL + pgVector — schema, queries, gotchas |
| Cache | [cache/cachereadme.md](cache/cachereadme.md) | Tabela search_cache — RAG e Web |
| Docker | [docker/dockerreadme.md](docker/dockerreadme.md) | docker-compose.yml — container, portas, volume |
| Schema SQL | [init_sql/initsqlreadme.md](init_sql/initsqlreadme.md) | init.sql — extensões, tabelas, pontos críticos |
| Startup | [ini/inireadme.md](ini/inireadme.md) | ini.bat — sequência de inicialização Windows |

---

## Estrutura de pastas

```
readme/
├── INDEX.md                  ← este arquivo
├── frontend/frontendreadme.md
├── ingest/ingestreadme.md
├── search/searchreadme.md
├── chat/chatreadme.md
├── web_search/web_searchreadme.md
├── cache/cachereadme.md
├── banco/bancoreadme.md
├── docker/dockerreadme.md
├── init_sql/initsqlreadme.md
└── ini/inireadme.md
```

## Documentação complementar

| Documento | Localização |
|---|---|
| Documentação técnica completa | [../../documentacao.md](../../documentacao.md) |
| Prompt para gerar a documentação | [../promptinicial.md](../promptinicial.md) |
| Protótipo HTML interativo | [../../prototipo/prototipo.html](../../prototipo/prototipo.html) |
