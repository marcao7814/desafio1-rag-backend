"""
frontEnd.py — Interface web Streamlit para o sistema RAG.

Executar:
    streamlit run src/frontEnd.py
"""

import json
import os
import sys
import tempfile
import pathlib

import psycopg # type: ignore
import streamlit as st
from dotenv import load_dotenv

# Garante que src/ está no path para importar search e chat
sys.path.insert(0, str(pathlib.Path(__file__).parent))

load_dotenv()

# ── Variáveis de ambiente ────────────────────────────────────────────────────
PROVIDER     = os.getenv("LLM_PROVIDER", "openai").lower()
DATABASE_URL = os.getenv("DATABASE_URL", "")
COLLECTION   = os.getenv("COLLECTION_NAME", "documentos_rag")

# psycopg.connect() não aceita o prefixo "+psycopg" do SQLAlchemy
PSYCOPG_URL = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://") \
                           .replace("postgres+psycopg://", "postgresql://")




# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — Banco de dados (PDFs)
# ══════════════════════════════════════════════════════════════════════════════

def listar_pdfs_no_banco() -> list[dict]:
    """
    Retorna lista de dicts {"source": ..., "nome": ...} dos PDFs gravados.
    Prefere 'original_name' do metadata para exibição; usa basename do source como fallback.
    """
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
    try:
        with psycopg.connect(PSYCOPG_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (COLLECTION,))
                rows = cur.fetchall()
        return [
            {"source": r[0], "nome": r[1] or os.path.basename(r[0] or "")}
            for r in rows if r[0]
        ]
    except Exception as e:
        st.error(f"Erro ao listar PDFs: {e}")
        return []


def deletar_pdf_do_banco(source: str) -> int:
    """Remove todos os chunks do PDF indicado pelo source. Retorna qtd de chunks removidos."""
    sql = """
        DELETE FROM langchain_pg_embedding
        WHERE collection_id = (
            SELECT uuid FROM langchain_pg_collection WHERE name = %s
        )
        AND cmetadata->>'source' = %s
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (COLLECTION, source))
            deletados = cur.rowcount
        conn.commit()
    return deletados


def deletar_todos_pdfs() -> int:
    """Remove todos os chunks de todos os PDFs da coleção. Retorna qtd de chunks removidos."""
    sql = """
        DELETE FROM langchain_pg_embedding
        WHERE collection_id = (
            SELECT uuid FROM langchain_pg_collection WHERE name = %s
        )
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (COLLECTION,))
            deletados = cur.rowcount
        conn.commit()
    return deletados


def ingerir_pdfs(uploaded_files: list, substituir: bool = False) -> int:
    """
    Ingere lista de UploadedFile do Streamlit usando a função ingerir() do ingest.py.
    substituir=True apaga a coleção antes do primeiro arquivo (pre_delete=True).
    Os demais arquivos sempre usam pre_delete=False para preservar os anteriores.
    Retorna total de chunks gravados.
    """
    from ingest import ingerir

    total = 0
    for i, uf in enumerate(uploaded_files):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uf.read())
            tmp_path = tmp.name

        try:
            # Apenas o primeiro arquivo pode apagar a coleção (modo substituir)
            pre_delete = substituir and (i == 0)
            n = ingerir(tmp_path, nome_original=uf.name, pre_delete=pre_delete)
            total += n
        finally:
            os.unlink(tmp_path)

    return total


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS — Cache de perguntas
# ══════════════════════════════════════════════════════════════════════════════

def criar_tabela_cache():
    """Cria a tabela search_cache (e migra colunas se necessário)."""
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    id            SERIAL PRIMARY KEY,
                    pergunta      TEXT NOT NULL,
                    resposta      TEXT NOT NULL,
                    chunks        JSONB,
                    data_consulta TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("ALTER TABLE search_cache ADD COLUMN IF NOT EXISTS chunks JSONB")
            cur.execute("ALTER TABLE search_cache ADD COLUMN IF NOT EXISTS tipo VARCHAR DEFAULT 'rag'")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS verification_cache (
                    id                SERIAL PRIMARY KEY,
                    arquivo           TEXT NOT NULL,
                    modo              VARCHAR(10) NOT NULL,
                    criterio          TEXT NOT NULL,
                    ocorrencias       JSONB NOT NULL,
                    status            VARCHAR(20) NOT NULL,
                    data_verificacao  TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("ALTER TABLE verification_cache ALTER COLUMN status TYPE VARCHAR(30)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS aprovacao_manual (
                    id               SERIAL PRIMARY KEY,
                    verification_id  INTEGER NOT NULL REFERENCES verification_cache(id) ON DELETE CASCADE,
                    chunk_indice     INTEGER NOT NULL,
                    observacao       TEXT,
                    tipo             VARCHAR(30) DEFAULT 'aprovado',
                    data_aprovacao   TIMESTAMP DEFAULT NOW(),
                    UNIQUE (verification_id, chunk_indice)
                )
            """)
            cur.execute("ALTER TABLE aprovacao_manual ADD COLUMN IF NOT EXISTS tipo VARCHAR(30) DEFAULT 'aprovado'")
        conn.commit()


def buscar_verificacao_cache(arquivo: str, modo: str, criterio: str) -> dict | None:
    """Busca resultado de verificação no cache. Retorna dict ou None."""
    sql = """
        SELECT ocorrencias, status, data_verificacao
        FROM verification_cache
        WHERE arquivo = %s
          AND modo    = %s
          AND LOWER(TRIM(criterio)) = LOWER(TRIM(%s))
        ORDER BY data_verificacao DESC
        LIMIT 1
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (arquivo, modo, criterio))
            row = cur.fetchone()
    if row:
        return {"ocorrencias": row[0] or [], "status": row[1], "data_verificacao": row[2]}
    return None


