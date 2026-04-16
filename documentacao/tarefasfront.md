# Tarefas — Implementação do frontEnd.py

Referência: [estudofront.md](estudofront.md)
Arquivo criado: `src/frontEnd.py`

---

## Status

- [ ] = pendente
- [x] = concluída

---

## TAREFA 1 — Preparação do ambiente

- [x] **1.1** Adicionar `streamlit>=1.35.0` e `reportlab>=4.0.0` ao `requirements.txt`
- [x] **1.2** Instalar as dependências: `pip install streamlit reportlab`
- [x] **1.3** Verificar que `psycopg[binary]` já está instalado

---

## TAREFA 2 — Criar o arquivo `src/frontEnd.py` (esqueleto)

- [x] **2.1** Criar `src/frontEnd.py` com:
  - Imports: `json`, `os`, `sys`, `tempfile`, `pathlib`, `streamlit`, `dotenv`, `psycopg`
  - `load_dotenv()`
  - Leitura das variáveis: `DATABASE_URL`, `COLLECTION_NAME`, `LLM_PROVIDER`
  - Conversão `PSYCOPG_URL` (remove `+psycopg` para uso com `psycopg.connect()`)
  - `st.set_page_config(page_title="RAG — Gerenciador de PDFs", layout="wide")`
  - `st.title("Sistema RAG — PDFs + Busca")`
- [x] **2.2** Inicializar embeddings conforme `LLM_PROVIDER` via `@st.cache_resource`

> **Nota:** `DATABASE_URL` usa `postgresql+psycopg://` (SQLAlchemy). Para `psycopg.connect()` a variável `PSYCOPG_URL` remove o `+psycopg`.

---

## TAREFA 3 — Helpers de banco de dados (PDFs)

- [x] **3.1** Implementar `listar_pdfs_no_banco() -> list[dict]`
  - Query: `SELECT DISTINCT cmetadata->>'source'` e `cmetadata->>'original_name'` em `langchain_pg_embedding` filtrado pela coleção
  - Retorna `[{"source": ..., "nome": ...}]` (prefere `original_name`, fallback para basename)

- [x] **3.2** Implementar `deletar_pdf_do_banco(source: str) -> int`
  - DELETE em `langchain_pg_embedding` onde `cmetadata->>'source' = source`
  - Retorna quantidade de chunks removidos

- [x] **3.3** Implementar `deletar_todos_pdfs() -> int`
  - DELETE todos os chunks da coleção
  - Retorna quantidade de chunks removidos

- [x] **3.4** Implementar `ingerir_pdfs(uploaded_files: list, substituir: bool) -> int`
  - Chama `from ingest import ingerir` (reutiliza lógica de `ingest.py`)
  - `pre_delete=True` apenas no primeiro arquivo quando `substituir=True`
  - Arquivo temporário removido no bloco `finally`
  - Retorna total de chunks gravados

> **Nota:** coluna de metadata nas tabelas LangChain é `cmetadata`, não `metadata`.

---

## TAREFA 4 — Helpers de cache de perguntas

- [x] **4.1** Implementar `criar_tabela_cache()`
  - DDL: `CREATE TABLE IF NOT EXISTS search_cache (id, pergunta, resposta, chunks JSONB, data_consulta)`
  - Migração automática: `ALTER TABLE search_cache ADD COLUMN IF NOT EXISTS chunks JSONB`
  - Chamado na inicialização do app (antes dos widgets)

- [x] **4.2** Implementar `buscar_cache(pergunta: str) -> dict | None`
  - SELECT com `LOWER(TRIM(pergunta))` para match insensível a maiúsculas/espaços
  - Retorna `{"resposta": ..., "chunks": [...], "data_consulta": ...}` ou `None`

- [x] **4.3** Implementar `salvar_cache(pergunta: str, resposta: str, resultados: list = None)`
  - Serializa `resultados` (list[(Document, float)]) para JSONB com `{"content","score","metadata"}`
  - INSERT na tabela `search_cache`

