# Documentação Técnica - Sistema RAG

## Visão Geral

Sistema de Retrieval-Augmented Generation (RAG) que ingere PDFs, armazena embeddings no PostgreSQL com pgVector via Docker e responde perguntas através de uma interface web Streamlit usando Google Gemini ou OpenAI. Inclui também busca na internet em tempo real via Gemini com Google Search grounding.

---

## Objetivo

- **Ingestão:** Carregar até 5 PDFs pelo navegador, dividir em chunks, gerar embeddings e salvar no PostgreSQL com extensão pgVector.
- **Busca RAG:** Fazer perguntas via interface web e receber respostas baseadas apenas no conteúdo dos PDFs, com cache automático para evitar chamadas repetidas ao LLM.
- **Busca na Internet:** Fazer perguntas que são respondidas pelo Gemini com acesso ao Google Search em tempo real, com cache automático.
- **Histórico:** Consultar, filtrar e baixar em PDF todas as perguntas e respostas anteriores (RAG e web).

---

## Tecnologias

| Categoria             | Tecnologia                        |
|-----------------------|-----------------------------------|
| Linguagem             | Python 3.11+                      |
| Interface Web         | Streamlit                         |
| Framework LLM         | LangChain                         |
| Banco de Dados        | PostgreSQL + pgVector             |
| Execução do Banco     | Docker & Docker Compose           |
| Provedores LLM/Embed  | OpenAI ou Google Gemini           |
| Busca na Internet     | Google Search grounding (Gemini)  |
| SDK Gemini direto     | google-genai                      |
| Geração de PDF        | ReportLab                         |

---

## Estrutura do Projeto

```
├── docker-compose.yml    # PostgreSQL + pgVector
├── requirements.txt      # Dependências Python
├── .env.example          # Template de variáveis de ambiente
├── .env                  # Suas credenciais (não versionar)
├── document.pdf          # PDF de exemplo
├── ini.bat               # Script de inicialização Windows
├── src/
│   ├── frontEnd.py       # Interface web Streamlit (app principal)
│   ├── ingest.py         # Ingestão de PDFs; expõe ingerir()
│   ├── search.py         # Busca por similaridade vetorial
│   ├── chat.py           # Geração de resposta com LLM
│   └── web_search.py     # Busca na internet via Gemini + Google Search
├── scripts/
│   └── init.sql          # Schema de referência do banco
└── documentacao/
    ├── documentacao.md   # Esta documentação
    ├── estudofront.md    # Estudo técnico do frontEnd.py
    └── tarefasfront.md   # Lista de tarefas de implementação
```

---

## Variáveis de Ambiente (.env)

| Variável           | Obrigatória | Descrição                                              |
|--------------------|-------------|--------------------------------------------------------|
| `LLM_PROVIDER`     | Sim         | `openai` ou `gemini`                                   |
| `OPENAI_API_KEY`   | Condicional | Chave OpenAI (se `LLM_PROVIDER=openai`)                |
| `GOOGLE_API_KEY`   | Sim         | Chave Google AI Studio — usada pelo LLM Gemini e pela busca na internet |
| `DATABASE_URL`     | Sim         | String de conexão PostgreSQL (formato SQLAlchemy)      |
| `COLLECTION_NAME`  | Não         | Nome da coleção vetorial (default: `documentos_rag`)   |
| `PDF_PATH`         | Não         | Caminho do PDF para ingestão standalone                |
| `EMBEDDING_MODEL`  | Não         | Modelo de embeddings (default por provider)            |
| `LLM_MODEL`        | Não         | Modelo LLM (default por provider)                      |

> `GOOGLE_API_KEY` é obrigatória sempre que `LLM_PROVIDER=gemini` **ou** quando a Busca na Internet for usada (independente do provider RAG).

---

## Provedores de LLM e Embeddings

### OpenAI

