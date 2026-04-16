# Estudo: Verificação de Conteúdo no Sistema RAG

## Objetivo

Verificar se os dados já ingeridos no banco vetorial (pgVector) ou o conteúdo retornado pelo
LLM contêm palavras proibidas/inapropriadas — como "safado", "corno", "inutil" — e, caso
positivo, bloquear ou sinalizar esse conteúdo antes de exibi-lo ao usuário.

---

## Onde a verificação pode ocorrer

O pipeline de dados do sistema segue o fluxo:

```
PDF → ingest.py (chunks) → pgVector → search.py (retrieval) → chat.py (LLM) → frontEnd.py (exibição)
```

Existem **três pontos estratégicos** para aplicar a verificação:

| Ponto | Onde | O que é verificado |
|-------|------|-------------------|
| 1 | Na **ingestão** (`ingest.py`) | Conteúdo dos chunks extraídos do PDF |
| 2 | Na **resposta do LLM** (`chat.py`) | Texto gerado pelo modelo (Gemini/OpenAI) |
| 3 | Na **exibição** (`frontEnd.py`) | Antes de renderizar qualquer texto ao usuário |

---

## 1. Verificação nos Chunks Já Gravados no Banco

### Consulta SQL direta

Os chunks ficam na tabela `langchain_pg_embedding`, coluna `document`. Para localizar
palavras proibidas já gravadas:

```sql
SELECT
    id,
    cmetadata->>'source'        AS arquivo,
    cmetadata->>'original_name' AS nome_amigavel,
    cmetadata->>'page'          AS pagina,
    document
FROM langchain_pg_embedding
WHERE collection_id = (
    SELECT uuid FROM langchain_pg_collection WHERE name = 'documentos_rag'
)
AND (
    LOWER(document) LIKE '%safado%'
    OR LOWER(document) LIKE '%corno%'
    OR LOWER(document) LIKE '%inutil%'
);
```

> **Nota:** A coluna que guarda o texto do chunk no schema do `langchain_postgres` é
> `document` (tipo TEXT). A coluna `cmetadata` guarda os metadados em JSONB.

### Script Python de auditoria

```python
# src/auditar_conteudo.py
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
COLLECTION   = os.getenv("COLLECTION_NAME", "documentos_rag")

# Converte URL para formato aceito pelo psycopg
PSYCOPG_URL = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://") \
                           .replace("postgres+psycopg://",  "postgresql://")

PALAVRAS_PROIBIDAS = ["safado", "corno", "inutil", "idiota", "burro"]


def auditar_banco() -> list[dict]:
    """
    Varre todos os chunks do banco e retorna os que contêm palavras proibidas.
    """
    condicoes = " OR ".join(
        f"LOWER(document) LIKE '%{p}%'" for p in PALAVRAS_PROIBIDAS
    )
    sql = f"""
        SELECT
            id,
            cmetadata->>'source'        AS arquivo,
            cmetadata->>'original_name' AS nome,
            cmetadata->>'page'          AS pagina,
            document
        FROM langchain_pg_embedding
        WHERE collection_id = (
            SELECT uuid FROM langchain_pg_collection WHERE name = %s
        )
        AND ({condicoes})
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (COLLECTION,))
            rows = cur.fetchall()

    return [
        {
            "id":      r[0],
            "arquivo": r[1],
            "nome":    r[2],
            "pagina":  r[3],
            "trecho":  r[4][:300],
        }
        for r in rows
    ]


if __name__ == "__main__":
    ocorrencias = auditar_banco()
    if not ocorrencias:
        print("Nenhuma palavra proibida encontrada no banco.")
    else:
        print(f"{len(ocorrencias)} chunk(s) com conteúdo proibido:\n")
        for item in ocorrencias:
            print(f"  Arquivo : {item['nome'] or item['arquivo']}")
            print(f"  Página  : {item['pagina']}")
            print(f"  Trecho  : {item['trecho'][:150]}...")
            print()
```

---

## 2. Filtro na Ingestão (prevenir que entrem no banco)

Em `ingest.py`, após o chunking e antes de gravar no pgVector, filtrar os chunks:

```python
# Dentro da função ingerir(), após: chunks = splitter.split_documents(pages)

PALAVRAS_PROIBIDAS = {"safado", "corno", "inutil"}

def _tem_palavra_proibida(texto: str) -> bool:
    texto_lower = texto.lower()
    return any(p in texto_lower for p in PALAVRAS_PROIBIDAS)

chunks_limpos = [c for c in chunks if not _tem_palavra_proibida(c.page_content)]

rejeitados = len(chunks) - len(chunks_limpos)
if rejeitados:
    print(f"  AVISO: {rejeitados} chunk(s) removidos por conteúdo proibido.")

chunks = chunks_limpos  # substitui a lista original
```

**Ponto positivo:** impede que conteúdo inadequado chegue ao banco.  
**Ponto de atenção:** chunks que contêm a palavra _junto com conteúdo relevante_ serão
perdidos. Avaliar se o melhor é rejeitar ou somente registrar em log.

---

## 3. Filtro na Resposta do LLM

Em `chat.py`, na função `responder()`, aplicar o filtro após receber a resposta gerada:

```python
PALAVRAS_PROIBIDAS = {"safado", "corno", "inutil"}

def _contem_palavra_proibida(texto: str) -> bool:
    texto_lower = texto.lower()
    return any(p in texto_lower for p in PALAVRAS_PROIBIDAS)

def responder(pergunta: str) -> str:
    resultados = buscar(pergunta, k=15)

    if not resultados:
        return "Não tenho informações necessárias para responder sua pergunta."

    contexto = "\n\n---\n\n".join(doc.page_content for doc, _ in resultados)
    prompt   = PROMPT_TEMPLATE.format(contexto=contexto, pergunta=pergunta)
    resposta = llm.invoke(prompt).content

    # Verificação de conteúdo proibido
    if _contem_palavra_proibida(resposta):
        return "Resposta bloqueada: conteúdo inapropriado detectado."

    return resposta
```

---

## 4. Filtro na Pergunta do Usuário

Antes de executar a busca, verificar se a própria pergunta contém palavras proibidas:

```python
# frontEnd.py — dentro da seção de Busca, antes de chamar buscar_vetorial()

PALAVRAS_PROIBIDAS = {"safado", "corno", "inutil"}

def _pergunta_valida(texto: str) -> bool:
    texto_lower = texto.lower()
    return not any(p in texto_lower for p in PALAVRAS_PROIBIDAS)

# Uso:
if not _pergunta_valida(pergunta):
    st.error("Sua pergunta contém termos não permitidos. Por favor, reformule.")
    st.stop()
```

---

## 5. Centralizar as Palavras Proibidas

Para não duplicar a lista em vários arquivos, criar um módulo dedicado:

```python
# src/content_guard.py

"""
content_guard.py — Verificação centralizada de conteúdo proibido.
"""

PALAVRAS_PROIBIDAS: set[str] = {
    "safado",
    "corno",
    "inutil",
    # adicione mais conforme necessário
}


def contem_proibido(texto: str) -> bool:
    """Retorna True se o texto contiver ao menos uma palavra proibida."""
    texto_lower = texto.lower()
    return any(palavra in texto_lower for palavra in PALAVRAS_PROIBIDAS)


def palavras_encontradas(texto: str) -> list[str]:
    """Retorna lista das palavras proibidas encontradas no texto."""
    texto_lower = texto.lower()
    return [p for p in PALAVRAS_PROIBIDAS if p in texto_lower]
```

Importação nos demais módulos:

```python
from content_guard import contem_proibido, palavras_encontradas
```

---

## 6. Diagrama do Fluxo com Verificações

```
Usuário digita pergunta
        │
        ▼
┌───────────────────────┐
│  Verificar pergunta   │ ← content_guard.contem_proibido()
│  (frontEnd.py)        │
└──────────┬────────────┘
           │ OK
           ▼
┌───────────────────────┐
│  Busca vetorial       │
│  (search.py)          │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│  LLM gera resposta    │
│  (chat.py)            │
└──────────┬────────────┘
           │
           ▼
┌───────────────────────┐
│  Verificar resposta   │ ← content_guard.contem_proibido()
│  (chat.py)            │
└──────────┬────────────┘
           │ OK
           ▼
      Exibe ao usuário


Na ingestão:
PDF → chunks → [filtro content_guard] → apenas chunks limpos → pgVector
```

---

## 7. Considerações Importantes

### Falsos positivos
Palavras como "inutil" podem aparecer em contextos legítimos: "produto inútil para o
descarte" em documentos técnicos. Avaliar o uso de verificação por **contexto** (frases)
em vez de palavras isoladas.

### Variações ortográficas
Tratar acentuação e variações:
```python
import unicodedata

def normalizar(texto: str) -> str:
    """Remove acentos e converte para minúsculas."""
    return unicodedata.normalize("NFD", texto.lower()).encode("ascii", "ignore").decode()

# "inútil" → "inutil", "safadão" → "safadao"
```

### Log de ocorrências
Registrar no banco (tabela `content_violations`) cada detecção:
```sql
CREATE TABLE IF NOT EXISTS content_violations (
    id          SERIAL PRIMARY KEY,
    tipo        VARCHAR(20),   -- 'pergunta', 'chunk', 'resposta'
    texto       TEXT,
    palavras    TEXT[],
    detectado   TIMESTAMP DEFAULT NOW()
);
```

### Lista configurável
Em vez de hardcodar no código, carregar de variável de ambiente ou arquivo:
```
# .env
PALAVRAS_PROIBIDAS=safado,corno,inutil,idiota
```
```python
PALAVRAS_PROIBIDAS = set(os.getenv("PALAVRAS_PROIBIDAS", "").split(","))
```

---

## Resumo das Ações

| # | Ação | Arquivo | Prioridade |
|---|------|---------|-----------|
| 1 | Criar `src/content_guard.py` com lista centralizada | novo arquivo | Alta |
| 2 | Filtrar pergunta antes da busca | `frontEnd.py` | Alta |
| 3 | Filtrar resposta do LLM | `chat.py` | Alta |
| 4 | Filtrar chunks na ingestão | `ingest.py` | Média |
| 5 | Script de auditoria dos dados já gravados | `src/auditar_conteudo.py` | Média |
| 6 | Normalizar acentos na comparação | `content_guard.py` | Baixa |
| 7 | Tabela de log de violações no banco | `init.sql` | Baixa |