- [x] **4.4** Implementar `listar_cache() -> list[dict]`
  - SELECT todos os registros ordenados por `data_consulta DESC`
  - Retorna lista de dicts com id, pergunta, resposta, chunks, data_consulta

- [x] **4.5** Implementar `deletar_cache_por_id(registro_id: int) -> int`
  - DELETE registro pelo id; retorna quantidade removida

---

## TAREFA 5 — Geração de PDF

- [x] **5.1** Implementar `gerar_pdf_bytes(pergunta, resposta, chunks) -> bytes`
  - Usa ReportLab (`SimpleDocTemplate`, `Paragraph`, `Spacer`, `HRFlowable`)
  - Conteúdo: título + data, seção Pergunta, seção Resposta, seção Chunks Utilizados
  - Aceita `chunks` como `list[(Document, float)]` ou `list[dict]` (formato cache)
  - Escapa caracteres `&` e `<` para markup ReportLab
  - Trunca conteúdo dos chunks em 500 chars

---

## TAREFA 6 — Seção 1: Gerenciar PDFs (UI Streamlit)

- [x] **6.1** Criar bloco `with st.expander("📂 Gerenciar PDFs", expanded=True):`

- [x] **6.2** Adicionar `st.file_uploader`
  - `type=["pdf"]`, `accept_multiple_files=True`
  - Label: "Selecione de 1 a 5 PDFs"
  - Validar: se `len(arquivos) > 5`, exibir `st.warning` e truncar para 5

- [x] **6.3** Adicionar `st.radio` para modo de ingestão
  - Opções: `"Adicionar aos existentes"` | `"Substituir tudo"`
  - `horizontal=True`, com `help` explicativo

- [x] **6.4** Adicionar botão `"⬆️ Ingerir PDFs"`
  - Desabilitado quando nenhum arquivo selecionado
  - Ao clicar: `ingerir_pdfs()` dentro de `st.spinner`
  - Exibir `st.success` com quantidade de chunks; chamar `st.rerun()`

- [x] **6.5** Exibir lista de PDFs gravados (`listar_pdfs_no_banco()`)
  - `st.dataframe` com coluna "PDF gravado" se houver PDFs
  - `st.info` se banco vazio

- [x] **6.6** Adicionar `st.selectbox` + botão `"🗑️ Apagar selecionado"`
  - Ao clicar: `deletar_pdf_do_banco()` + `st.success` + `st.rerun()`

- [x] **6.7** Adicionar checkbox de confirmação + botão `"🗑️ Apagar todos os PDFs"`
  - Botão desabilitado enquanto checkbox não marcado
  - Ao clicar: `deletar_todos_pdfs()` + `st.success` + `st.rerun()`

---

## TAREFA 7 — Seção 2: Busca com Cache (UI Streamlit)

- [x] **7.1** Criar bloco `with st.expander("🔍 Busca / Consulta", expanded=True):`

- [x] **7.2** Adicionar `st.text_input("Sua pergunta sobre os documentos")`

- [x] **7.3** Limpar estado ao mudar a pergunta
  - Comparar com `st.session_state["_pergunta_ativa"]`
  - Limpar: `resposta_exibida`, `chunks_exibidos`, `chunks_cache`, `_cache_db`, `_buscando`, etc.

- [x] **7.4** Consultar cache uma vez por pergunta
  - Armazenar resultado em `st.session_state["_cache_db"]`
  - Se encontrado: `st.info` com data + `st.radio` "Usar resposta salva" | "Refazer consulta (gera tokens)"
  - Se não encontrado: ação padrão = refazer

- [x] **7.5** Implementar botão `"🔍 Buscar"` desabilitável durante processamento
  - Padrão dois-rerenders: clique seta `_buscando=True` + `_trigger_busca=True` + rerun
  - Processamento ocorre quando `_trigger_busca` está setado (botão aparece desabilitado)
  - Ao terminar: `_buscando=False` + rerun