- Crie uma API Key em [platform.openai.com](https://platform.openai.com)
- Modelo de embeddings: `text-embedding-3-small`
- Modelo de LLM: `gpt-5-nano`

### Gemini (Google)

- Crie uma API Key em [aistudio.google.com](https://aistudio.google.com)
- Modelo de embeddings: `models/gemini-embedding-001`
- Modelo de LLM: `gemini-2.5-flash-lite`
- Modelo de busca web: `gemini-2.5-flash` (via `google-genai` SDK, com Google Search grounding)

> Embeddings gerados por provedores diferentes são incompatíveis. Ao trocar de provedor, reingerir os PDFs.

---

## Dependências (requirements.txt)

```
# LangChain
langchain>=0.3.0,<1.0.0
langchain-core>=0.3.0,<0.4.0
langchain-text-splitters>=0.3.0,<1.0.0
langchain-community>=0.3.0,<1.0.0

# Provedores LLM e Embeddings
langchain-openai>=0.2.0,<1.0.0
langchain-google-genai>=2.0.0,<3.0.0
google-genai>=1.0.0          # SDK direto para busca web com grounding

# Banco vetorial (PostgreSQL + pgVector)
langchain-postgres>=0.0.12
psycopg[binary]>=3.1.0
pgvector>=0.3.0

# PDF
pypdf>=4.0.0
reportlab>=4.0.0

# Variáveis de ambiente
python-dotenv>=1.0.0

# Front-end web
streamlit>=1.35.0
```

---

## Instalação

```bash
# 1. Criar e ativar ambiente virtual
python -m venv venv
venv\Scripts\activate        # Windows
# ou
source venv/bin/activate     # Linux/macOS

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar variáveis de ambiente
cp .env.example .env
# Edite o .env com suas credenciais

# 4. Iniciar o banco de dados
docker compose up -d
```

---

## Uso

### Inicialização rápida (Windows)

```
ini.bat
```

O script `ini.bat`:
1. Ativa o ambiente virtual
2. Verifica/inicia o container Docker `rag_postgres`
3. Verifica se Streamlit está instalado
4. Abre o Chrome em `http://localhost:8501` após 4 segundos
5. Inicia o Streamlit em modo headless

### Uso manual

```bash
streamlit run src/frontEnd.py
```

---

## Interface Web — Seções

### Seção 1 — Gerenciar PDFs

- **Upload:** Selecione de 1 a 5 arquivos PDF simultaneamente.
- **Modo de ingestão:**
  - `Adicionar aos existentes` — acrescenta ao banco sem apagar o que já existe.
  - `Substituir tudo` — apaga toda a coleção antes de ingerir os novos PDFs.
- **PDFs no banco:** Tabela com todos os arquivos gravados, com opção de apagar individualmente ou todos de uma vez.

### Seção 2 — Busca / Consulta (RAG)

- Digite uma pergunta sobre os documentos ingeridos.
- O sistema verifica automaticamente se a pergunta já foi respondida (cache `tipo='rag'`).
  - **Cache hit:** exibe a data do cache e oferece opção de usar a resposta salva ou refazer (gera tokens).
  - **Cache miss:** realiza busca vetorial (k=10) + chamada ao LLM, salva automaticamente no cache.
- Exibe os chunks recuperados com score, arquivo e página.
- Botão para baixar a resposta + chunks em PDF.

### Seção 3 — Busca na Internet (via Gemini)

- Digite qualquer pergunta para buscar na internet em tempo real.
- Usa o modelo `gemini-2.5-flash` com **Google Search grounding** — o Gemini consulta o Google e baseia a resposta em páginas reais.
- O sistema verifica automaticamente se a pergunta já foi respondida (cache `tipo='web'`).
  - **Cache hit:** exibe a data do cache e oferece opção de usar a resposta salva ou refazer (gera tokens + custo de busca).
  - **Cache miss:** chama o Gemini, salva a resposta e as fontes no cache.
- Exibe as fontes utilizadas como links clicáveis.
- Botão para baixar a resposta em PDF.

> **Custo:** além dos tokens (entrada/saída), o Google Search grounding cobra ~$0,035 por consulta de busca. O cache elimina esse custo em perguntas repetidas.

### Seção 4 — Histórico de Perguntas e Respostas

- Lista todas as consultas salvas (RAG e web), ordenadas da mais recente à mais antiga.
- Cada registro exibe um badge de tipo: `[📄 RAG]` ou `[🌐 Web]`.
- Filtro por texto (pesquisa na pergunta e na resposta).
- Cada registro expandível com:
  - Pergunta e resposta
  - **RAG:** chunks utilizados com score, arquivo e página
  - **Web:** fontes como links clicáveis
  - Botão de download PDF e botão de exclusão

---

## Schema do Banco de Dados

### Tabelas do LangChain (criadas automaticamente)

```sql
langchain_pg_collection (
    name      VARCHAR,
    cmetadata JSONB,
    uuid      UUID PRIMARY KEY
)

langchain_pg_embedding (
    id            VARCHAR PRIMARY KEY,   -- VARCHAR, não UUID!
    collection_id UUID REFERENCES langchain_pg_collection(uuid),
    embedding     vector,
    document      VARCHAR,
    cmetadata     JSONB                  -- cmetadata, não metadata!
)
```

> **Atenção:** `langchain_postgres >= 0.0.12` usa `id VARCHAR` (não UUID). O campo de metadados é `cmetadata` (não `metadata`).

### Tabela de cache (criada pelo app)

```sql
search_cache (
    id            SERIAL PRIMARY KEY,
    pergunta      TEXT NOT NULL,
    resposta      TEXT NOT NULL,
    chunks        JSONB,              -- chunks RAG ou fontes web (lista JSON)
    data_consulta TIMESTAMP DEFAULT NOW(),
    tipo          VARCHAR DEFAULT 'rag'  -- 'rag' ou 'web'
)
```

**Conteúdo do campo `chunks` por tipo:**

- `tipo = 'rag'` → lista de objetos `{"content", "score", "metadata"}`
- `tipo = 'web'` → lista de objetos `{"title", "url"}`

---

## Arquitetura e Fluxo

```
+------------------+     +-------------------------+     +------------------+
|   PDFs           |     |   PostgreSQL + pgVector |     |   LLM            |
|   (upload web)   |---->|   (embeddings / chunks) |---->|   OpenAI/Gemini  |
+------------------+     +-------------------------+     +------------------+
                                    |
                         +---------------------+
                         |   search_cache      |
                         |   tipo: rag | web   |
                         +---------------------+
                                    ^
+------------------+               |
|   Internet       |               |
|   (Google Search)|----> Gemini --+
+------------------+    grounding
```

**Fluxo RAG:**
1. Pergunta → verificar cache (`tipo='rag'`) → se hit: retornar resposta salva
2. Se miss: Embedding → Busca Vetorial (k=10) → Contexto → LLM → Resposta → Salvar cache

**Fluxo Busca Web:**
1. Pergunta → verificar cache (`tipo='web'`) → se hit: retornar resposta salva
2. Se miss: `gemini-2.5-flash` + Google Search grounding → Resposta + Fontes → Salvar cache

---

## Prompt (RAG)

```
CONTEXTO:
{resultados concatenados do banco de dados}

REGRAS:
- Responda somente com base no CONTEXTO.
- Se a informação não estiver explicitamente no CONTEXTO, responda:
  "Não tenho informações necessárias para responder sua pergunta."
- Nunca invente ou use conhecimento externo.
- Nunca produza opiniões ou interpretações além do que está escrito.

PERGUNTA DO USUÁRIO:
{pergunta do usuário}

RESPONDA A "PERGUNTA DO USUÁRIO"
```

---

## Módulo web_search.py

```python
from web_search import buscar_na_web

resposta, fontes = buscar_na_web("Qual é a cotação do dólar hoje?")
# resposta: str com a resposta gerada pelo Gemini
# fontes:   list[dict] com {"title": ..., "url": ...}
```

- Usa `google-genai` SDK diretamente (não LangChain)
- Modelo: `gemini-2.5-flash` com `tools=[GoogleSearch()]`
- Extrai fontes do `grounding_metadata.grounding_chunks`
- Requer `GOOGLE_API_KEY` no `.env`

---

## Pacotes Utilizados

| Finalidade              | Import                                                                  |
|-------------------------|-------------------------------------------------------------------------|
| Carregamento PDF        | `from langchain_community.document_loaders import PyPDFLoader`          |
| Chunking                | `from langchain_text_splitters import RecursiveCharacterTextSplitter`   |
| Embeddings OpenAI       | `from langchain_openai import OpenAIEmbeddings`                         |
| Embeddings Gemini       | `from langchain_google_genai import GoogleGenerativeAIEmbeddings`       |
| Banco vetorial          | `from langchain_postgres import PGVector`                               |
| Busca                   | `vectorstore.similarity_search_with_score(query, k=10)`                 |
| LLM OpenAI              | `from langchain_openai import ChatOpenAI`                               |
| LLM Gemini              | `from langchain_google_genai import ChatGoogleGenerativeAI`             |
| Busca web (Gemini)      | `from google import genai` + `from google.genai import types`           |
| Conexão direta DB       | `import psycopg`                                                        |
| Geração de PDF          | `from reportlab.platypus import SimpleDocTemplate, Paragraph, ...`      |

---

## Remover dados do banco

```bash
docker compose down -v   # Remove container e volume (apaga todos os dados)
docker compose up -d     # Reinicia limpo
```
