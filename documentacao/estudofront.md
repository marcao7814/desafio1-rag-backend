# Estudo: Front-End Streamlit — frontEnd.py

## Objetivo

`src/frontEnd.py` é a interface web do sistema RAG. Substitui a interação via CLI, oferecendo:

1. **Seção 1 — Gerenciamento de PDFs** — upload de 1 a 5 arquivos, visualização dos gravados, exclusão individual ou total, dois modos de ingestão.
2. **Seção 2 — Busca inteligente** — cache automático de perguntas com opção de reutilizar ou refazer, botão desabilitável durante processamento, download de resposta em PDF.
3. **Seção 3 — Histórico** — listagem de todas as consultas salvas, filtro por texto, download PDF e exclusão individual.

---

## Dependências extras

```bash
pip install streamlit reportlab
```

> `psycopg[binary]`, `langchain_postgres`, `langchain_google_genai` já estão em `requirements.txt`.

---

## Estrutura do frontEnd.py

```
frontEnd.py
├── Imports e configuração (json, os, sys, tempfile, pathlib, psycopg, streamlit, dotenv)
├── Variáveis de ambiente (DATABASE_URL, COLLECTION, LLM_PROVIDER, PSYCOPG_URL)
│
├── Helpers — Embeddings
│   └── _get_embeddings()  ← @st.cache_resource
│
├── Helpers — Banco de dados (PDFs)
│   ├── listar_pdfs_no_banco() -> list[dict]
│   ├── deletar_pdf_do_banco(source) -> int
│   ├── deletar_todos_pdfs() -> int
│   └── ingerir_pdfs(uploaded_files, substituir) -> int
│
├── Helpers — Cache de perguntas (tabela search_cache)
│   ├── criar_tabela_cache()
│   ├── buscar_cache(pergunta) -> dict | None
│   ├── salvar_cache(pergunta, resposta, resultados)
│   ├── listar_cache() -> list[dict]
│   └── deletar_cache_por_id(id) -> int
│
├── Helpers — Geração de PDF
│   └── gerar_pdf_bytes(pergunta, resposta, chunks) -> bytes
│
├── APP — Configuração (st.set_page_config, validação, criar_tabela_cache)
│
├── Seção 1 — st.expander("📂 Gerenciar PDFs")
│   ├── st.file_uploader (1-5 PDFs)
│   ├── Rádio: "Adicionar aos existentes" | "Substituir tudo"
│   ├── Botão "⬆️ Ingerir PDFs"
│   ├── st.dataframe com PDFs gravados
│   ├── st.selectbox + Botão "🗑️ Apagar selecionado"
│   └── Checkbox + Botão "🗑️ Apagar todos os PDFs"
│
├── Seção 2 — st.expander("🔍 Busca / Consulta")
│   ├── st.text_input("Sua pergunta")
│   ├── Limpeza de estado ao mudar a pergunta (_pergunta_ativa)
│   ├── Consulta ao cache (uma vez por pergunta, via _cache_db)
│   ├── st.radio: "Usar resposta salva" | "Refazer consulta (gera tokens)"
│   ├── Botão "🔍 Buscar" (desabilitado durante processamento via _buscando)
│   ├── Processamento com flags _trigger_busca / _buscando
│   ├── Exibição persistente da resposta (session_state["resposta_exibida"])
│   ├── Expander de chunks recuperados (Document objects ou dicts do cache)
│   └── Botão "📄 Baixar PDF desta resposta"
│
└── Seção 3 — st.expander("📋 Histórico de Perguntas e Respostas")
    ├── listar_cache()
    ├── st.text_input para filtro
    └── Para cada registro: pergunta, resposta, chunks, "📄 Baixar PDF", "🗑️ Apagar"
```

---

## Variáveis de Ambiente e PSYCOPG_URL

```python
DATABASE_URL = os.getenv("DATABASE_URL", "")   # postgresql+psycopg://user:pass@host/db
COLLECTION   = os.getenv("COLLECTION_NAME", "documentos_rag")

# psycopg.connect() não aceita o prefixo "+psycopg" do SQLAlchemy
PSYCOPG_URL = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://") \
                           .replace("postgres+psycopg://",  "postgresql://")
```

> `PGVector` (LangChain) usa `DATABASE_URL` com `+psycopg`.
> `psycopg.connect()` usa `PSYCOPG_URL` sem `+psycopg`.

---

## Seção 1 — Gerenciar PDFs

### Listar PDFs no banco