def salvar_verificacao_cache(arquivo: str, modo: str, criterio: str, ocorrencias: list) -> int:
    """Salva resultado de verificação no cache. Retorna o id gerado."""
    status = "aprovado" if not ocorrencias else "reprovado"
    sql = """
        INSERT INTO verification_cache (arquivo, modo, criterio, ocorrencias, status)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (arquivo, modo, criterio, json.dumps(ocorrencias, ensure_ascii=False), status))
            novo_id = cur.fetchone()[0]
        conn.commit()
    return novo_id


def buscar_cache(pergunta: str, tipo: str = "rag") -> dict | None:
    """
    Busca a pergunta no cache (case-insensitive, ignora espaços extras) filtrando por tipo.
    Retorna dict {"resposta", "chunks", "data_consulta"} ou None se não encontrado.
    """
    sql = """
        SELECT resposta, chunks, data_consulta
        FROM search_cache
        WHERE LOWER(TRIM(pergunta)) = LOWER(TRIM(%s))
          AND tipo = %s
        ORDER BY data_consulta DESC
        LIMIT 1
    """
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (pergunta, tipo))
            row = cur.fetchone()
    if row:
        return {"resposta": row[0], "chunks": row[1] or [], "data_consulta": row[2]}
    return None


def salvar_cache(pergunta: str, resposta: str, resultados: list = None, tipo: str = "rag"):
    """Insere nova entrada no cache incluindo chunks/fontes serializados em JSON."""
    chunks_json = None
    if resultados and tipo == "rag":
        chunks_json = json.dumps([
            {
                "content":  doc.page_content,
                "score":    float(score),
                "metadata": doc.metadata,
            }
            for doc, score in resultados
        ], ensure_ascii=False)
    elif resultados and tipo == "web":
        # resultados é lista de dicts {"title", "url"} para buscas web
        chunks_json = json.dumps(resultados, ensure_ascii=False)

    sql = "INSERT INTO search_cache (pergunta, resposta, chunks, tipo) VALUES (%s, %s, %s, %s)"
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (pergunta, resposta, chunks_json, tipo))
        conn.commit()


def listar_cache() -> list[dict]:
    """Retorna todos os registros do cache ordenados do mais recente ao mais antigo."""
    sql = "SELECT id, pergunta, resposta, chunks, data_consulta, tipo FROM search_cache ORDER BY data_consulta DESC"
    try:
        with psycopg.connect(PSYCOPG_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [
            {"id": r[0], "pergunta": r[1], "resposta": r[2],
             "chunks": r[3] or [], "data_consulta": r[4], "tipo": r[5] or "rag"}
            for r in rows
        ]
    except Exception as e:
        st.error(f"Erro ao listar cache: {e}")
        return []


def deletar_cache_por_id(registro_id: int) -> int:
    """Remove um registro do cache pelo id. Retorna qtd de linhas removidas."""
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM search_cache WHERE id = %s", (registro_id,))
            deletados = cur.rowcount
        conn.commit()
    return deletados



def listar_verificacao_cache() -> list[dict]:
    """Retorna todos os registros de verificação ordenados do mais recente ao mais antigo."""
    sql = """
        SELECT id, arquivo, modo, criterio, ocorrencias, status, data_verificacao
        FROM verification_cache
        ORDER BY data_verificacao DESC
    """
    try:
        with psycopg.connect(PSYCOPG_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [
            {
                "id":               r[0],
                "arquivo":          r[1],
                "modo":             r[2],
                "criterio":         r[3],
                "ocorrencias":      r[4] or [],
                "status":           r[5],
                "data_verificacao": r[6],
            }
            for r in rows
        ]
    except Exception as e:
        st.error(f"Erro ao listar histórico de verificações: {e}")
        return []


def deletar_verificacao_cache_por_id(registro_id: int) -> int:
    """Remove um registro de verificação pelo id."""
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM verification_cache WHERE id = %s", (registro_id,))
            deletados = cur.rowcount
        conn.commit()
    return deletados


def aprovar_chunk_manual(verification_id: int, chunk_indice: int, observacao: str = "", tipo: str = "aprovado"):
    """Registra revisão manual de um chunk. tipo: 'aprovado' ou 'reprovado_confirmado'."""
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO aprovacao_manual (verification_id, chunk_indice, observacao, tipo)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (verification_id, chunk_indice) DO UPDATE
                    SET observacao = EXCLUDED.observacao,
                        tipo = EXCLUDED.tipo,
                        data_aprovacao = NOW()
            """, (verification_id, chunk_indice, observacao, tipo))
        conn.commit()
    _atualizar_status_verificacao(verification_id)


def aprovar_por_mesmo_motivo(verification_id: int, chunk_indice: int, observacao: str, ocorrencias: list, tipo: str = "aprovado") -> int:
    """
    Aprova o chunk indicado e todos os demais da mesma verificação que compartilham
    o mesmo motivo de reprovação (mesmas palavras para modo exata; mesmo motivo para LLM).
    Retorna a quantidade de chunks aprovados.
    """
    def _chave(oc: dict):
        palavras = oc.get("palavras")
        if palavras:
            return ("exata", frozenset(p.lower() for p in palavras))
        motivo = (oc.get("motivo") or "").strip().lower()
        return ("llm", motivo) if motivo else None

    chave_ref = _chave(ocorrencias[chunk_indice])
    indices = [
        i for i, oc in enumerate(ocorrencias)
        if chave_ref is not None and _chave(oc) == chave_ref
    ]
    if chunk_indice not in indices:
        indices.append(chunk_indice)

    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            for idx in indices:
                cur.execute("""
                    INSERT INTO aprovacao_manual (verification_id, chunk_indice, observacao, tipo)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (verification_id, chunk_indice) DO UPDATE
                        SET observacao = EXCLUDED.observacao,
                            tipo = EXCLUDED.tipo,
                            data_aprovacao = NOW()
                """, (verification_id, idx, observacao, tipo))
        conn.commit()
    _atualizar_status_verificacao(verification_id)
    return len(indices)


def remover_aprovacao_manual(verification_id: int, chunk_indice: int):
    """Remove aprovação manual de um chunk."""
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM aprovacao_manual WHERE verification_id = %s AND chunk_indice = %s",
                (verification_id, chunk_indice),
            )
        conn.commit()
    _atualizar_status_verificacao(verification_id)


def listar_aprovacoes_manuais(verification_id: int) -> dict[int, str]:
    """Retorna dict {chunk_indice: tipo} de todas as revisões manuais da verificação.
    tipo pode ser 'aprovado' ou 'reprovado_confirmado'."""
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_indice, COALESCE(tipo, 'aprovado') FROM aprovacao_manual WHERE verification_id = %s",
                (verification_id,),
            )
            rows = cur.fetchall()
    return {r[0]: r[1] for r in rows}


def _atualizar_status_verificacao(verification_id: int):
    """Recalcula e grava o status da verificação com base nas revisões manuais."""
    with psycopg.connect(PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ocorrencias FROM verification_cache WHERE id = %s",
                (verification_id,),
            )
            row = cur.fetchone()
            if not row:
                return
            n_ocs = len(row[0] or [])

            cur.execute(
                "SELECT COALESCE(tipo,'aprovado'), COUNT(*) FROM aprovacao_manual WHERE verification_id = %s GROUP BY tipo",
                (verification_id,),
            )
            contagens = {r[0]: r[1] for r in cur.fetchall()}
            n_aprovados   = contagens.get("aprovado", 0)
            n_confirmados = contagens.get("reprovado_confirmado", 0)
            n_revisados   = n_aprovados + n_confirmados

            if n_ocs == 0:
                novo_status = "aprovado"
            elif n_aprovados >= n_ocs:
                novo_status = "aprovado manualmente"
            elif n_revisados >= n_ocs:
                novo_status = "reprovado confirmado"
            else:
                novo_status = "reprovado"

            cur.execute(
                "UPDATE verification_cache SET status = %s WHERE id = %s",
                (novo_status, verification_id),
            )
        conn.commit()


def _nome_pdf(pergunta: str) -> str:
    """Gera nome de arquivo PDF com até 30 chars da pergunta, sanitizado."""
    import re
    slug = re.sub(r'[\\/:*?"<>|]', '', pergunta)  # remove chars inválidos
    slug = re.sub(r'\s+', '_', slug.strip())        # espaços → underscore
    slug = slug[:30].rstrip('_')                    # limita e remove _ final
    return f"{slug}.pdf" if slug else "resposta.pdf"


