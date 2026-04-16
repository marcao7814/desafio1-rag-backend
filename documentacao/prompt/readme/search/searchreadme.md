# search.py — Busca Vetorial

## O que faz

Conecta ao banco PostgreSQL + pgVector e realiza busca por similaridade semântica, retornando os chunks mais relevantes para uma pergunta.

## Localização

```
src/search.py
```

## Função exportada

```python
from search import buscar

resultados = buscar("Qual é o prazo de entrega?", k=10)
# retorna: list[tuple[Document, float]]
```

## Parâmetros

| Parâmetro | Tipo  | Default | Descrição                              |
|-----------|-------|---------|----------------------------------------|
| `query`   | `str` | —       | Texto da pergunta                      |
| `k`       | `int` | `10`    | Número máximo de chunks a retornar     |

**Retorno:** `list[tuple[Document, float]]` — lista de `(documento, score)` ordenada por relevância. Score menor = mais similar.

## Como usar os resultados

```python
for doc, score in resultados:
    print(score)                          # float — distância vetorial
    print(doc.page_content)               # texto do chunk
    print(doc.metadata["source"])         # caminho do arquivo
    print(doc.metadata["page"])           # número da página
    print(doc.metadata["original_name"])  # nome amigável do PDF
```

## Fluxo interno

```
query
  └─> embeddings.embed_query(query)          → vetor da pergunta
         └─> vectorstore.similarity_search_with_score(query, k=k)
                └─> list[(Document, score)]
```

## Configuração do vectorstore

```python
PGVector(
    embeddings=embeddings,
    collection_name=COLLECTION,   # env COLLECTION_NAME
    connection=DATABASE_URL,      # env DATABASE_URL
    use_jsonb=True,
)
```

O vectorstore é inicializado uma única vez na importação do módulo (nível de módulo), não a cada chamada.

## Modelos de embeddings por provider

| `LLM_PROVIDER` | Modelo                         |
|----------------|--------------------------------|
| `openai`       | `text-embedding-3-small`       |
| `gemini`       | `models/gemini-embedding-001`  |

## Uso standalone (terminal)

```bash
python src/search.py "Qual é o prazo de entrega?"
# Imprime os resultados com score, fonte e página
```

## Uso por outros módulos

| Módulo       | Chamada                         |
|--------------|---------------------------------|
| `chat.py`    | `buscar(pergunta, k=15)`        |
| `frontEnd.py`| `buscar(pergunta, k=10)`        |

## Variáveis de ambiente necessárias

| Variável          | Descrição                                        |
|-------------------|--------------------------------------------------|
| `LLM_PROVIDER`    | `openai` ou `gemini`                             |
| `DATABASE_URL`    | String de conexão PostgreSQL (formato SQLAlchemy)|
| `COLLECTION_NAME` | Nome da coleção (default: `documentos_rag`)      |
| `OPENAI_API_KEY`  | Se `LLM_PROVIDER=openai`                         |
| `GOOGLE_API_KEY`  | Se `LLM_PROVIDER=gemini`                         |

## Dependências

```python
from langchain_postgres import PGVector
from langchain_openai import OpenAIEmbeddings          # se openai
from langchain_google_genai import GoogleGenerativeAIEmbeddings  # se gemini
```