```python
def listar_pdfs_no_banco() -> list[dict]:
    sql = """
        SELECT DISTINCT
            cmetadata->>'source'        AS source,
            cmetadata->>'original_name' AS nome
        FROM langchain_pg_embedding
        WHERE collection_id = (
            SELECT uuid FROM langchain_pg_collection WHERE name = %s
        )
        ORDER BY source
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (COLLECTION,))
            rows = cur.fetchall()
    return [
        {"source": r[0], "nome": r[1] or os.path.basename(r[0] or "")}
        for r in rows if r[0]
    ]
```

> **Nota:** A coluna de metadados é `cmetadata` (não `metadata`). O campo `original_name` é gravado pelo `ingest.py` para exibição amigável.

### Deletar PDF específico

```python
def deletar_pdf_do_banco(source: str) -> int:
    sql = """
        DELETE FROM langchain_pg_embedding
        WHERE collection_id = (SELECT uuid FROM langchain_pg_collection WHERE name = %s)
        AND cmetadata->>'source' = %s
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (COLLECTION, source))
            deletados = cur.rowcount
        conn.commit()
    return deletados
```

### Deletar todos os PDFs

```python
def deletar_todos_pdfs() -> int:
    sql = """
        DELETE FROM langchain_pg_embedding
        WHERE collection_id = (SELECT uuid FROM langchain_pg_collection WHERE name = %s)
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (COLLECTION,))
            deletados = cur.rowcount
        conn.commit()
    return deletados
```

### Ingestão via front-end

```python
def ingerir_pdfs(uploaded_files: list, substituir: bool = False) -> int:
    from ingest import ingerir  # reutiliza a lógica de ingest.py

    total = 0
    for i, uf in enumerate(uploaded_files):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uf.read())
            tmp_path = tmp.name
        try:
            pre_delete = substituir and (i == 0)  # só apaga na primeira iteração
            n = ingerir(tmp_path, nome_original=uf.name, pre_delete=pre_delete)
            total += n
        finally:
            os.unlink(tmp_path)
    return total
```

> - `substituir=True`: `pre_delete=True` apenas no primeiro arquivo (apaga coleção uma vez).
> - `substituir=False`: `pre_delete=False` em todos (adiciona sem apagar).
> - O arquivo temporário é sempre removido no bloco `finally`.

### UI da Seção 1

```python
with st.expander("📂 Gerenciar PDFs", expanded=True):
    arquivos = st.file_uploader(
        "Selecione de 1 a 5 PDFs", type=["pdf"],
        accept_multiple_files=True, key="uploader",
    )
    if arquivos and len(arquivos) > 5:
        st.warning("Máximo de 5 arquivos por vez. Somente os 5 primeiros serão processados.")
        arquivos = arquivos[:5]

    modo = st.radio("Modo de ingestão",
                    ["Adicionar aos existentes", "Substituir tudo"], horizontal=True)

    if st.button("⬆️ Ingerir PDFs", disabled=not arquivos, type="primary"):
        with st.spinner(f"Processando {len(arquivos)} arquivo(s)..."):
            n = ingerir_pdfs(arquivos, substituir=(modo == "Substituir tudo"))
        st.success(f"✅ {n} chunk(s) gravados com sucesso.")
        st.rerun()

    # Lista dos gravados
    pdfs = listar_pdfs_no_banco()
    if not pdfs:
        st.info("Nenhum PDF gravado ainda.")
    else:
        col_tab, col_del = st.columns([3, 2])
        with col_tab:
            st.dataframe({"PDF gravado": [p["nome"] for p in pdfs]},
                         use_container_width=True, hide_index=True)
        with col_del:
            opcoes = {p["nome"]: p["source"] for p in pdfs}
            nome_sel = st.selectbox("Selecione para apagar", list(opcoes.keys()))
            if st.button("🗑️ Apagar selecionado", type="secondary"):
                n = deletar_pdf_do_banco(opcoes[nome_sel])
                st.success(f"✅ {n} chunk(s) de '{nome_sel}' removidos.")
                st.rerun()

            confirmar = st.checkbox("Confirmar exclusão de **todos** os PDFs")
            if st.button("🗑️ Apagar todos os PDFs", type="secondary", disabled=not confirmar):
                n = deletar_todos_pdfs()
                st.success(f"✅ {n} chunk(s) removidos. Banco vazio.")
                st.rerun()
```

---

## Seção 2 — Busca com Cache

### Schema da tabela search_cache

```sql
CREATE TABLE IF NOT EXISTS search_cache (
    id            SERIAL PRIMARY KEY,
    pergunta      TEXT NOT NULL,
    resposta      TEXT NOT NULL,
    chunks        JSONB,          -- chunks recuperados serializados
    data_consulta TIMESTAMP DEFAULT NOW()
)
```

### Criar tabela (com migração)