def gerar_pdf_bytes(pergunta: str, resposta: str, chunks: list) -> bytes:
    """
    Gera um PDF com pergunta, resposta e chunks utilizados.
    chunks aceita:
      - list[(Document, float)]  — resultado direto da busca vetorial
      - list[dict]               — formato serializado do cache ({"content","score","metadata"})
    """
    from io import BytesIO
    from datetime import datetime
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER

    buffer = BytesIO()
    doc_pdf = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )

    styles = getSampleStyleSheet()
    titulo_st = ParagraphStyle("Titulo", parent=styles["Title"], alignment=TA_CENTER, spaceAfter=4*mm)
    h2_st     = ParagraphStyle("H2",     parent=styles["Heading2"], spaceBefore=4*mm, spaceAfter=2*mm)
    body_st   = styles["Normal"]
    small_st  = ParagraphStyle("Small",  parent=styles["Normal"], fontSize=9, leading=13)
    hr        = HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#AAAAAA"))

    story = []
    story.append(Paragraph("RAG — Resposta Gerada", titulo_st))
    story.append(Paragraph(f"<b>Data:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", body_st))
    story.append(Spacer(1, 4*mm))
    story.append(hr)

    story.append(Paragraph("Pergunta", h2_st))
    story.append(Paragraph(pergunta.replace("&", "&amp;").replace("<", "&lt;"), body_st))
    story.append(Spacer(1, 4*mm))
    story.append(hr)

    story.append(Paragraph("Resposta", h2_st))
    for linha in resposta.split("\n"):
        txt = linha.strip().replace("&", "&amp;").replace("<", "&lt;")
        if txt:
            story.append(Paragraph(txt, body_st))
        else:
            story.append(Spacer(1, 2*mm))
    story.append(Spacer(1, 4*mm))

    if chunks:
        story.append(hr)
        story.append(Paragraph(f"Chunks Utilizados ({len(chunks)})", h2_st))
        for i, chunk in enumerate(chunks, 1):
            if isinstance(chunk, tuple):           # (Document, score)
                doc_obj, score = chunk
                content = doc_obj.page_content
                meta    = doc_obj.metadata
            else:                                   # dict do cache
                content = chunk.get("content", "")
                score   = chunk.get("score", 0)
                meta    = chunk.get("metadata", {})

            nome   = meta.get("original_name") or os.path.basename(meta.get("source") or "?")
            pagina = meta.get("page", "?")
            header = (f"<b>[{i}]</b> Score: {float(score):.4f} | "
                      f"Arquivo: {nome} | Página: {pagina}")
            story.append(Paragraph(header, body_st))
            trecho = (content[:500] + "…") if len(content) > 500 else content
            story.append(Paragraph(
                trecho.replace("&", "&amp;").replace("<", "&lt;").replace("\n", " "),
                small_st,
            ))
            story.append(Spacer(1, 3*mm))

    doc_pdf.build(story)
    return buffer.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# APP — Configuração (deve ser a primeira chamada Streamlit)
# ══════════════════════════════════════════════════════════════════════════════

def _render_botao_aprovacao(
    verification_id: int | None,
    chunk_indice: int,
    tipo_revisao: str | None,
    key_suffix: str,
    ocorrencias: list | None = None,
):
    """Renderiza botões de revisão manual para um chunk.
    tipo_revisao: None = não revisado | 'aprovado' | 'reprovado_confirmado'
    Se ocorrencias for fornecido, aplica a todos os itens com o mesmo motivo."""
    if verification_id is None:
        st.caption("_Salve a verificação para habilitar revisão manual._")
        return

    def _aplicar(tipo: str, obs: str):
        if ocorrencias:
            n = aprovar_por_mesmo_motivo(verification_id, chunk_indice, obs, ocorrencias, tipo)
            label = "aprovada(s)" if tipo == "aprovado" else "reprovação(ões) confirmada(s)"
            st.session_state[f"_msg_aprov_{verification_id}"] = (
                f"{'✅' if tipo == 'aprovado' else '🚫'} {n} ocorrência(s) com o mesmo motivo {label}."
            )
        else:
            aprovar_chunk_manual(verification_id, chunk_indice, obs, tipo)
        st.rerun()

    if tipo_revisao == "aprovado":
        col1, col2 = st.columns([1, 1])
        with col1:
            st.success("✅ Aprovado manualmente")
        with col2:
            if st.button("🚫 Reprovar", key=f"reprovar_{key_suffix}_{verification_id}"):
                _aplicar("reprovado_confirmado", "")

    elif tipo_revisao == "reprovado_confirmado":
        col1, col2 = st.columns([1, 1])
        with col1:
            st.error("🚫 Reprovação confirmada")
        with col2:
            obs = st.text_input(
                "Observação (opcional)",
                key=f"obs_aprov_{key_suffix}_{verification_id}",
                label_visibility="collapsed",
                placeholder="Observação sobre a aprovação...",
            )
            if st.button("✅ Aprovar manualmente", key=f"aprov_{key_suffix}_{verification_id}"):
                _aplicar("aprovado", obs)

    else:  # não revisado
        obs = st.text_input(
            "Observação (opcional)",
            key=f"obs_aprov_{key_suffix}_{verification_id}",
            label_visibility="collapsed",
            placeholder="Observação sobre a revisão...",
        )
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("✅ Aprovar manualmente", key=f"aprov_{key_suffix}_{verification_id}"):
                _aplicar("aprovado", obs)
        with col2:
            if st.button("🚫 Confirmar Reprovação", key=f"reprovar_{key_suffix}_{verification_id}"):
                _aplicar("reprovado_confirmado", obs)


def gerar_pdf_verificacao(
    nome_arquivo: str,
    modo: str,
    label: str,
    ocorrencias: list,
) -> bytes:
    """Gera PDF com o resultado da verificação de conteúdo."""
    from io import BytesIO
    from datetime import datetime
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER

    aprovado = len(ocorrencias) == 0
    status   = "APROVADO" if aprovado else "REPROVADO"

    buffer   = BytesIO()
    doc_pdf  = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )

    styles   = getSampleStyleSheet()
    titulo_st = ParagraphStyle("Titulo", parent=styles["Title"], alignment=TA_CENTER, spaceAfter=4*mm)
    h2_st    = ParagraphStyle("H2",    parent=styles["Heading2"], spaceBefore=4*mm, spaceAfter=2*mm)
    body_st  = styles["Normal"]
    small_st = ParagraphStyle("Small", parent=styles["Normal"], fontSize=9, leading=13)
    cor_status = colors.HexColor("#1a7f37") if aprovado else colors.HexColor("#c0392b")
    status_st = ParagraphStyle("Status", parent=styles["Title"], alignment=TA_CENTER,
                                textColor=cor_status, fontSize=20, spaceAfter=4*mm)
    hr = HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#AAAAAA"))

    story = []
    story.append(Paragraph("Verificação de Conteúdo — RAG", titulo_st))
    story.append(Paragraph(status, status_st))
    story.append(Paragraph(f"<b>Data:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", body_st))
    story.append(Spacer(1, 2*mm))
    story.append(hr)

    story.append(Paragraph("Informações", h2_st))
    story.append(Paragraph(f"<b>Arquivo verificado:</b> {nome_arquivo}", body_st))
    modo_label = "Busca Exata (SQL)" if modo == "exata" else "Moderação por LLM"
    story.append(Paragraph(f"<b>Modo:</b> {modo_label}", body_st))
    story.append(Paragraph(f"<b>Critério:</b> {label}", body_st))
    story.append(Paragraph(f"<b>Resultado:</b> {status}", body_st))
    story.append(Spacer(1, 4*mm))
    story.append(hr)

    def _escapar(txt: str) -> str:
        return txt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _grifar_exata(trecho: str, palavras: list[str]) -> str:
        """Grifa palavras encontradas em vermelho negrito no markup ReportLab."""
        import re as _re
        resultado = _escapar(trecho).replace("\n", " ")
        for p in palavras:
            resultado = _re.sub(
                f"({_re.escape(_escapar(p))})",
                r'<font color="#c0392b"><b>\1</b></font>',
                resultado,
                flags=_re.IGNORECASE,
            )
        return resultado

    def _grifar_llm(trecho: str, motivo: str) -> str:
        """Grifa a frase reprovada (extraída do motivo) em vermelho negrito."""
        import re as _re
        trecho_esc = _escapar(trecho).replace("\n", " ")
        # Motivo tem formato: '"frase reprovada" — explicação'
        match = _re.search(r'"([^"]+)"', motivo)
        if not match:
            return trecho_esc
        frase = match.group(1).strip()
        frase_esc = _escapar(frase)
        return _re.sub(
            f"({_re.escape(frase_esc)})",
            r'<font color="#c0392b"><b>\1</b></font>',
            trecho_esc,
            flags=_re.IGNORECASE,
        )

    if aprovado:
        story.append(Paragraph("Resultado", h2_st))
        story.append(Paragraph("Nenhum conteúdo proibido encontrado. O arquivo está aprovado.", body_st))
    else:
        story.append(Paragraph(f"Ocorrências ({len(ocorrencias)} chunk(s) reprovado(s))", h2_st))
        for i, oc in enumerate(ocorrencias, 1):
            story.append(Paragraph(f"<b>[{i}] Página:</b> {oc.get('pagina','?')}", body_st))
            if modo == "exata":
                palavras = oc.get("palavras", [])
                story.append(Paragraph(
                    f"<b>Palavras encontradas:</b> " + ", ".join(f"<font color='#c0392b'><b>{_escapar(p)}</b></font>" for p in palavras),
                    body_st,
                ))
                trecho_markup = _grifar_exata(oc.get("trecho", "") or "", palavras)
            else:
                motivo_txt = oc.get("motivo", "não especificado")
                story.append(Paragraph(
                    f"<b>Motivo:</b> {_escapar(motivo_txt)}", body_st,
                ))
                trecho_markup = _grifar_llm(oc.get("trecho", "") or "", motivo_txt)

            story.append(Paragraph(trecho_markup, small_st))
            story.append(Spacer(1, 3*mm))

    doc_pdf.build(story)
    return buffer.getvalue()


