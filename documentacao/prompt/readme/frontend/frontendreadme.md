# frontEnd.py — Interface Web Streamlit

## O que faz

Aplicação web principal do sistema RAG. Integra ingestão de PDFs, busca RAG, busca na internet e histórico em uma única interface Streamlit com 4 seções.

## Localização

```
src/frontEnd.py
```

## Como iniciar

```bash
# Forma recomendada (Windows)
ini.bat

# Forma manual
streamlit run src/frontEnd.py
# Acesse: http://localhost:8501
```

## Seções da interface

### Seção 1 — Gerenciar PDFs

| Funcionalidade        | Detalhe                                              |
|-----------------------|------------------------------------------------------|
| Upload                | 1 a 5 arquivos PDF por vez                           |
| Modo Adicionar        | Acrescenta ao banco sem apagar existentes            |
| Modo Substituir tudo  | Apaga toda a coleção antes de ingerir                |
| Listar PDFs           | Tabela com nome amigável de cada arquivo gravado     |
| Apagar selecionado    | Remove todos os chunks do PDF escolhido              |
| Apagar todos          | Requer checkbox de confirmação antes de executar     |

### Seção 2 — Busca / Consulta (RAG)

| Funcionalidade   | Detalhe                                                             |
|------------------|---------------------------------------------------------------------|
| Cache automático | Verifica `search_cache` com `tipo='rag'` antes de chamar o LLM     |
| Cache hit        | Exibe data do cache; oferece usar salvo ou refazer                  |
| Cache miss       | Busca vetorial (k=10) → LLM → salva no cache                       |
| Chunks           | Checkbox para exibir score, arquivo e página de cada chunk          |
| Download PDF     | Gera PDF com pergunta, resposta e chunks via ReportLab              |

### Seção 3 — Busca na Internet (via Gemini)

| Funcionalidade   | Detalhe                                                             |
|------------------|---------------------------------------------------------------------|
| Cache automático | Verifica `search_cache` com `tipo='web'` antes de chamar o Gemini  |
| Cache hit        | Exibe data do cache; oferece usar salvo ou refazer                  |
| Cache miss       | Chama `web_search.buscar_na_web()` → salva resposta + fontes        |
| Fontes           | Exibe links clicáveis das páginas usadas pelo Gemini                |
| Download PDF     | Gera PDF com pergunta e resposta                                    |

### Seção 4 — Histórico de Perguntas e Respostas

| Funcionalidade   | Detalhe                                                              |
|------------------|----------------------------------------------------------------------|
| Listagem         | Todos os registros, ordem decrescente por data                       |
| Badge de tipo    | `[📄 RAG]` ou `[🌐 Web]` em cada registro                           |
| Filtro           | Pesquisa por texto na pergunta e na resposta                         |
| Chunks (RAG)     | Score, arquivo e página de cada chunk                                |
| Fontes (Web)     | Links clicáveis das fontes                                           |
| Download PDF     | PDF com pergunta, resposta e chunks/fontes                           |
| Exclusão         | Apaga o registro do banco pelo id                                    |

## Funções principais

| Função                    | Descrição                                                  |
|---------------------------|------------------------------------------------------------|
| `listar_pdfs_no_banco()`  | Retorna PDFs gravados na coleção vetorial                  |
| `deletar_pdf_do_banco()`  | Remove chunks de um PDF pelo campo `source`                |
| `deletar_todos_pdfs()`    | Remove todos os chunks da coleção                          |
| `ingerir_pdfs()`          | Wrapper para chamar `ingest.ingerir()` por arquivo         |
| `criar_tabela_cache()`    | Cria/migra `search_cache` (roda na inicialização)          |
| `buscar_cache()`          | Busca no cache filtrando por `tipo`                        |
| `salvar_cache()`          | Insere no cache com `tipo` e chunks/fontes serializados    |
| `listar_cache()`          | Retorna todos os registros do cache                        |
| `deletar_cache_por_id()`  | Remove um registro do cache pelo id                        |
| `gerar_pdf_bytes()`       | Gera bytes de PDF com pergunta, resposta e chunks          |

## Gerenciamento de estado (session_state)

O Streamlit reexecuta o script inteiro a cada interação. Para evitar chamadas duplicadas ao banco ou ao LLM, o app usa flags no `st.session_state`:

| Chave                 | Propósito                                         |
|-----------------------|---------------------------------------------------|
| `_pergunta_ativa`     | Detecta mudança de pergunta e limpa estado RAG    |
| `_cache_db`           | Cache da consulta ao banco (evita requery)        |
| `_buscando`           | Desabilita botão RAG durante processamento        |
| `_trigger_busca`      | Dispara processamento no rerender seguinte        |
| `resposta_exibida`    | Resposta RAG atual para exibição persistente      |
| `chunks_exibidos`     | Chunks da nova consulta RAG                       |
| `chunks_cache`        | Chunks recuperados do cache RAG                   |
| `_pergunta_web_ativa` | Detecta mudança de pergunta e limpa estado web    |
| `_cache_web`          | Cache da consulta ao banco para busca web         |
| `_buscando_web`       | Desabilita botão web durante processamento        |
| `_trigger_web`        | Dispara processamento web no rerender seguinte    |
| `_resposta_web`       | Resposta web atual para exibição persistente      |
| `_fontes_web`         | Fontes da busca web atual                         |

## Variáveis de ambiente necessárias

| Variável          | Descrição                                        |
|-------------------|--------------------------------------------------|
| `LLM_PROVIDER`    | `openai` ou `gemini`                             |
| `DATABASE_URL`    | String de conexão PostgreSQL (formato SQLAlchemy)|
| `GOOGLE_API_KEY`  | Obrigatória para Gemini e para busca na internet |
| `OPENAI_API_KEY`  | Se `LLM_PROVIDER=openai`                         |
| `COLLECTION_NAME` | Nome da coleção (default: `documentos_rag`)      |

## Dependências diretas

```python
import psycopg
import streamlit as st
from dotenv import load_dotenv
# Imports lazy (dentro de funções):
from ingest import ingerir
from search import buscar as buscar_vetorial
from chat import responder
from web_search import buscar_na_web
from reportlab.platypus import SimpleDocTemplate, Paragraph, ...
```