```python
def criar_tabela_cache():
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS search_cache (
                id SERIAL PRIMARY KEY, pergunta TEXT NOT NULL,
                resposta TEXT NOT NULL, chunks JSONB,
                data_consulta TIMESTAMP DEFAULT NOW()
            )""")
            # Migração: adiciona coluna chunks em tabelas já existentes
            cur.execute("ALTER TABLE search_cache ADD COLUMN IF NOT EXISTS chunks JSONB")
        conn.commit()
```

### Buscar no cache

```python
def buscar_cache(pergunta: str) -> dict | None:
    sql = """
        SELECT resposta, chunks, data_consulta
        FROM search_cache
        WHERE LOWER(TRIM(pergunta)) = LOWER(TRIM(%s))
        ORDER BY data_consulta DESC LIMIT 1
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (pergunta,))
            row = cur.fetchone()
    if row:
        return {"resposta": row[0], "chunks": row[1] or [], "data_consulta": row[2]}
    return None
```

### Salvar no cache (com chunks)

```python
def salvar_cache(pergunta: str, resposta: str, resultados: list = None):
    chunks_json = None
    if resultados:
        chunks_json = json.dumps([
            {"content": doc.page_content, "score": float(score), "metadata": doc.metadata}
            for doc, score in resultados
        ], ensure_ascii=False)
    sql = "INSERT INTO search_cache (pergunta, resposta, chunks) VALUES (%s, %s, %s)"
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (pergunta, resposta, chunks_json))
        conn.commit()
```

> `resultados` é `list[(Document, float)]` — retorno direto de `buscar_vetorial()`.
> Os chunks são serializados para JSONB com `{"content", "score", "metadata"}`.

### Padrão de botão desabilitável durante processamento

O Streamlit re-executa o script inteiro a cada interação. Para desabilitar o botão enquanto processa:

```python
# Render 1: botão clicado → seta flags → rerun
if st.button("🔍 Buscar", type="primary",
             disabled=st.session_state.get("_buscando", False)):
    st.session_state["_buscando"] = True
    st.session_state["_trigger_busca"] = True
    st.rerun()

# Render 2: botão aparece desabilitado → processamento ocorre → rerun
if st.session_state.get("_trigger_busca"):
    st.session_state.pop("_trigger_busca")
    # ... lógica de busca ...
    st.session_state["_buscando"] = False
    st.rerun()

# Render 3: botão re-habilitado, resultado visível
```

### Cache consistente por pergunta

Para evitar múltiplas queries ao banco em diferentes rerenders da mesma pergunta:

```python
# Limpa estado ao mudar pergunta
if pergunta != st.session_state.get("_pergunta_ativa", ""):
    for k in ["resposta_exibida", "chunks_exibidos", "chunks_cache",
              "fonte_resposta", "_cache_db", "_buscando", ...]:
        st.session_state.pop(k, None)
    st.session_state["_pergunta_ativa"] = pergunta

# Consulta o banco apenas uma vez por pergunta
if "_cache_db" not in st.session_state:
    st.session_state["_cache_db"] = buscar_cache(pergunta)  # pode ser None

cache = st.session_state["_cache_db"]
```

### Exibição persistente da resposta

A resposta deve ser exibida **fora** do bloco `if st.button()`, pois dentro desaparece no próximo rerender:

```python
# DENTRO do bloco de processamento: salva no session_state
st.session_state["resposta_exibida"] = resposta
st.session_state["fonte_resposta"] = "nova"
st.session_state["chunks_exibidos"] = resultados

# FORA do bloco do botão: exibe persistentemente
if "resposta_exibida" in st.session_state:
    st.markdown("### Resposta")
    st.write(st.session_state["resposta_exibida"])
```

---

## Seção 3 — Histórico

### Listar cache

```python
def listar_cache() -> list[dict]:
    sql = "SELECT id, pergunta, resposta, chunks, data_consulta FROM search_cache ORDER BY data_consulta DESC"
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [
        {"id": r[0], "pergunta": r[1], "resposta": r[2],
         "chunks": r[3] or [], "data_consulta": r[4]}
        for r in rows
    ]
```

### Deletar registro do cache

```python
def deletar_cache_por_id(registro_id: int) -> int:
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM search_cache WHERE id = %s", (registro_id,))
            deletados = cur.rowcount
        conn.commit()
    return deletados
```

---

## Geração de PDF

```python
def gerar_pdf_bytes(pergunta: str, resposta: str, chunks: list) -> bytes:
    """
    chunks aceita:
      - list[(Document, float)]  — resultado direto da busca vetorial
      - list[dict]               — formato serializado do cache {"content","score","metadata"}
    """
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    # ... configuração de estilos ...
    story = []
    # Título, data, pergunta, resposta (linha a linha), chunks (score + arquivo + página + 500 chars)
    doc_pdf.build(story)
    return buffer.getvalue()
```

