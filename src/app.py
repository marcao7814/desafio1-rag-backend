"""
app.py — Servidor Flask: orquestrador principal do sistema RAG.

Gera HTML no servidor via Jinja2 e expõe API REST para interações dinâmicas.

Executar:
    python src/app.py
ou via ini.bat
"""

import json
import os
import pathlib
import re
import sys
import tempfile
from io import BytesIO

from flask import (
    Flask,
    abort,
    jsonify,
    render_template,
    request,
    send_file,
)
from dotenv import load_dotenv

# Garante que src/ está no path para importar os módulos locais
sys.path.insert(0, str(pathlib.Path(__file__).parent))

load_dotenv()

# ── Importações dos módulos de negócio ───────────────────────────────────────
import db  # camada de banco de dados

# ── Configuração do Flask ────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB por upload

PORT      = int(os.getenv("FLASK_PORT", 5000))
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash-lite")
PROVIDER  = os.getenv("LLM_PROVIDER", "gemini").lower()


# ── Lazy-imports de módulos pesados (evita lentidão no startup) ──────────────
_llm        = None
_vectorstore = None
_ingerir_fn  = None


def _get_llm():
    global _llm
    if _llm is None:
        if PROVIDER == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            _llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
        else:
            from langchain_openai import ChatOpenAI
            _llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    return _llm


def _get_vectorstore():
    global _vectorstore
    if _vectorstore is None:
        from search import vectorstore
        _vectorstore = vectorstore
    return _vectorstore


def _get_ingerir():
    global _ingerir_fn
    if _ingerir_fn is None:
        from ingest import ingerir
        _ingerir_fn = ingerir
    return _ingerir_fn


# ── Inicialização ─────────────────────────────────────────────────────────────

@app.before_request
def _startup():
    """Garante que as tabelas existam antes da primeira requisição."""
    global _startup_done
    if not getattr(app, "_startup_done", False):
        db.criar_tabela_cache()
        app._startup_done = True


# ── Helpers ───────────────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """CONTEXTO:
{contexto}

REGRAS:
- Responda somente com base no CONTEXTO.
- Se a informação não estiver explicitamente no CONTEXTO, responda:
  "Não tenho informações necessárias para responder sua pergunta."
- Nunca invente ou use conhecimento externo.

PERGUNTA DO USUÁRIO:
{pergunta}

