# ingest.py — Ingestão de PDFs

## O que faz

Carrega um arquivo PDF, divide em chunks de texto, gera embeddings e persiste no banco vetorial PostgreSQL + pgVector.

## Localização

```
src/ingest.py
```

## Função exportada

```python
from ingest import ingerir

n = ingerir("documento.pdf", nome_original="Contrato.pdf", pre_delete=False)
# retorna: int — número de chunks gravados
```

## Parâmetros

| Parâmetro       | Tipo   | Default  | Descrição                                                  |
|-----------------|--------|----------|------------------------------------------------------------|
| `pdf_path`      | `str`  | —        | Caminho do arquivo PDF no disco                            |
| `nome_original` | `str`  | `None`   | Nome amigável gravado nos metadados (exibido no front-end) |
| `pre_delete`    | `bool` | `True`   | `True` = apaga a coleção antes de gravar; `False` = acrescenta |

**Retorno:** `int` — total de chunks gravados.

## Fluxo interno

```
pdf_path
   └─> PyPDFLoader.load()                → páginas
          └─> metadata["original_name"]  → nome_original
          └─> RecursiveCharacterTextSplitter
                chunk_size=1000, chunk_overlap=150
                └─> chunks
                       └─> PGVector.from_documents(
                               pre_delete_collection=pre_delete
                           )             → banco vetorial
```

## Chunking

| Parâmetro       | Valor |
|-----------------|-------|
| `chunk_size`    | 1000  |
| `chunk_overlap` | 150   |
| Splitter        | `RecursiveCharacterTextSplitter` |

## Retry automático (provider Gemini)

O provider Gemini envolve `embed_documents` e `embed_query` com retry exponencial para erros de quota (HTTP 429):

| Parâmetro  | Valor        |
|------------|--------------|
| Min wait   | 25 segundos  |
| Max wait   | 90 segundos  |
| Tentativas | 6            |

## Uso standalone (terminal)

```bash
# Lê PDF_PATH do .env (default: document.pdf)
python src/ingest.py
```

## Uso no frontEnd.py

```python
# frontEnd.py chama ingerir() para cada arquivo uploaded
pre_delete = substituir and (i == 0)   # só apaga na 1ª iteração no modo "substituir"
n = ingerir(tmp_path, nome_original=uf.name, pre_delete=pre_delete)
```

## Metadados gravados por chunk

| Campo           | Origem                              |
|-----------------|-------------------------------------|
| `source`        | Caminho do arquivo (PyPDFLoader)    |
| `page`          | Número da página (PyPDFLoader)      |
| `original_name` | Parâmetro `nome_original`           |

## Modelos de embeddings por provider

| `LLM_PROVIDER` | Modelo                         |
|----------------|--------------------------------|
| `openai`       | `text-embedding-3-small`       |
| `gemini`       | `models/gemini-embedding-001`  |

## Variáveis de ambiente necessárias

| Variável          | Descrição                                       |
|-------------------|-------------------------------------------------|
| `LLM_PROVIDER`    | `openai` ou `gemini`                            |
| `DATABASE_URL`    | String de conexão PostgreSQL (formato SQLAlchemy)|
| `COLLECTION_NAME` | Nome da coleção (default: `documentos_rag`)     |
| `OPENAI_API_KEY`  | Se `LLM_PROVIDER=openai`                        |
| `GOOGLE_API_KEY`  | Se `LLM_PROVIDER=gemini`                        |
| `PDF_PATH`        | Caminho do PDF (apenas uso standalone)          |

## Dependências

```python
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_postgres import PGVector
from tenacity import retry, wait_exponential, stop_after_attempt
```