st.set_page_config(page_title="RAG — Gerenciador de PDFs", layout="wide")

# Validação crítica de ambiente
if not DATABASE_URL:
    st.error("DATABASE_URL não definida no .env. Verifique o arquivo .env e reinicie.")
    st.stop()

# Inicialização única na primeira carga
try:
    criar_tabela_cache()
except Exception as e:
    st.error(f"Erro ao conectar no banco: {e}")
    st.stop()

st.title("Sistema RAG — PDFs + Busca")

# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 1 — Gerenciar PDFs
# ══════════════════════════════════════════════════════════════════════════════

with st.expander("📂 Gerenciar PDFs", expanded=True):

    # --- Upload ---
    arquivos = st.file_uploader(
        "Selecione de 1 a 5 PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        key="uploader",
    )
    if arquivos and len(arquivos) > 5:
        st.warning("Máximo de 5 arquivos por vez. Somente os 5 primeiros serão processados.")
        arquivos = arquivos[:5]

    modo = st.radio(
        "Modo de ingestão",
        ["Adicionar aos existentes", "Substituir tudo"],
        horizontal=True,
        help="'Substituir tudo' apaga todos os PDFs já gravados antes de ingerir os novos.",
    )

    if st.button("⬆️ Ingerir PDFs", disabled=not arquivos, type="primary"):
        with st.spinner(f"Processando {len(arquivos)} arquivo(s)..."):
            try:
                n = ingerir_pdfs(arquivos, substituir=(modo == "Substituir tudo"))
                st.session_state["_ingest_msg"] = ("success", f"✅ {n} chunk(s) gravados com sucesso.")
            except Exception as e:
                st.session_state["_ingest_msg"] = ("error", f"Erro na ingestão: {e}")
        st.rerun()

    if "_ingest_msg" in st.session_state:
        kind, msg = st.session_state.pop("_ingest_msg")
        if kind == "success":
            st.success(msg)
        else:
            st.error(msg)

    # --- Lista dos PDFs gravados ---
    st.markdown("---")
    st.markdown("### PDFs no banco")
    pdfs = listar_pdfs_no_banco()

    if not pdfs:
        st.info("Nenhum PDF gravado ainda.")
    else:
        col_tab, col_del = st.columns([3, 2])

        with col_tab:
            st.dataframe(
                {"PDF gravado": [p["nome"] for p in pdfs]},
                width="stretch",
                hide_index=True,
            )
            st.caption(f"Total: {len(pdfs)} arquivo(s) no banco")

        with col_del:
            opcoes = {p["nome"]: p["source"] for p in pdfs}
            nome_sel = st.selectbox("Selecione para apagar", list(opcoes.keys()))
            if st.button("🗑️ Apagar selecionado", type="secondary"):
                try:
                    n = deletar_pdf_do_banco(opcoes[nome_sel])
                    st.success(f"✅ {n} chunk(s) de '{nome_sel}' removidos.")
                except Exception as e:
                    st.error(f"Erro ao apagar: {e}")
                st.rerun()

            st.markdown("---")
            confirmar = st.checkbox("Confirmar exclusão de **todos** os PDFs")
            if st.button("🗑️ Apagar todos os PDFs", type="secondary", disabled=not confirmar):
                try:
                    n = deletar_todos_pdfs()
                    st.success(f"✅ {n} chunk(s) removidos. Banco vazio.")
                except Exception as e:
                    st.error(f"Erro ao apagar tudo: {e}")
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 2 — Busca / Consulta
# ══════════════════════════════════════════════════════════════════════════════

