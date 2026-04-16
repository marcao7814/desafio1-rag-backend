# Cache — Tabela search_cache

## O que faz

Armazena perguntas e respostas já processadas para evitar chamadas repetidas ao LLM ou ao Google Search. Suporta dois tipos de registro: buscas RAG nos PDFs e buscas na internet.

## Schema

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

## Campo `tipo`

| Valor   | Origem              | Conteúdo de `chunks`                          |
|---------|---------------------|-----------------------------------------------|
| `'rag'` | Busca nos PDFs      | `[{"content", "score", "metadata"}]`          |
| `'web'` | Busca na internet   | `[{"title", "url"}]`                          |

## Campo `chunks` — formato detalhado

### tipo = 'rag'

```json
[
  {
    "content": "texto do chunk recuperado",
    "score": 0.1823,
    "metadata": {
      "source": "/tmp/tmpXXXXXX.pdf",
      "page": 3,
      "original_name": "Contrato2024.pdf"
    }
  }
]
```

### tipo = 'web'

```json
[
  {
    "title": "Título da página web",
    "url": "https://exemplo.com/artigo"
  }
]
```

## Funções no frontEnd.py

### `criar_tabela_cache()`

Cria a tabela se não existir e aplica migrações via `ADD COLUMN IF NOT EXISTS`. Executada automaticamente na inicialização do app.

```python
criar_tabela_cache()
```

### `buscar_cache(pergunta, tipo='rag')`

Busca a pergunta no cache ignorando case e espaços extras, filtrando por tipo.

```python
cache = buscar_cache("Qual o prazo?", tipo="rag")
# retorna: {"resposta": str, "chunks": list, "data_consulta": datetime} ou None
```

### `salvar_cache(pergunta, resposta, resultados=None, tipo='rag')`

Insere um novo registro. Para `tipo='rag'`, serializa objetos `Document`. Para `tipo='web'`, serializa a lista de fontes.

```python
# RAG
salvar_cache(pergunta, resposta, resultados=lista_de_tuples, tipo="rag")

# Web
salvar_cache(pergunta, resposta, resultados=lista_de_fontes, tipo="web")
```

### `listar_cache()`

Retorna todos os registros ordenados do mais recente ao mais antigo, incluindo o campo `tipo`.

```python
registros = listar_cache()
# [{"id", "pergunta", "resposta", "chunks", "data_consulta", "tipo"}, ...]
```

### `deletar_cache_por_id(registro_id)`

Remove um registro pelo id. Retorna quantidade de linhas removidas.

```python
n = deletar_cache_por_id(42)
```

## Busca case-insensitive

A busca normaliza a pergunta para evitar duplicatas:

```sql
WHERE LOWER(TRIM(pergunta)) = LOWER(TRIM(%s))
  AND tipo = %s
ORDER BY data_consulta DESC
LIMIT 1
```

## Fluxo de uso no front-end

```
Usuário digita pergunta
   └─> buscar_cache(pergunta, tipo)
          ├─ hit  → exibe data + opção "usar salvo" ou "refazer"
          │         └─ "usar salvo" → exibe resposta do cache (0 tokens)
          │         └─ "refazer"   → processa normalmente → salvar_cache()
          └─ miss → processa normalmente → salvar_cache()
```

## Migração automática

Na inicialização, `criar_tabela_cache()` executa:

```sql
ALTER TABLE search_cache ADD COLUMN IF NOT EXISTS chunks JSONB;
ALTER TABLE search_cache ADD COLUMN IF NOT EXISTS tipo VARCHAR DEFAULT 'rag';
```

Isso garante que bancos criados em versões anteriores (sem `chunks` ou `tipo`) sejam atualizados automaticamente sem perda de dados.