RESPONDA A "PERGUNTA DO USUÁRIO"
"""


def _buscar_rag(pergunta: str, sources: list[str] | None = None):
    """Executa pipeline RAG completo. Retorna (resposta, resultados)."""
    vs = _get_vectorstore()
    filtro = {"source": {"$in": sources}} if sources else None
    resultados = vs.similarity_search_with_score(pergunta, k=15, filter=filtro)

    if not resultados:
        return "Não tenho informações necessárias para responder sua pergunta.", []

    contexto = "\n\n---\n\n".join(doc.page_content for doc, _ in resultados)
    prompt   = PROMPT_TEMPLATE.format(contexto=contexto, pergunta=pergunta)
    llm      = _get_llm()
    resposta = llm.invoke(prompt).content
    return resposta, resultados


def _gerar_pdf_resposta(pergunta: str, resposta: str, chunks: list) -> bytes:
    """Gera PDF com pergunta, resposta e chunks."""
    from datetime import datetime
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER

    buffer  = BytesIO()
    doc_pdf = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )
    styles    = getSampleStyleSheet()
    titulo_st = ParagraphStyle("T", parent=styles["Title"], alignment=TA_CENTER, spaceAfter=4*mm)
    h2_st     = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=4*mm, spaceAfter=2*mm)
    body_st   = styles["Normal"]
    small_st  = ParagraphStyle("S", parent=styles["Normal"], fontSize=9, leading=13)
    hr        = HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#AAAAAA"))

    story = [
        Paragraph("RAG — Resposta Gerada", titulo_st),
        Paragraph(f"<b>Data:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", body_st),
        Spacer(1, 4*mm), hr,
        Paragraph("Pergunta", h2_st),
        Paragraph(pergunta.replace("&", "&amp;").replace("<", "&lt;"), body_st),
        Spacer(1, 4*mm), hr,
        Paragraph("Resposta", h2_st),
    ]
    for linha in resposta.split("\n"):
        txt = linha.strip().replace("&", "&amp;").replace("<", "&lt;")
        story.append(Paragraph(txt, body_st) if txt else Spacer(1, 2*mm))

    if chunks:
        story += [Spacer(1, 4*mm), hr, Paragraph(f"Chunks Utilizados ({len(chunks)})", h2_st)]
        for i, chunk in enumerate(chunks, 1):
            if isinstance(chunk, dict):
                content = chunk.get("content", "")
                score   = chunk.get("score", 0)
                meta    = chunk.get("metadata", {})
            else:
                doc_obj, score = chunk
                content = doc_obj.page_content
                meta    = doc_obj.metadata
            nome   = meta.get("original_name") or os.path.basename(meta.get("source") or "?")
            pagina = meta.get("page", "?")
            story.append(Paragraph(
                f"<b>[{i}]</b> Score: {float(score):.4f} | {nome} | Pág. {pagina}", body_st,
            ))
            trecho = (content[:500] + "…") if len(content) > 500 else content
            story.append(Paragraph(
                trecho.replace("&", "&amp;").replace("<", "&lt;").replace("\n", " "), small_st,
            ))
            story.append(Spacer(1, 3*mm))

    doc_pdf.build(story)
    return buffer.getvalue()


def _gerar_pdf_verificacao(nome_arquivo: str, modo: str, criterio: str, ocorrencias: list) -> bytes:
    """Gera PDF com o resultado da verificação de conteúdo."""
    from datetime import datetime
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER

    aprovado  = len(ocorrencias) == 0
    status    = "APROVADO" if aprovado else "REPROVADO"
    buffer    = BytesIO()
    doc_pdf   = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=20*mm, leftMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )
    styles    = getSampleStyleSheet()
    titulo_st = ParagraphStyle("T", parent=styles["Title"], alignment=TA_CENTER, spaceAfter=4*mm)
    h2_st     = ParagraphStyle("H2", parent=styles["Heading2"], spaceBefore=4*mm, spaceAfter=2*mm)
    body_st   = styles["Normal"]
    small_st  = ParagraphStyle("S", parent=styles["Normal"], fontSize=9, leading=13)
    cor       = colors.HexColor("#1a7f37") if aprovado else colors.HexColor("#c0392b")
    status_st = ParagraphStyle("St", parent=styles["Title"], alignment=TA_CENTER,
                                textColor=cor, fontSize=20, spaceAfter=4*mm)
    hr        = HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#AAAAAA"))

    def _esc(t): return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story = [
        Paragraph("Verificação de Conteúdo — RAG", titulo_st),
        Paragraph(status, status_st),
        Paragraph(f"<b>Data:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", body_st),
        Spacer(1, 2*mm), hr,
        Paragraph("Informações", h2_st),
        Paragraph(f"<b>Arquivo:</b> {nome_arquivo}", body_st),
        Paragraph(f"<b>Modo:</b> {'Busca Exata (SQL)' if modo=='exata' else 'Moderação por LLM'}", body_st),
        Paragraph(f"<b>Critério:</b> {_esc(criterio)}", body_st),
        Spacer(1, 4*mm), hr,
    ]

    if aprovado:
        story.append(Paragraph("Resultado", h2_st))
        story.append(Paragraph("Nenhum conteúdo proibido encontrado. Aprovado.", body_st))
    else:
        story.append(Paragraph(f"Ocorrências ({len(ocorrencias)} chunk(s) reprovado(s))", h2_st))
        for i, oc in enumerate(ocorrencias, 1):
            story.append(Paragraph(f"<b>[{i}] Pág. {oc.get('pagina','?')}</b>", body_st))
            if modo == "exata":
                words = oc.get("palavras", [])
                story.append(Paragraph(f"<b>Palavras:</b> {', '.join(words)}", body_st))
            else:
                story.append(Paragraph(f"<b>Motivo:</b> {_esc(oc.get('motivo',''))}", body_st))
            trecho = (oc.get("trecho","") or "")[:500]
            story.append(Paragraph(_esc(trecho).replace("\n"," "), small_st))
            story.append(Spacer(1, 3*mm))

    doc_pdf.build(story)
    return buffer.getvalue()


def _safe_filename(s: str) -> str:
    slug = re.sub(r'[\\/:*?"<>|]', '', s)
    slug = re.sub(r'\s+', '_', slug.strip())[:30].rstrip('_')
    return slug or "resposta"


# ═══════════════════════════════════════════════════════════════════════════════
# ROTAS — Página principal (HTML gerado pelo servidor)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """Gera e serve o HTML completo da aplicação."""
    pdfs  = db.listar_pdfs_no_banco()
    cache = db.listar_cache()
    verif = db.listar_verificacao_cache()

    total_chunks = sum(p["chunks"] for p in pdfs)
    stats = {
        "total_pdfs":    len(pdfs),
        "total_chunks":  total_chunks,
        "total_perguntas": len(cache),
        "total_verif":   len(verif),
    }
    return render_template(
        "index.html",
        pdfs=pdfs,
        stats=stats,
        modelo=LLM_MODEL,
        provider=PROVIDER,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# API — PDFs
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/pdfs", methods=["GET"])
def api_listar_pdfs():
    return jsonify(db.listar_pdfs_no_banco())


@app.route("/api/pdfs/upload", methods=["POST"])
def api_upload_pdfs():
    arquivos = request.files.getlist("files")
    if not arquivos:
        return jsonify({"erro": "Nenhum arquivo enviado."}), 400

    arquivos = arquivos[:5]
    substituir = request.form.get("modo") == "substituir"

    ingerir = _get_ingerir()
    total   = 0
    erros   = []

    for i, arq in enumerate(arquivos):
        if not arq.filename.lower().endswith(".pdf"):
            erros.append(f"{arq.filename}: não é PDF.")
            continue
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            arq.save(tmp.name)
            tmp_path = tmp.name
        try:
            pre_delete = substituir and (i == 0)
            n     = ingerir(tmp_path, nome_original=arq.filename, pre_delete=pre_delete)
            total += n
        except Exception as e:
            erros.append(f"{arq.filename}: {e}")
        finally:
            os.unlink(tmp_path)

    pdfs = db.listar_pdfs_no_banco()
    return jsonify({
        "chunks_gravados": total,
        "erros":           erros,
        "pdfs":            pdfs,
    })


@app.route("/api/pdfs/<path:source>", methods=["DELETE"])
def api_deletar_pdf(source):
    n = db.deletar_pdf_do_banco(source)
    return jsonify({"chunks_removidos": n, "pdfs": db.listar_pdfs_no_banco()})


@app.route("/api/pdfs", methods=["DELETE"])
def api_deletar_todos_pdfs():
    n = db.deletar_todos_pdfs()
    return jsonify({"chunks_removidos": n, "pdfs": []})


# ═══════════════════════════════════════════════════════════════════════════════
# API — Busca RAG
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/busca/rag", methods=["POST"])
def api_busca_rag():
    data     = request.get_json(force=True)
    pergunta = (data.get("pergunta") or "").strip()
    sources  = data.get("sources") or None  # lista de source paths selecionados

    if not pergunta:
        return jsonify({"erro": "Pergunta vazia."}), 400

    # Verifica cache
    cache = db.buscar_cache(pergunta, tipo="rag")
    if cache and not data.get("ignorar_cache"):
        return jsonify({
            "resposta":      cache["resposta"],
            "chunks":        cache["chunks"],
            "do_cache":      True,
            "data_consulta": cache["data_consulta"].strftime("%d/%m/%Y %H:%M") if hasattr(cache["data_consulta"], "strftime") else str(cache["data_consulta"]),
            "cache_id":      cache["id"],
        })

    try:
        resposta, resultados = _buscar_rag(pergunta, sources=sources)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

    # Serializa chunks para JSON
    chunks_serializados = [
        {
            "content":  doc.page_content,
            "score":    float(score),
            "metadata": doc.metadata,
        }
        for doc, score in resultados
    ]

    cache_id = db.salvar_cache(pergunta, resposta, resultados, tipo="rag")

    return jsonify({
        "resposta":  resposta,
        "chunks":    chunks_serializados,
        "do_cache":  False,
        "cache_id":  cache_id,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# API — Busca Web
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/busca/web", methods=["POST"])
def api_busca_web():
    data     = request.get_json(force=True)
    pergunta = (data.get("pergunta") or "").strip()

    if not pergunta:
        return jsonify({"erro": "Pergunta vazia."}), 400

    cache = db.buscar_cache(pergunta, tipo="web")
    if cache and not data.get("ignorar_cache"):
        return jsonify({
            "resposta":      cache["resposta"],
            "fontes":        cache["chunks"],
            "do_cache":      True,
            "data_consulta": cache["data_consulta"].strftime("%d/%m/%Y %H:%M") if hasattr(cache["data_consulta"], "strftime") else str(cache["data_consulta"]),
            "cache_id":      cache["id"],
        })

    try:
        from web_search import buscar_na_web
        resposta, fontes = buscar_na_web(pergunta)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

    cache_id = db.salvar_cache(pergunta, resposta, fontes, tipo="web")

    return jsonify({
        "resposta":  resposta,
        "fontes":    fontes,
        "do_cache":  False,
        "cache_id":  cache_id,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# API — Verificação de conteúdo
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/verificar", methods=["POST"])
def api_verificar():
    data    = request.get_json(force=True)
    arquivo = data.get("arquivo")      # source path do PDF
    nome    = data.get("nome", arquivo)
    modo    = data.get("modo", "exata")
    criterio = (data.get("criterio") or "").strip()

    if not arquivo or not criterio:
        return jsonify({"erro": "Arquivo e critério são obrigatórios."}), 400

    try:
        if modo == "exata":
            from content_guard import auditar_banco
            palavras = [p.strip() for p in criterio.splitlines() if p.strip()]
            raw = auditar_banco(
                psycopg_url=db.PSYCOPG_URL,
                collection=db.COLLECTION,
                lista=palavras,
                source=arquivo,
            )
            # Separa falsos positivos conhecidos das ocorrências reais
            ocorrencias       = []
            auto_aprovados    = []
            for oc in raw:
                fp_match = None
                for p in oc["palavras"]:
                    fp_match = db.checar_falso_positivo(p, oc["trecho"])
                    if fp_match:
                        break
                item = {
                    "arquivo":  oc["arquivo"],
                    "nome":     oc["nome"],
                    "pagina":   oc["pagina"],
                    "trecho":   oc["trecho"],
                    "palavras": oc["palavras"],
                }
                if fp_match:
                    item["auto_aprovado"] = True
                    item["fp_observacao"] = fp_match["observacao"]
                    auto_aprovados.append(item)
                else:
                    ocorrencias.append(item)
        else:
            from content_guard import auditar_banco_llm
            llm = _get_llm()
            resultado   = auditar_banco_llm(
                psycopg_url=db.PSYCOPG_URL,
                collection=db.COLLECTION,
                criterio=criterio,
                llm=llm,
                source=arquivo,
            )
            ocorrencias    = resultado[0] if isinstance(resultado, tuple) else resultado
            auto_aprovados = []
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

    verification_id = db.salvar_verificacao_cache(arquivo, modo, criterio, ocorrencias)

    # Registra auto-aprovações no banco (tipo='falso_positivo')
    for idx, oc in enumerate(auto_aprovados):
        db.aprovar_chunk_manual(verification_id, -(idx + 1), oc.get("fp_observacao", ""), "falso_positivo")

    return jsonify({
        "verification_id": verification_id,
        "ocorrencias":     ocorrencias,
        "auto_aprovados":  auto_aprovados,
        "total":           len(ocorrencias),
        "status":          "aprovado" if not ocorrencias else "reprovado",
        "nome_arquivo":    nome,
    })


@app.route("/api/verificar/<int:vid>/revisar", methods=["POST"])
def api_revisar(vid):
    data         = request.get_json(force=True)
    chunk_indice = data.get("chunk_indice")
    tipo         = data.get("tipo", "aprovado")  # 'aprovado' | 'reprovado_confirmado'
    observacao   = data.get("observacao", "")
    ocorrencias  = data.get("ocorrencias")

    if chunk_indice is None:
        return jsonify({"erro": "chunk_indice obrigatório."}), 400

    try:
        if ocorrencias:
            n = db.aprovar_por_mesmo_motivo(vid, chunk_indice, observacao, ocorrencias, tipo)
        else:
            db.aprovar_chunk_manual(vid, chunk_indice, observacao, tipo)
            n = 1
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

    aprovacoes = db.listar_aprovacoes_manuais(vid)
    return jsonify({"revisados": n, "aprovacoes": aprovacoes})


@app.route("/api/verificar/<int:vid>", methods=["DELETE"])
def api_deletar_verificacao(vid):
    n = db.deletar_verificacao_cache_por_id(vid)
    return jsonify({"removidos": n})


# ═══════════════════════════════════════════════════════════════════════════════
# API — Histórico
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/historico/perguntas", methods=["GET"])
def api_historico_perguntas():
    return jsonify(db.listar_cache())


@app.route("/api/historico/perguntas/<int:rid>", methods=["DELETE"])
def api_deletar_pergunta(rid):
    n = db.deletar_cache_por_id(rid)
    return jsonify({"removidos": n})


@app.route("/api/historico/verificacoes", methods=["GET"])
def api_historico_verificacoes():
    registros = db.listar_verificacao_cache()
    # Inclui aprovações manuais para cada registro
    for reg in registros:
        reg["aprovacoes"] = db.listar_aprovacoes_manuais(reg["id"])
    return jsonify(registros)


# ═══════════════════════════════════════════════════════════════════════════════
# API — Download de PDFs gerados
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/download/resposta/<int:cache_id>", methods=["GET"])
def api_download_resposta(cache_id):
    cache = db.buscar_cache_por_id(cache_id)
    if not cache:
        abort(404)
    pdf_bytes = _gerar_pdf_resposta(cache["pergunta"], cache["resposta"], cache["chunks"])
    nome_arq  = _safe_filename(cache["pergunta"]) + ".pdf"
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nome_arq,
    )


@app.route("/api/download/verificacao/<int:vid>", methods=["GET"])
def api_download_verificacao(vid):
    registros = db.listar_verificacao_cache()
    reg = next((r for r in registros if r["id"] == vid), None)
    if not reg:
        abort(404)
    pdf_bytes = _gerar_pdf_verificacao(
        reg["arquivo"], reg["modo"], reg["criterio"], reg["ocorrencias"]
    )
    nome_arq = f"verificacao_{vid}.pdf"
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nome_arq,
    )


# ── Função extra em db.py que falta: buscar por id ───────────────────────────
# Adicionamos inline aqui para não editar db.py novamente
def _buscar_cache_por_id(cache_id: int) -> dict | None:
    import psycopg
    sql = "SELECT id, pergunta, resposta, chunks, data_consulta, tipo FROM search_cache WHERE id = %s"
    with psycopg.connect(db.PSYCOPG_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (cache_id,))
            row = cur.fetchone()
    if row:
        return {
            "id": row[0], "pergunta": row[1], "resposta": row[2],
            "chunks": row[3] or [], "data_consulta": row[4], "tipo": row[5],
        }
    return None

# Monkey-patch para ficar acessível como db.buscar_cache_por_id
db.buscar_cache_por_id = _buscar_cache_por_id


# ═══════════════════════════════════════════════════════════════════════════════
# Ponto de entrada
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print(f"  RAG — Servidor Flask iniciando na porta {PORT}")
    print(f"  Acesse: http://localhost:{PORT}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=PORT, debug=False)