- [x] **7.6** Processamento no rerender com flag `_trigger_busca`
  - Modo cache: salva `resposta_exibida`, `fonte_resposta="cache"`, `chunks_cache`
  - Modo nova busca: `buscar_vetorial(k=10)` + `responder()` + `salvar_cache()` (automático)
  - Armazena `resposta_exibida`, `fonte_resposta="nova"`, `chunks_exibidos`

- [x] **7.7** Exibição persistente da resposta fora do bloco do botão
  - `st.write(session_state["resposta_exibida"])`
  - Expander "Ver chunks recuperados" (Document objects)
  - Expander "Ver chunks recuperados (salvos no cache)" (dicts)

- [x] **7.8** Botão `"📄 Baixar PDF desta resposta"`
  - Chama `gerar_pdf_bytes()` com pergunta, resposta e chunks
  - `st.download_button` com `mime="application/pdf"`

---

## TAREFA 8 — Seção 3: Histórico (UI Streamlit)

- [x] **8.1** Criar bloco `with st.expander("📋 Histórico de Perguntas e Respostas", expanded=False):`

- [x] **8.2** Chamar `listar_cache()` e exibir contador de registros

- [x] **8.3** Adicionar `st.text_input` de filtro por texto
  - Filtra por pergunta e resposta (case-insensitive)

- [x] **8.4** Para cada registro: `st.expander` com data + início da pergunta
  - Exibir pergunta completa e resposta
  - Expander de chunks (se houver)
  - Coluna PDF: `st.download_button` "📄 Baixar PDF"
  - Coluna Delete: `st.button` "🗑️ Apagar este registro" com `st.rerun()`

---

## TAREFA 9 — Script de inicialização `ini.bat`

- [x] **9.1** Criar `ini.bat` na raiz do projeto
- [x] **9.2** Ativar ambiente virtual (`venv\Scripts\activate.bat`)
- [x] **9.3** Verificar/iniciar container Docker `rag_postgres`
- [x] **9.4** Verificar se Streamlit está instalado; instalar se não
- [x] **9.5** Abrir Chrome em `http://localhost:8501` após 4 segundos (em background)
- [x] **9.6** Iniciar Streamlit em modo headless na porta 8501

---

## TAREFA 10 — Testes manuais

- [ ] **10.1** Executar `ini.bat` e verificar que o Chrome abre com a página carregada
- [ ] **10.2** Testar upload de 1 PDF no modo "Adicionar aos existentes"
- [ ] **10.3** Testar upload de 5 PDFs simultaneamente
- [ ] **10.4** Testar upload no modo "Substituir tudo" — verificar que PDFs anteriores somem
- [ ] **10.5** Testar apagar um PDF específico e verificar que apenas ele é removido
- [ ] **10.6** Testar "Apagar todos os PDFs" com confirmação
- [ ] **10.7** Testar busca com pergunta nova (sem cache) — verificar resposta e chunks
- [ ] **10.8** Verificar que a resposta é salva automaticamente no cache após nova consulta
- [ ] **10.9** Refazer a mesma pergunta — verificar que o aviso de cache aparece com data
- [ ] **10.10** Testar opção "Usar resposta salva" — deve retornar sem chamar o LLM
- [ ] **10.11** Testar opção "Refazer consulta (gera tokens)" — deve chamar o LLM
- [ ] **10.12** Verificar que o botão "Buscar" fica desabilitado durante o processamento
- [ ] **10.13** Baixar PDF da resposta (Seção 2) e verificar conteúdo
- [ ] **10.14** Verificar Seção 3: registros aparecem, filtro funciona, chunks visíveis
- [ ] **10.15** Baixar PDF do histórico (Seção 3) e verificar conteúdo
- [ ] **10.16** Apagar registro do histórico e verificar que some da lista

---

## Ordem de execução

```
TAREFA 1 → TAREFA 2 → TAREFA 3 → TAREFA 4 → TAREFA 5 → TAREFA 6 → TAREFA 7 → TAREFA 8 → TAREFA 9 → TAREFA 10
```

Tarefas 1 a 9: **concluídas**.
Tarefa 10 (testes manuais): pendente — executar via `ini.bat`.