with st.expander("🔍 Busca / Consulta", expanded=True):

    pergunta = st.text_input("Sua pergunta sobre os documentos", key="pergunta_input")

    # Limpa resultados e flags quando a pergunta muda
    if pergunta != st.session_state.get("_pergunta_ativa", ""):
        for k in ["resposta_exibida", "chunks_exibidos", "chunks_cache", "fonte_resposta",
                  "_cache_db", "_buscando", "_trigger_busca", "_aviso_busca"]:
            st.session_state.pop(k, None)
        st.session_state["_pergunta_ativa"] = pergunta

    if pergunta:
        # Consulta o banco uma única vez por pergunta; reutiliza nas rerenders seguintes
        if "_cache_db" not in st.session_state:
            try:
                st.session_state["_cache_db"] = buscar_cache(pergunta)
            except Exception as e:
                st.session_state["_cache_db"] = None
                st.error(f"Erro ao consultar cache: {e}")

        cache = st.session_state["_cache_db"]

        if cache:
            data_fmt = cache["data_consulta"].strftime("%d/%m/%Y %H:%M")
            st.info(f"⚡ Resposta em cache de **{data_fmt}**. Nenhum token será gerado.")
            acao = st.radio(
                "O que deseja fazer?",
                ["Usar resposta salva", "Refazer consulta (gera tokens)"],
                horizontal=True,
                key="acao_cache",
            )
        else:
            acao = "Refazer consulta"

        # Botão desabilitado enquanto processa; clique define a flag e faz rerun
        if st.button("🔍 Buscar", type="primary",
                     disabled=st.session_state.get("_buscando", False)):
            st.session_state["_buscando"] = True
            st.session_state["_trigger_busca"] = True
            st.rerun()

        # Processamento — ocorre no rerender após o botão ser exibido como desabilitado
        if st.session_state.get("_trigger_busca"):
            st.session_state.pop("_trigger_busca")

            if cache and acao == "Usar resposta salva":
                st.session_state["resposta_exibida"] = cache["resposta"]
                st.session_state["fonte_resposta"] = "cache"
                st.session_state["chunks_cache"] = cache.get("chunks", [])
                st.session_state.pop("chunks_exibidos", None)

            else:
                from search import buscar as buscar_vetorial

                with st.spinner("Buscando nos documentos..."):
                    resultados = buscar_vetorial(pergunta, k=10)

                if not resultados:
                    st.session_state["_aviso_busca"] = "Nenhum resultado encontrado nos documentos."
                else:
                    from chat import responder

                    with st.spinner("Gerando resposta com o LLM..."):
                        resposta = responder(pergunta)

                    try:
                        salvar_cache(pergunta, resposta, resultados)
                        st.session_state.pop("_cache_db", None)
                    except Exception as e:
                        st.session_state["_aviso_busca"] = f"Não foi possível salvar no cache: {e}"

                    st.session_state["resposta_exibida"] = resposta
                    st.session_state["fonte_resposta"] = "nova"
                    st.session_state["chunks_exibidos"] = resultados

            st.session_state["_buscando"] = False
            st.rerun()

        if st.session_state.get("_aviso_busca"):
            st.warning(st.session_state.pop("_aviso_busca"))

    # Exibição persistente da resposta (fora do bloco do botão)
    if "resposta_exibida" in st.session_state:
        fonte = st.session_state.get("fonte_resposta", "nova")
        pergunta_ativa = st.session_state.get("_pergunta_ativa", "")

        st.markdown("---")
        st.markdown(f"**Pergunta:** {pergunta_ativa}")
        st.markdown("### Resposta (cache)" if fonte == "cache" else "### Resposta")
        with st.container(height=400):
            st.write(st.session_state["resposta_exibida"])

        mostrar_chunks = st.checkbox("Mostrar chunks recuperados", value=False, key="chk_chunks_busca")

        if mostrar_chunks:
            # Chunks de nova consulta (objetos Document)
            if st.session_state.get("chunks_exibidos"):
                with st.expander("Chunks recuperados", expanded=True):
                    for i, (doc, score) in enumerate(st.session_state["chunks_exibidos"], 1):
                        nome = doc.metadata.get("original_name") or \
                               os.path.basename(doc.metadata.get("source", "?"))
                        st.markdown(
                            f"**[{i}]** Score: `{score:.4f}` | "
                            f"Arquivo: `{nome}` | "
                            f"Página: `{doc.metadata.get('page', '?')}`"
                        )
                        st.caption(doc.page_content[:300] + "...")

            # Chunks salvos no cache (dicts JSON)
            if st.session_state.get("chunks_cache"):
                with st.expander("Chunks recuperados (cache)", expanded=True):
                    for i, chunk in enumerate(st.session_state["chunks_cache"], 1):
                        meta = chunk.get("metadata", {})
                        nome = meta.get("original_name") or os.path.basename(meta.get("source", "?"))
                        st.markdown(
                            f"**[{i}]** Score: `{chunk.get('score', 0):.4f}` | "
                            f"Arquivo: `{nome}` | "
                            f"Página: `{meta.get('page', '?')}`"
                        )
                        st.caption(chunk.get("content", "")[:300] + "...")

        # Botão de download do PDF
        chunks_para_pdf = (
            (st.session_state.get("chunks_exibidos") or
             st.session_state.get("chunks_cache") or [])
            if mostrar_chunks else []
        )
        try:
            pdf_bytes = gerar_pdf_bytes(
                st.session_state.get("_pergunta_ativa", ""),
                st.session_state["resposta_exibida"],
                chunks_para_pdf,
            )
            st.download_button(
                "📄 Baixar PDF desta resposta",
                data=pdf_bytes,
                file_name=_nome_pdf(st.session_state.get("_pergunta_ativa", "")),
                mime="application/pdf",
                key="dl_pdf_secao2",
            )
        except Exception as e:
            st.warning(f"Erro ao gerar PDF: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 3 — Busca na Internet (via Gemini + Google Search)
# ══════════════════════════════════════════════════════════════════════════════

with st.expander("🌐 Busca na Internet (via Gemini)", expanded=False):

    pergunta_web = st.text_input("Sua pergunta para a internet", key="pergunta_web_input")

    # Limpa resultado quando a pergunta muda
    if pergunta_web != st.session_state.get("_pergunta_web_ativa", ""):
        for k in ["_resposta_web", "_fontes_web", "_buscando_web", "_trigger_web",
                  "_aviso_web", "_cache_web", "_acao_web"]:
            st.session_state.pop(k, None)
        st.session_state["_pergunta_web_ativa"] = pergunta_web

    if pergunta_web:
        if "_cache_web" not in st.session_state:
            try:
                st.session_state["_cache_web"] = buscar_cache(pergunta_web, tipo="web")
            except Exception as e:
                st.session_state["_cache_web"] = None
                st.error(f"Erro ao consultar cache: {e}")

        cache_web = st.session_state["_cache_web"]

        if cache_web:
            data_fmt = cache_web["data_consulta"].strftime("%d/%m/%Y %H:%M")
            st.info(f"⚡ Resposta em cache de **{data_fmt}**. Nenhum token será gerado.")
            acao_web = st.radio(
                "O que deseja fazer?",
                ["Usar resposta salva", "Refazer consulta (gera tokens)"],
                horizontal=True,
                key="acao_cache_web",
            )
        else:
            acao_web = "Refazer consulta"

        if st.button("🌐 Buscar na Internet", type="primary",
                     disabled=st.session_state.get("_buscando_web", False),
                     key="btn_busca_web"):
            st.session_state["_buscando_web"] = True
            st.session_state["_trigger_web"] = True
            st.session_state["_acao_web"] = acao_web
            st.rerun()

        if st.session_state.get("_trigger_web"):
            st.session_state.pop("_trigger_web")
            acao_atual = st.session_state.pop("_acao_web", "Refazer consulta")

            if cache_web and acao_atual == "Usar resposta salva":
                st.session_state["_resposta_web"] = cache_web["resposta"]
                st.session_state["_fontes_web"] = cache_web["chunks"]
            else:
                from web_search import buscar_na_web

                with st.spinner("Buscando na internet..."):
                    try:
                        resposta_web, fontes_web = buscar_na_web(pergunta_web)
                        st.session_state["_resposta_web"] = resposta_web
                        st.session_state["_fontes_web"] = fontes_web
                        try:
                            salvar_cache(pergunta_web, resposta_web, fontes_web, tipo="web")
                            st.session_state.pop("_cache_web", None)
                        except Exception as e:
                            st.session_state["_aviso_web"] = f"Não foi possível salvar no cache: {e}"
                    except Exception as e:
                        st.session_state["_aviso_web"] = f"Erro na busca web: {e}"

            st.session_state["_buscando_web"] = False
            st.rerun()

        if st.session_state.get("_aviso_web"):
            st.warning(st.session_state.pop("_aviso_web"))

    if "_resposta_web" in st.session_state:
        st.markdown("---")
        st.markdown(f"**Pergunta:** {st.session_state.get('_pergunta_web_ativa', '')}")
        st.markdown("### Resposta")
        with st.container(height=400):
            st.write(st.session_state["_resposta_web"])

        fontes = st.session_state.get("_fontes_web", [])
        if fontes:
            with st.expander(f"🔗 Fontes utilizadas ({len(fontes)})", expanded=True):
                for i, f in enumerate(fontes, 1):
                    titulo = f.get("title") or f.get("url", "")
                    url = f.get("url", "")
                    if url:
                        st.markdown(f"**[{i}]** [{titulo}]({url})")
                    else:
                        st.markdown(f"**[{i}]** {titulo}")

        try:
            pdf_bytes_web = gerar_pdf_bytes(
                st.session_state.get("_pergunta_web_ativa", ""),
                st.session_state["_resposta_web"],
                [],
            )
            st.download_button(
                "📄 Baixar PDF desta resposta",
                data=pdf_bytes_web,
                file_name=_nome_pdf(st.session_state.get("_pergunta_web_ativa", "")),
                mime="application/pdf",
                key="dl_pdf_web",
            )
        except Exception as e:
            st.warning(f"Erro ao gerar PDF: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 4 — Verificação de Conteúdo
# ══════════════════════════════════════════════════════════════════════════════

with st.expander("🚫 Verificação de Conteúdo", expanded=False):

    from content_guard import (
        PALAVRAS_PROIBIDAS_PADRAO,
        auditar_banco,
        auditar_banco_llm,
    )

    st.markdown("Verifique se os chunks já gravados no banco contêm conteúdo proibido.")

    # ── Seletor de arquivo ────────────────────────────────────────────────────
    pdfs_disponiveis = sorted(listar_pdfs_no_banco(), key=lambda p: (p["nome"] or "").lower())

    if not pdfs_disponiveis:
        st.warning("Nenhum PDF gravado no banco. Ingira um arquivo antes de verificar.")
        st.stop()

    opcoes_arquivo = {p["nome"]: p["source"] for p in pdfs_disponiveis}

    arquivo_selecionado_nome = st.selectbox(
        "Arquivo a verificar",
        list(opcoes_arquivo.keys()),
        key="arquivo_verificacao",
    )
    source_selecionado = opcoes_arquivo[arquivo_selecionado_nome]

    modo_verificacao = st.radio(
        "Modo de verificação",
        [
            "Busca exata (SQL — sem custo)",
            "Moderação por LLM (conceito — tokens de geração)",
        ],
        key="modo_verificacao",
    )

    # ── Opção 1: lista de palavras ────────────────────────────────────────────
    if modo_verificacao.startswith("Busca exata"):
        lista_texto = st.text_area(
            "Palavras proibidas (uma por linha)",
            value="\n".join(PALAVRAS_PROIBIDAS_PADRAO),
            height=120,
            key="lista_palavras_proibidas",
        )
        palavras_configuradas = [p.strip() for p in lista_texto.splitlines() if p.strip()]

    # ── Opção 2: critério em linguagem natural ────────────────────────────────
    else:
        criterio = st.text_input(
            "Descreva o que deve ser detectado",
            value="linguagem inadequada",
            key="criterio_llm",
            help="Ex.: linguagem ofensiva, conteúdo sexual, incitação à violência.",
        )
        st.slider("Chunks por lote (batch)", 5, 20, 10, key="batch_llm",
                  help="Quantos chunks enviar por chamada ao LLM. Mais = menos chamadas, prompt maior.")

    # ── Chave de cache — limpa se arquivo/modo/critério mudou ────────────────
    _arq_cache = source_selecionado or "todos"
    _modo_cache = "exata" if modo_verificacao.startswith("Busca exata") else "llm"
    _criterio_cache = (
        ", ".join(palavras_configuradas) if _modo_cache == "exata"
        else st.session_state.get("criterio_llm", "")
    )

    # Invalida cache se chave mudou
    _chave_atual = f"{_arq_cache}|{_modo_cache}|{_criterio_cache}"
    if st.session_state.get("_chave_verif") != _chave_atual:
        st.session_state.pop("_cache_verif", None)
        st.session_state.pop("_ocorrencias_conteudo", None)
        st.session_state["_chave_verif"] = _chave_atual

    # Verifica cache existente
    if "_cache_verif" not in st.session_state:
        try:
            st.session_state["_cache_verif"] = buscar_verificacao_cache(_arq_cache, _modo_cache, _criterio_cache)
        except Exception:
            st.session_state["_cache_verif"] = None

    cache_verif = st.session_state.get("_cache_verif")
    if cache_verif:
        data_fmt = cache_verif["data_verificacao"].strftime("%d/%m/%Y %H:%M")
        st.info(f"⚡ Resultado em cache de **{data_fmt}**. Nenhum token será gerado.")
        acao_verif = st.radio(
            "O que deseja fazer?",
            ["Usar resultado salvo", "Refazer verificação"],
            horizontal=True,
            key="acao_cache_verif",
        )
    else:
        acao_verif = "Refazer verificação"

    # ── Botão ─────────────────────────────────────────────────────────────────
    if st.button("🔍 Verificar conteúdo do banco", type="primary", key="btn_verificar_conteudo"):

        if cache_verif and acao_verif == "Usar resultado salvo":
            st.session_state["_ocorrencias_conteudo"] = cache_verif["ocorrencias"]
            st.session_state["_modo_verificacao"] = _modo_cache
            st.session_state["_label_verificacao"] = _criterio_cache
            st.session_state["_verif_id_atual"] = cache_verif["id"]
            st.session_state["_fonte_verif"] = "cache"
            st.rerun()

        elif modo_verificacao.startswith("Busca exata"):
            if not palavras_configuradas:
                st.warning("Adicione ao menos uma palavra para verificar.")
            else:
                with st.spinner("Varrendo chunks do banco..."):
                    try:
                        ocs = auditar_banco(PSYCOPG_URL, COLLECTION, palavras_configuradas, source=source_selecionado)
                        novo_id = salvar_verificacao_cache(_arq_cache, "exata", _criterio_cache, ocs)
                        st.session_state["_ocorrencias_conteudo"] = ocs
                        st.session_state["_modo_verificacao"] = "exata"
                        st.session_state["_label_verificacao"] = _criterio_cache
                        st.session_state["_verif_id_atual"] = novo_id
                        st.session_state["_fonte_verif"] = "nova"
                        st.session_state.pop("_cache_verif", None)
                    except Exception as e:
                        st.error(f"Erro ao varrer o banco: {e}")
                        st.session_state.pop("_ocorrencias_conteudo", None)

        else:  # Moderação por LLM
            criterio_val = st.session_state.get("criterio_llm", "").strip()
            if not criterio_val:
                st.warning("Descreva o critério de moderação.")
            else:
                with st.spinner("Moderando chunks com o LLM..."):
                    try:
                        if PROVIDER == "gemini":
                            from langchain_google_genai import ChatGoogleGenerativeAI
                            llm_mod = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
                        else:
                            from langchain_openai import ChatOpenAI
                            llm_mod = ChatOpenAI(model="gpt-4o-mini", temperature=0)

                        ocs, log_llm = auditar_banco_llm(
                            PSYCOPG_URL,
                            COLLECTION,
                            criterio_val,
                            llm_mod,
                            batch_size=st.session_state.get("batch_llm", 10),
                            source=source_selecionado,
                        )
                        novo_id = salvar_verificacao_cache(_arq_cache, "llm", criterio_val, ocs)
                        st.session_state["_ocorrencias_conteudo"] = ocs
                        st.session_state["_log_llm"] = log_llm
                        st.session_state["_modo_verificacao"] = "llm"
                        st.session_state["_label_verificacao"] = criterio_val
                        st.session_state["_verif_id_atual"] = novo_id
                        st.session_state["_fonte_verif"] = "nova"
                        st.session_state.pop("_cache_verif", None)
                    except Exception as e:
                        st.error(f"Erro na moderação LLM: {e}")
                        st.session_state.pop("_ocorrencias_conteudo", None)

    # ── Exibição dos resultados ───────────────────────────────────────────────
    if "_ocorrencias_conteudo" in st.session_state:
        ocorrencias = st.session_state["_ocorrencias_conteudo"]
        modo_usado  = st.session_state.get("_modo_verificacao", "exata")
        label       = st.session_state.get("_label_verificacao", "")

        st.markdown("---")
        verif_id_atual = st.session_state.get("_verif_id_atual")
        if f"_msg_aprov_{verif_id_atual}" in st.session_state:
            st.success(st.session_state.pop(f"_msg_aprov_{verif_id_atual}"))
        if not ocorrencias:
            st.success(f"Nenhum conteúdo proibido encontrado — critério: **{label}**")
        else:
            # Carrega aprovações manuais do banco (se a verificação já foi salva)
            verif_id_atual = st.session_state.get("_verif_id_atual")
            aprovados_manual = listar_aprovacoes_manuais(verif_id_atual) if verif_id_atual else {}
            n_aprovados_manual  = sum(1 for v in aprovados_manual.values() if v == "aprovado")
            n_confirmados_manual = sum(1 for v in aprovados_manual.values() if v == "reprovado_confirmado")
            n_revisados = len(aprovados_manual)
            n_total_ocs = len(ocorrencias)

            if n_aprovados_manual > 0 or n_confirmados_manual > 0:
                if n_revisados >= n_total_ocs and n_aprovados_manual >= n_total_ocs:
                    st.success(f"✅ Todas as {n_total_ocs} ocorrência(s) aprovadas manualmente.")
                elif n_revisados >= n_total_ocs:
                    partes = []
                    if n_aprovados_manual:
                        partes.append(f"{n_aprovados_manual} aprovada(s)")
                    if n_confirmados_manual:
                        partes.append(f"{n_confirmados_manual} com reprovação confirmada")
                    st.warning(f"⚠ Todas revisadas: {', '.join(partes)}.")
                else:
                    st.warning(f"⚠ {n_revisados} de {n_total_ocs} ocorrência(s) revisada(s) manualmente.")

            n_pendentes = n_total_ocs - n_revisados
            if n_pendentes > 0:
                st.error(f"{n_pendentes} chunk(s) pendente(s) de revisão — critério: **{label}**")

            if modo_usado == "exata":
                import re as _re

                def _destacar(trecho: str, palavras: list[str]) -> str:
                    resultado_txt = trecho
                    for p in palavras:
                        resultado_txt = _re.sub(
                            f"({_re.escape(p)})",
                            r"<mark>\1</mark>",
                            resultado_txt,
                            flags=_re.IGNORECASE,
                        )
                    return resultado_txt

                por_arquivo: dict[str, list] = {}
                for idx_oc, oc in enumerate(ocorrencias):
                    por_arquivo.setdefault(oc["nome"] or oc["arquivo"], []).append((idx_oc, oc))
                for nome_arq, chunks in por_arquivo.items():
                    with st.expander(f"📄 {nome_arq} — {len(chunks)} ocorrência(s)", expanded=True):
                        for idx_oc, oc in chunks:
                            tipo_revisao = aprovados_manual.get(idx_oc)
                            badge = (" ✅ aprovado manualmente" if tipo_revisao == "aprovado"
                                     else " 🚫 reprovação confirmada" if tipo_revisao == "reprovado_confirmado"
                                     else "")
                            st.markdown(
                                f"**Página:** {oc['pagina']} &nbsp;|&nbsp; "
                                f"**Palavras:** " + ", ".join(f"`{p}`" for p in oc["palavras"]) + badge
                            )
                            st.markdown(_destacar(oc["trecho"], oc["palavras"]), unsafe_allow_html=True)
                            _render_botao_aprovacao(verif_id_atual, idx_oc, tipo_revisao, f"exata_{idx_oc}", ocorrencias)
                            st.markdown("---")

            else:  # llm
                por_arquivo2: dict[str, list] = {}
                for idx_oc, oc in enumerate(ocorrencias):
                    por_arquivo2.setdefault(oc["nome"] or oc["arquivo"], []).append((idx_oc, oc))
                for nome_arq, chunks in por_arquivo2.items():
                    with st.expander(f"📄 {nome_arq} — {len(chunks)} chunk(s) reprovado(s)", expanded=True):
                        for idx_oc, oc in chunks:
                            tipo_revisao = aprovados_manual.get(idx_oc)
                            badge = (" ✅ aprovado manualmente" if tipo_revisao == "aprovado"
                                     else " 🚫 reprovação confirmada" if tipo_revisao == "reprovado_confirmado"
                                     else "")
                            st.markdown(
                                f"**Página:** {oc['pagina']} &nbsp;|&nbsp; "
                                f"**Motivo:** {oc['motivo'] or 'não especificado'}{badge}"
                            )
                            st.caption(oc["trecho"])
                            _render_botao_aprovacao(verif_id_atual, idx_oc, tipo_revisao, f"llm_{idx_oc}", ocorrencias)
                            st.markdown("---")

        # Botão de download PDF
        verif_id_atual = st.session_state.get("_verif_id_atual")
        aprovados_manual_dl = listar_aprovacoes_manuais(verif_id_atual) if verif_id_atual else {}
        n_ap_dl = sum(1 for v in aprovados_manual_dl.values() if v == "aprovado")
        n_rev_dl = len(aprovados_manual_dl)
        status_real = (
            "aprovado" if not ocorrencias
            else "aprovado_manualmente" if n_ap_dl >= len(ocorrencias)
            else "reprovado_confirmado" if n_rev_dl >= len(ocorrencias)
            else "reprovado"
        )
        nome_base = os.path.splitext(arquivo_selecionado_nome)[0]
        nome_pdf_verif = f"{nome_base}_{status_real}.pdf"
        try:
            pdf_verif = gerar_pdf_verificacao(
                arquivo_selecionado_nome, modo_usado, label, ocorrencias
            )
            st.download_button(
                "📄 Baixar PDF da verificação",
                data=pdf_verif,
                file_name=nome_pdf_verif,
                mime="application/pdf",
                key="dl_pdf_verificacao",
            )
        except Exception as e:
            st.warning(f"Erro ao gerar PDF: {e}")

        # Debug — sempre visível após verificação LLM, independente do resultado
        if modo_usado == "llm":
            log_llm = st.session_state.get("_log_llm", [])
            if log_llm:
                with st.expander("🔬 Debug — resposta bruta do LLM", expanded=True):
                    for entrada in log_llm:
                        st.markdown(f"**Lote {entrada['lote']}:**")
                        st.code(entrada["resposta_bruta"], language="text")


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 5 — Histórico de Verificações de Conteúdo
# ══════════════════════════════════════════════════════════════════════════════

with st.expander("🗂 Histórico de Verificações de Conteúdo", expanded=False):

    historico_verif = listar_verificacao_cache()

    if not historico_verif:
        st.info("Nenhuma verificação realizada ainda.")
    else:
        st.caption(f"Total: {len(historico_verif)} verificação(ões) salva(s)")

        filtro_verif = st.text_input(
            "🔎 Filtrar por arquivo ou critério",
            key="filtro_historico_verif",
            placeholder="Digite para filtrar...",
        )
        if filtro_verif:
            historico_verif = [
                r for r in historico_verif
                if filtro_verif.lower() in (r["arquivo"] or "").lower()
                or filtro_verif.lower() in (r["criterio"] or "").lower()
            ]
            st.caption(f"{len(historico_verif)} resultado(s) encontrado(s)")

        for reg in historico_verif:
            data_fmt     = reg["data_verificacao"].strftime("%d/%m/%Y %H:%M")
            modo_label   = "SQL" if reg["modo"] == "exata" else "LLM"
            status       = reg["status"] or "?"
            if status == "aprovado":
                badge_status = "✅ APROVADO"
            elif status == "aprovado manualmente":
                badge_status = "✅ APROVADO MANUALMENTE"
            elif status == "reprovado confirmado":
                badge_status = "🚫 REPROVADO CONFIRMADO"
            else:
                badge_status = "❌ REPROVADO"
            nome_exib    = os.path.basename(reg["arquivo"]) if reg["arquivo"] != "todos" else "Todos os arquivos"
            n_ocs        = len(reg["ocorrencias"])

            # Extrai motivos para exibir no cabeçalho
            if reg["modo"] == "exata":
                palavras_todas = []
                for oc in reg["ocorrencias"]:
                    palavras_todas.extend(oc.get("palavras", []))
                motivo_resumo = ", ".join(f'"{p}"' for p in sorted(set(palavras_todas))) if palavras_todas else "—"
            else:
                motivos = [oc.get("motivo", "") for oc in reg["ocorrencias"] if oc.get("motivo")]
                motivo_resumo = motivos[0][:80] + ("…" if len(motivos[0]) > 80 else "") if motivos else "—"

            with st.expander(
                f"🗓 {data_fmt}  [{modo_label}]  [{badge_status}]  —  {nome_exib}",
                expanded=False,
            ):
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    st.markdown(f"**Arquivo:** {nome_exib}")
                    st.markdown(f"**Modo:** {'Busca Exata (SQL)' if reg['modo'] == 'exata' else 'Moderação por LLM'}")
                with col_info2:
                    st.markdown(f"**Resultado:** {badge_status}")
                    st.markdown(f"**Critério:** {reg['criterio']}")

                if n_ocs:
                    st.markdown(f"**Ocorrências:** {n_ocs} chunk(s) reprovado(s)")
                    label_motivo = "Palavras encontradas" if reg["modo"] == "exata" else "Motivo"
                    st.markdown(f"**{label_motivo}:** {motivo_resumo}")

                if reg["ocorrencias"]:
                    aprovados_hist = listar_aprovacoes_manuais(reg["id"])
                    n_ap_hist   = sum(1 for v in aprovados_hist.values() if v == "aprovado")
                    n_conf_hist = sum(1 for v in aprovados_hist.values() if v == "reprovado_confirmado")
                    n_rev_hist  = len(aprovados_hist)

                    if f"_msg_aprov_{reg['id']}" in st.session_state:
                        st.success(st.session_state.pop(f"_msg_aprov_{reg['id']}"))

                    if n_rev_hist > 0:
                        if n_rev_hist >= n_ocs and n_ap_hist >= n_ocs:
                            st.success(f"✅ Todas as {n_ocs} ocorrência(s) aprovadas manualmente.")
                        elif n_rev_hist >= n_ocs:
                            partes = []
                            if n_ap_hist:   partes.append(f"{n_ap_hist} aprovada(s)")
                            if n_conf_hist: partes.append(f"{n_conf_hist} com reprovação confirmada")
                            st.warning(f"⚠ Todas revisadas: {', '.join(partes)}.")
                        else:
                            st.warning(f"⚠ {n_rev_hist} de {n_ocs} ocorrência(s) revisada(s) manualmente.")

                    with st.expander(f"Ver ocorrências ({n_ocs})", expanded=False):
                        for idx_oc, oc in enumerate(reg["ocorrencias"]):
                            tipo_revisao_h = aprovados_hist.get(idx_oc)
                            if reg["modo"] == "exata":
                                detalhe = "**Palavras:** " + ", ".join(f"`{p}`" for p in oc.get("palavras", []))
                            else:
                                detalhe = f"**Motivo:** {oc.get('motivo', '')}"
                            badge_ap = (" &nbsp;✅ *aprovado manualmente*" if tipo_revisao_h == "aprovado"
                                        else " &nbsp;🚫 *reprovação confirmada*" if tipo_revisao_h == "reprovado_confirmado"
                                        else "")
                            st.markdown(
                                f"**[{idx_oc+1}] Arquivo:** {oc.get('nome', nome_exib)} &nbsp;|&nbsp; "
                                f"**Página:** {oc.get('pagina','?')} &nbsp;|&nbsp; {detalhe}{badge_ap}"
                            )
                            st.caption((oc.get("trecho") or "")[:300] + "...")
                            _render_botao_aprovacao(reg["id"], idx_oc, tipo_revisao_h, f"hist_{reg['id']}_{idx_oc}", reg["ocorrencias"])
                            st.markdown("---")

                col_pdf, col_del = st.columns([1, 1])
                with col_pdf:
                    try:
                        nome_base = os.path.splitext(nome_exib)[0]
                        pdf_hist  = gerar_pdf_verificacao(
                            nome_exib, reg["modo"], reg["criterio"], reg["ocorrencias"]
                        )
                        st.download_button(
                            "📄 Baixar PDF",
                            data=pdf_hist,
                            file_name=f"{nome_base}_{reg['status']}.pdf",
                            mime="application/pdf",
                            key=f"dl_verif_{reg['id']}",
                        )
                    except Exception as e:
                        st.warning(f"Erro ao gerar PDF: {e}")
                with col_del:
                    if st.button("🗑️ Apagar este registro", key=f"del_verif_{reg['id']}"):
                        try:
                            deletar_verificacao_cache_por_id(reg["id"])
                            st.success("Registro removido.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao remover: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SEÇÃO 6 — Histórico de Perguntas e Respostas
# ══════════════════════════════════════════════════════════════════════════════

with st.expander("📋 Histórico de Perguntas e Respostas", expanded=False):

    registros = listar_cache()

    if not registros:
        st.info("Nenhuma pergunta salva ainda.")
    else:
        st.caption(f"Total: {len(registros)} registro(s) salvos")

        # Filtro por texto
        filtro = st.text_input("🔎 Filtrar por texto", key="filtro_historico",
                               placeholder="Digite para filtrar perguntas...")
        if filtro:
            registros = [r for r in registros
                         if filtro.lower() in r["pergunta"].lower()
                         or filtro.lower() in r["resposta"].lower()]
            st.caption(f"{len(registros)} resultado(s) encontrado(s)")

        for reg in registros:
            data_fmt = reg["data_consulta"].strftime("%d/%m/%Y %H:%M")
            tipo_badge = "🌐 Web" if reg.get("tipo") == "web" else "📄 RAG"
            with st.expander(f"🗓 {data_fmt}  [{tipo_badge}]  —  {reg['pergunta'][:80]}"):
                st.markdown(f"**Pergunta:** {reg['pergunta']}")
                st.markdown("**Resposta:**")
                st.write(reg["resposta"])

                if reg.get("chunks"):
                    if reg.get("tipo") == "web":
                        with st.expander(f"🔗 Fontes ({len(reg['chunks'])} links)"):
                            for i, fonte in enumerate(reg["chunks"], 1):
                                titulo = fonte.get("title") or fonte.get("url", "")
                                url = fonte.get("url", "")
                                if url:
                                    st.markdown(f"**[{i}]** [{titulo}]({url})")
                                else:
                                    st.markdown(f"**[{i}]** {titulo}")
                    else:
                        with st.expander(f"Ver chunks ({len(reg['chunks'])} recuperados)"):
                            for i, chunk in enumerate(reg["chunks"], 1):
                                meta = chunk.get("metadata", {})
                                nome = meta.get("original_name") or os.path.basename(meta.get("source", "?"))
                                st.markdown(
                                    f"**[{i}]** Score: `{chunk.get('score', 0):.4f}` | "
                                    f"Arquivo: `{nome}` | "
                                    f"Página: `{meta.get('page', '?')}`"
                                )
                                st.caption(chunk.get("content", "")[:300] + "...")

                col_pdf, col_del = st.columns([1, 1])
                with col_pdf:
                    try:
                        pdf_bytes = gerar_pdf_bytes(
                            reg["pergunta"], reg["resposta"], reg.get("chunks", [])
                        )
                        st.download_button(
                            "📄 Baixar PDF",
                            data=pdf_bytes,
                            file_name=_nome_pdf(reg["pergunta"]),
                            mime="application/pdf",
                            key=f"dl_pdf_{reg['id']}",
                        )
                    except Exception as e:
                        st.warning(f"Erro ao gerar PDF: {e}")
                with col_del:
                    if st.button("🗑️ Apagar este registro", key=f"del_cache_{reg['id']}"):
                        try:
                            deletar_cache_por_id(reg["id"])
                            st.success("Registro removido.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao remover: {e}")