Características do PDF gerado:
- Título: "RAG — Resposta Gerada" + data/hora
- Seção "Pergunta"
- Seção "Resposta" (linha por linha, com espaçamento)
- Seção "Chunks Utilizados (N)" — para cada chunk: score, arquivo, página, até 500 chars do conteúdo
- Escapa `&` → `&amp;` e `<` → `&lt;` para evitar erros de markup do ReportLab

---

## Diagrama de Fluxo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          frontEnd.py (Streamlit)                            │
│                                                                             │
│  ┌─────────────────────────┐  ┌─────────────────────────┐  ┌────────────┐  │
│  │  Seção 1 — PDFs         │  │  Seção 2 — Busca        │  │  Seção 3   │  │
│  │                         │  │                         │  │  Histórico │  │
│  │  [Upload 1-5 PDFs]      │  │  [Input: pergunta]      │  │            │  │
│  │       │                 │  │       │                 │  │  listar_   │  │
│  │       ▼                 │  │       ▼                 │  │  cache()   │  │
│  │  ingerir_pdfs()         │  │  buscar_cache()         │  │            │  │
│  │  └─ from ingest import  │  │  ├─ hit → data + radio  │  │  filtro    │  │
│  │     ingerir()           │  │  └─ miss → nova busca   │  │  por texto │  │
│  │                         │  │       │                 │  │            │  │
│  │  [Lista PDFs]           │  │  buscar_vetorial() k=10 │  │  por regis │  │
│  │  listar_pdfs_no_banco() │  │  responder() via LLM    │  │  📄 PDF    │  │
│  │                         │  │  salvar_cache()         │  │  🗑️ Apagar │  │
│  │  [Apagar] individual    │  │  📄 Baixar PDF resposta │  │            │  │
│  │  ou todos               │  │                         │  │            │  │
│  └─────────────────────────┘  └─────────────────────────┘  └────────────┘  │
└──────────────────────┬─────────────────────────┬───────────────────────────┘
                       │                         │
                       ▼                         ▼
          ┌──────────────────────┐   ┌─────────────────────────┐
          │ PostgreSQL + pgVector│   │  search_cache (tabela)  │
          │ langchain_pg_embedding│   │  pergunta | resposta    │
          │ (chunks + embeddings) │   │  chunks JSONB           │
          └──────────────────────┘   │  data_consulta          │
                                     └─────────────────────────┘
```

---

## Resumo das Funções

| Função | Descrição |
|--------|-----------|
| `_get_embeddings()` | Retorna instância de embeddings conforme `LLM_PROVIDER` (@cache_resource) |
| `listar_pdfs_no_banco()` | SELECT DISTINCT source/original_name de langchain_pg_embedding |
| `deletar_pdf_do_banco(source)` | DELETE chunks do PDF pelo source |
| `deletar_todos_pdfs()` | DELETE todos os chunks da coleção |
| `ingerir_pdfs(files, substituir)` | Wrapper para `ingest.ingerir()` com arquivos de upload Streamlit |
| `criar_tabela_cache()` | DDL de search_cache + migração de coluna chunks |
| `buscar_cache(pergunta)` | SELECT com LOWER/TRIM; retorna `{"resposta","chunks","data_consulta"}` |
| `salvar_cache(pergunta, resposta, resultados)` | INSERT com chunks serializados em JSONB |
| `listar_cache()` | SELECT todos os registros do cache |
| `deletar_cache_por_id(id)` | DELETE registro de cache pelo id |
| `gerar_pdf_bytes(pergunta, resposta, chunks)` | Gera PDF com ReportLab; aceita tuples e dicts |

---

## Pontos de Atenção

| Ponto | Observação |
|-------|-----------|
| `cmetadata` | Nome real da coluna em `langchain_pg_embedding` (não `metadata`) |
| `PSYCOPG_URL` | Remover `+psycopg` do DATABASE_URL para `psycopg.connect()` |
| `original_name` | Metadado extra gravado na ingestão para exibir nome amigável |
| `pre_delete` | Apenas `True` no primeiro arquivo do modo "Substituir tudo" |
| Botão desabilitável | Padrão de dois rerenders com flags `_buscando` e `_trigger_busca` |
| Cache por pergunta | `_cache_db` no session_state evita queries repetidas no mesmo ciclo |
| Exibição persistente | Resposta em `session_state["resposta_exibida"]`, fora do bloco do botão |
| Chunks no cache | Serializados como JSONB; `gerar_pdf_bytes` aceita tanto tuples quanto dicts |
| Limite de PDFs | 5 por vez; validado manualmente (Streamlit não limita nativamente) |
