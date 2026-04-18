/* ───────────────────────────────────────────────────────────────────────────
   app.js — cliente do sistema RAG (Flask back-end)
   Todas as interações usam fetch() para chamar a API REST Python.
─────────────────────────────────────────────────────────────────────────── */

"use strict";

/* ── Navegação ───────────────────────────────────────────────────────────── */
function go(id, el) {
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".nav-item[data-panel]").forEach(n => n.classList.remove("active"));
  const panel = document.getElementById("panel-" + id);
  if (panel) panel.classList.add("active");
  if (el) el.classList.add("active");
  closeSidebar();
  // Carrega dados da aba ao abrir
  if (id === "hist")      carregarHistoricoPerguntas();
  if (id === "histverif") carregarHistoricoVerificacoes();
}

/* ── Sidebar mobile ──────────────────────────────────────────────────────── */
function toggleSidebar() {
  document.getElementById("sidebar").classList.toggle("open");
  document.getElementById("overlay").classList.toggle("on");
}
function closeSidebar() {
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("overlay").classList.remove("on");
}
function toggleH(hd) { hd.nextElementSibling.classList.toggle("open"); }

/* ── Toast ───────────────────────────────────────────────────────────────── */
function toast(msg, isErr = false) {
  const el = document.createElement("div");
  el.className = "toast" + (isErr ? " err" : "");
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

/* ── API helper ──────────────────────────────────────────────────────────── */
async function api(method, url, body = null) {
  const opts = { method, headers: {} };
  if (body && !(body instanceof FormData)) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  } else if (body) {
    opts.body = body;
  }
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.erro || `HTTP ${res.status}`);
  return data;
}

/* ─────────────────────────────────────────────────────────────────────────
   PAINEL — PDFs
───────────────────────────────────────────────────────────────────────── */
let uploadFiles = [];

document.addEventListener("DOMContentLoaded", () => {
  const zone = document.getElementById("uploadZone");
  const fi   = document.getElementById("fileInput");
  if (!zone) return;

  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag"));
  zone.addEventListener("drop", e => {
    e.preventDefault(); zone.classList.remove("drag");
    addFiles(e.dataTransfer.files);
  });
  zone.addEventListener("click", () => fi.click());
  fi.addEventListener("change", () => addFiles(fi.files));
});

function addFiles(fileList) {
  const arr = Array.from(fileList).filter(f => f.name.toLowerCase().endsWith(".pdf"));
  uploadFiles = [...uploadFiles, ...arr].slice(0, 5);
  renderFileList();
}
function removeFile(i) { uploadFiles.splice(i, 1); renderFileList(); }

function renderFileList() {
  const el  = document.getElementById("fileList");
  const btn = document.getElementById("btnIngerir");
  el.innerHTML = uploadFiles.map((f, i) =>
    `<div class="flex gap8 mt8">
       <span>📄 ${f.name}</span>
       <span class="tag">${(f.size / 1024).toFixed(1)} KB</span>
       <button class="btn btn-secondary btn-sm" style="margin-left:auto;padding:2px 8px"
               onclick="removeFile(${i})">✕</button>
     </div>`
  ).join("");
  btn.disabled = !uploadFiles.length;
}

async function ingerirPdfs() {
  if (!uploadFiles.length) return;
  const btn  = document.getElementById("btnIngerir");
  const spin = document.getElementById("spinIngest");
  const msg  = document.getElementById("ingestMsg");
  const modo = document.querySelector('input[name="modo"]:checked').value;

  btn.disabled = true; spin.classList.add("on"); msg.innerHTML = "";

  const form = new FormData();
  uploadFiles.forEach(f => form.append("files", f));
  form.append("modo", modo);

  try {
    const data = await api("POST", "/api/pdfs/upload", form);
    msg.innerHTML = `<div class="alert alert-success mt8">✅ ${data.chunks_gravados} chunk(s) gravados com sucesso.</div>`;
    if (data.erros?.length) {
      msg.innerHTML += `<div class="alert alert-warning mt8">⚠ ${data.erros.join("<br>")}</div>`;
    }
    uploadFiles = []; renderFileList();
    renderTabelaPdfs(data.pdfs);
    atualizarPdfsBusca(data.pdfs);
    atualizarStatsTop(data.pdfs);
  } catch (e) {
    msg.innerHTML = `<div class="alert alert-error mt8">❌ ${e.message}</div>`;
  } finally {
    spin.classList.remove("on"); btn.disabled = false;
  }
}

function renderTabelaPdfs(pdfs) {
  const tbody = document.getElementById("tblPdfsBody");
  const total = document.getElementById("totalPdfsTag");
  if (!tbody) return;
  total.textContent = pdfs.length + " arquivo(s)";
  if (!pdfs.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="muted" style="text-align:center;padding:20px">Nenhum PDF no banco.</td></tr>';
    return;
  }
  tbody.innerHTML = pdfs.map(p =>
    `<tr>
       <td>${p.nome}</td>
       <td><span class="tag">${p.chunks}</span></td>
       <td>
         <button class="btn btn-danger btn-sm" onclick="deletarPdf('${encodeURIComponent(p.source)}', this)">🗑️</button>
       </td>
     </tr>`
  ).join("");
}

async function deletarPdf(sourceEnc, btn) {
  if (!confirm("Remover este PDF do banco vetorial?")) return;
  const source = decodeURIComponent(sourceEnc);
  try {
    const data = await api("DELETE", `/api/pdfs/${encodeURIComponent(source)}`);
    toast(`✅ ${data.chunks_removidos} chunk(s) removidos.`);
    renderTabelaPdfs(data.pdfs);
    atualizarPdfsBusca(data.pdfs);
    atualizarStatsTop(data.pdfs);
  } catch (e) { toast(e.message, true); }
}

async function deletarTodosPdfs() {
  if (!document.getElementById("chkConfirmAll").checked) return;
  if (!confirm("Apagar TODOS os PDFs do banco? Esta ação é irreversível.")) return;
  try {
    const data = await api("DELETE", "/api/pdfs");
    toast(`✅ ${data.chunks_removidos} chunk(s) removidos.`);
    renderTabelaPdfs([]);
    atualizarPdfsBusca([]);
    atualizarStatsTop([]);
    document.getElementById("chkConfirmAll").checked = false;
    document.getElementById("btnApagarTodos").disabled = true;
  } catch (e) { toast(e.message, true); }
}

function atualizarStatsTop(pdfs) {
  const el = document.getElementById("statTotalPdfs");
  const ec = document.getElementById("statTotalChunks");
  if (el) el.textContent = pdfs.length;
  if (ec) ec.textContent = pdfs.reduce((s, p) => s + p.chunks, 0);
}

/* ─────────────────────────────────────────────────────────────────────────
   PAINEL — Busca (RAG + Internet)
───────────────────────────────────────────────────────────────────────── */
let fonteAtual = "rag";

function setFonte(f) {
  fonteAtual = f;
  document.getElementById("btnFonteRag").classList.toggle("active", f === "rag");
  document.getElementById("btnFonteWeb").classList.toggle("active", f === "web");
  document.getElementById("ragPdfsPanel").classList.toggle("hidden", f !== "rag");
  document.getElementById("avisoWeb").classList.toggle("hidden", f !== "web");
  document.getElementById("lblPerguntaBusca").textContent =
    f === "rag" ? "Sua pergunta sobre os documentos" : "Sua pergunta (busca na internet)";
  document.getElementById("inputBusca").placeholder =
    f === "rag" ? "Ex.: Qual é o prazo de entrega do contrato?" : "Ex.: Qual é a cotação do dólar hoje?";
  // Limpa resultados
  ["resBuscaRag","resBuscaWeb","cacheBusca"].forEach(id => {
    document.getElementById(id)?.classList.add("hidden");
  });
  document.getElementById("inputBusca").value = "";
  document.getElementById("btnBuscar").disabled = true;
}

function atualizarPdfsBusca(pdfs) {
  const lista = document.getElementById("pdfListaBusca");
  if (!lista) return;
  if (!pdfs.length) {
    lista.innerHTML = '<div class="muted caption">Nenhum PDF disponível. Faça upload na aba PDFs.</div>';
    return;
  }
  lista.innerHTML = pdfs.map(p =>
    `<label class="pdf-item">
       <input type="checkbox" checked onchange="updatePdfCount()" data-source="${p.source}"/>
       <span class="pdf-name">📄 ${p.nome}</span>
       <span class="pdf-chunks">${p.chunks} chunks</span>
     </label>`
  ).join("");
  updatePdfCount();
}

function updatePdfCount() {
  const boxes = document.querySelectorAll("#pdfListaBusca input[type=checkbox]");
  const sel   = Array.from(boxes).filter(b => b.checked).length;
  const badge = document.getElementById("pdfsSelCount");
  const warn  = document.getElementById("noPdfWarn");
  if (badge) badge.textContent = sel + " selecionado" + (sel !== 1 ? "s" : "");
  if (warn)  warn.style.display = (fonteAtual === "rag" && sel === 0) ? "block" : "none";
  verificarPodeBuscar();
}

function verificarPodeBuscar() {
  const v    = (document.getElementById("inputBusca")?.value || "").trim();
  const boxes = document.querySelectorAll("#pdfListaBusca input[type=checkbox]");
  const sel   = Array.from(boxes).filter(b => b.checked).length;
  const pdfOk = fonteAtual === "web" || sel > 0;
  document.getElementById("btnBuscar").disabled = !v || !pdfOk;
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("inputBusca")?.addEventListener("input", verificarPodeBuscar);
});

async function buscar() {
  const pergunta = document.getElementById("inputBusca").value.trim();
  if (!pergunta) return;

  const btnB = document.getElementById("btnBuscar");
  const spin = document.getElementById("spinBusca");
  const spinTxt = document.getElementById("spinBuscaTxt");
  btnB.disabled = true; spin.classList.add("on");
  document.getElementById("resBuscaRag").classList.add("hidden");
  document.getElementById("resBuscaWeb").classList.add("hidden");
  document.getElementById("cacheBusca").classList.add("hidden");

  const ignorarCache = document.querySelector('input[name="acaoBusca"]:checked')?.value === "refazer";

  try {
    if (fonteAtual === "rag") {
      spinTxt.textContent = "Buscando nos documentos…";
      const boxes   = document.querySelectorAll("#pdfListaBusca input[type=checkbox]");
      const sources = Array.from(boxes).filter(b => b.checked).map(b => b.dataset.source);

      const data = await api("POST", "/api/busca/rag", { pergunta, sources, ignorar_cache: ignorarCache });
      spinTxt.textContent = "Gerando resposta com o LLM…";

      renderRespostaRag(data, pergunta);
    } else {
      spinTxt.textContent = "Buscando na internet via Gemini…";
      const data = await api("POST", "/api/busca/web", { pergunta, ignorar_cache: ignorarCache });
      renderRespostaWeb(data, pergunta);
    }
  } catch (e) {
    toast("❌ " + e.message, true);
  } finally {
    spin.classList.remove("on"); btnB.disabled = false;
    spinTxt.textContent = "Buscando…";
  }
}

function renderRespostaRag(data, pergunta) {
  document.getElementById("txtBuscaRag").textContent = data.resposta;
  document.getElementById("resBuscaRag").classList.remove("hidden");

  if (data.do_cache) {
    document.getElementById("cacheBusca").classList.remove("hidden");
    document.getElementById("cacheDataBusca").textContent = data.data_consulta;
  }

  // Chunks
  const area = document.getElementById("chunksAreaBusca");
  area.innerHTML = (data.chunks || []).map((c, i) => {
    const meta   = c.metadata || {};
    const nome   = meta.original_name || (meta.source || "").split("/").pop() || "?";
    const pagina = meta.page || "?";
    const score  = typeof c.score === "number" ? c.score.toFixed(4) : c.score;
    return `<div class="chunk">
      <div class="chunk-meta"><strong>[${i+1}]</strong> Score: <span class="tag">${score}</span> &nbsp; ${nome} &nbsp; Pág. ${pagina}</div>
      <div class="chunk-text">"${(c.content||"").substring(0,300)}${c.content?.length>300?"…":""}"</div>
    </div>`;
  }).join("");

  // Botão download
  const btnDl = document.getElementById("btnDownloadRag");
  if (btnDl) btnDl.onclick = () => window.open(`/api/download/resposta/${data.cache_id}`);
}

function renderRespostaWeb(data, pergunta) {
  document.getElementById("txtBuscaWeb").textContent = data.resposta;
  document.getElementById("resBuscaWeb").classList.remove("hidden");

  if (data.do_cache) {
    document.getElementById("cacheBusca").classList.remove("hidden");
    document.getElementById("cacheDataBusca").textContent = data.data_consulta;
  }

  // Fontes
  const area = document.getElementById("fontesWeb");
  area.innerHTML = (data.fontes || []).map((f, i) =>
    `<div class="src-link">
       <span class="num">[${i+1}]</span>
       <a href="${f.url}" target="_blank" rel="noopener">${f.title || f.url}</a>
     </div>`
  ).join("") || '<div class="muted caption">Nenhuma fonte retornada.</div>';

  const btnDl = document.getElementById("btnDownloadWeb");
  if (btnDl) btnDl.onclick = () => window.open(`/api/download/resposta/${data.cache_id}`);
}

function toggleChunks() {
  const checked = document.getElementById("chkChunks").checked;
  document.getElementById("chunksAreaBusca").classList.toggle("hidden", !checked);
}

/* ─────────────────────────────────────────────────────────────────────────
   PAINEL — Verificação
───────────────────────────────────────────────────────────────────────── */
let _verificacaoAtual = null;

function toggleModoVerif() {
  const v = document.getElementById("modoVerif").value;
  document.getElementById("configExata").classList.toggle("hidden", v !== "exata");
  document.getElementById("configLlm").classList.toggle("hidden",   v !== "llm");
}

async function verificarConteudo() {
  const arquivo  = document.getElementById("selArquivoVerif").value;
  const source   = document.getElementById("selArquivoVerif").selectedOptions[0]?.dataset.source;
  const modo     = document.getElementById("modoVerif").value;
  const criterio = modo === "exata"
    ? document.getElementById("palavrasProibidas").value
    : document.getElementById("criterioLlm").value;

  if (!source) { toast("Selecione um arquivo.", true); return; }
  if (!criterio.trim()) { toast("Informe o critério.", true); return; }

  const spin = document.getElementById("spinVerif");
  const res  = document.getElementById("resVerif");
  spin.classList.add("on"); res.classList.add("hidden");
  document.getElementById("resVerifEmpty").classList.add("hidden");

  try {
    const data = await api("POST", "/api/verificar", {
      arquivo: source, nome: arquivo, modo, criterio,
    });
    _verificacaoAtual = data;
    renderResultadoVerificacao(data);
  } catch (e) {
    toast("❌ " + e.message, true);
    document.getElementById("resVerifEmpty").classList.remove("hidden");
  } finally {
    spin.classList.remove("on");
  }
}

function renderResultadoVerificacao(data) {
  const el = document.getElementById("resVerif");
  const ocs = data.ocorrencias || [];

  let html = ocs.length === 0
    ? `<div class="alert alert-success">✅ <strong>Nenhuma ocorrência</strong> — o arquivo está aprovado.</div>`
    : `<div class="alert alert-error">❌ <strong>${ocs.length} chunk(s) reprovado(s)</strong></div>`;

  if (ocs.length) {
    html += `<div class="card"><div class="card-title mb8">📄 ${data.nome_arquivo}</div>`;
    ocs.forEach((oc, idx) => {
      const palavras = (oc.palavras || []).map(p => `<span class="tag">${p}</span>`).join(" ");
      const trecho   = marcarTrecho(oc.trecho || "", oc.palavras || [], oc.motivo || "");
      html += `
        <div class="occurrence" id="oc_${data.verification_id}_${idx}">
          <div class="occurrence-meta">
            <strong>Pág. ${oc.pagina || "?"}</strong>
            ${oc.palavras?.length ? `&nbsp;|&nbsp; Palavras: ${palavras}` : `&nbsp;|&nbsp; ${oc.motivo || ""}`}
          </div>
          <div class="occurrence-text">${trecho}</div>
          <div class="occurrence-actions" id="acoes_${data.verification_id}_${idx}">
            ${botoesRevisao(data.verification_id, idx, null, ocs)}
          </div>
        </div>`;
    });
    html += `</div>`;
  }
  html += `<button class="btn btn-secondary btn-sm" onclick="window.open('/api/download/verificacao/${data.verification_id}')">📄 Baixar PDF</button>`;

  el.innerHTML = html;
  el.classList.remove("hidden");
}

function marcarTrecho(trecho, palavras, motivo) {
  let t = trecho.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  (palavras || []).forEach(p => {
    t = t.replace(new RegExp(p.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"), "gi"),
      m => `<mark class="bad">${m}</mark>`);
  });
  return `"${t.substring(0,400)}${trecho.length>400?"…":""}"`;
}

function botoesRevisao(vid, idx, tipoAtual, ocorrencias) {
  if (tipoAtual === "aprovado") {
    return `<span class="badge b-ok">✅ Aprovado manualmente</span>
            <button class="btn btn-secondary btn-sm" onclick="revisar(${vid},${idx},'reprovado_confirmado',null)">🚫 Reprovar</button>`;
  }
  if (tipoAtual === "reprovado_confirmado") {
    return `<span class="badge b-conf">🚫 Reprovação confirmada</span>
            <button class="btn btn-ghost btn-sm" onclick="revisar(${vid},${idx},'aprovado',null)">✅ Aprovar manualmente</button>`;
  }
  return `<button class="btn btn-ghost btn-sm" onclick="revisar(${vid},${idx},'aprovado',${idx})">✅ Aprovar manualmente</button>
          <button class="btn btn-secondary btn-sm" onclick="revisar(${vid},${idx},'reprovado_confirmado',null)">🚫 Confirmar Reprovação</button>`;
}

async function revisar(vid, chunkIdx, tipo, propagarIdx) {
  const ocorrencias = _verificacaoAtual?.ocorrencias || null;
  const body = {
    chunk_indice: chunkIdx,
    tipo,
    observacao: "",
    ocorrencias: propagarIdx !== null ? ocorrencias : null,
  };
  try {
    const data = await api("POST", `/api/verificar/${vid}/revisar`, body);
    toast(tipo === "aprovado" ? "✅ Aprovado!" : "🚫 Reprovação confirmada.");
    // Atualiza botões de acordo com aprovações retornadas
    Object.entries(data.aprovacoes || {}).forEach(([idx, tipo]) => {
      const acoes = document.getElementById(`acoes_${vid}_${idx}`);
      if (acoes) acoes.innerHTML = botoesRevisao(vid, parseInt(idx), tipo, ocorrencias);
    });
  } catch (e) { toast(e.message, true); }
}

/* ─────────────────────────────────────────────────────────────────────────
   PAINEL — Histórico de Perguntas
───────────────────────────────────────────────────────────────────────── */
async function carregarHistoricoPerguntas() {
  const lista = document.getElementById("listaHistPerguntas");
  lista.innerHTML = '<div class="muted caption">Carregando…</div>';
  try {
    const data = await api("GET", "/api/historico/perguntas");
    renderHistoricoPerguntas(data);
  } catch (e) { lista.innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

function renderHistoricoPerguntas(registros) {
  const lista = document.getElementById("listaHistPerguntas");
  const total = document.getElementById("totalHistPerguntas");
  if (total) total.textContent = `Total: ${registros.length} registro(s)`;

  if (!registros.length) {
    lista.innerHTML = '<div class="empty-state"><div class="icon">💬</div>Nenhuma pergunta no histórico.</div>';
    return;
  }
  lista.innerHTML = registros.map(r => {
    const badge = r.tipo === "web"
      ? '<span class="badge b-web">🌐 Web</span>'
      : '<span class="badge b-rag">📄 RAG</span>';
    const fontes = r.tipo === "web" && Array.isArray(r.chunks) && r.chunks.length
      ? `<div class="mt8"><strong>Fontes:</strong>` +
        r.chunks.map((f, i) => `<div class="src-link"><span class="num">[${i+1}]</span><a href="${f.url}" target="_blank">${f.title||f.url}</a></div>`).join("") +
        `</div>`
      : "";

    return `<div class="hist-item">
      <div class="hist-hd" onclick="toggleH(this)">
        <div class="flex gap8"><span class="muted">🗓 ${r.data_consulta}</span>${badge}</div>
        <div class="muted" style="flex:1;margin:0 14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${r.pergunta}</div>
        <span class="muted">▼</span>
      </div>
      <div class="hist-bd">
        <p><strong>Pergunta:</strong> ${r.pergunta}</p>
        <div class="resp-box mt8">${r.resposta}</div>
        ${fontes}
        <div class="flex gap8 mt12">
          <button class="btn btn-secondary btn-sm" onclick="window.open('/api/download/resposta/${r.id}')">📄 Baixar PDF</button>
          <button class="btn btn-danger btn-sm" onclick="deletarPergunta(${r.id}, this)">🗑️ Apagar</button>
        </div>
      </div>
    </div>`;
  }).join("");
}

async function deletarPergunta(id, btn) {
  try {
    await api("DELETE", `/api/historico/perguntas/${id}`);
    btn.closest(".hist-item").remove();
    toast("✅ Registro removido.");
  } catch (e) { toast(e.message, true); }
}

function filtrarHistoricoPerguntas(q) {
  document.querySelectorAll("#listaHistPerguntas .hist-item").forEach(it => {
    it.style.display = !q || it.textContent.toLowerCase().includes(q.toLowerCase()) ? "" : "none";
  });
}

/* ─────────────────────────────────────────────────────────────────────────
   PAINEL — Histórico de Verificações
───────────────────────────────────────────────────────────────────────── */
async function carregarHistoricoVerificacoes() {
  const lista = document.getElementById("listaHistVerif");
  lista.innerHTML = '<div class="muted caption">Carregando…</div>';
  try {
    const data = await api("GET", "/api/historico/verificacoes");
    renderHistoricoVerificacoes(data);
  } catch (e) { lista.innerHTML = `<div class="alert alert-error">${e.message}</div>`; }
}

function renderHistoricoVerificacoes(registros) {
  const lista = document.getElementById("listaHistVerif");
  if (!registros.length) {
    lista.innerHTML = '<div class="empty-state"><div class="icon">🔍</div>Nenhuma verificação no histórico.</div>';
    return;
  }

  lista.innerHTML = registros.map(reg => {
    const statusBadge = {
      "aprovado":            '<span class="badge b-ok">✅ APROVADO</span>',
      "aprovado manualmente":'<span class="badge b-manual">✅ APROVADO MANUALMENTE</span>',
      "reprovado confirmado":'<span class="badge b-conf">🚫 REPROVADO CONFIRMADO</span>',
      "reprovado":           '<span class="badge b-fail">❌ REPROVADO</span>',
    }[reg.status] || `<span class="badge">${reg.status}</span>`;

    const modoTag = `<span class="tag">${reg.modo === "exata" ? "SQL" : "LLM"}</span>`;
    const ocs     = reg.ocorrencias || [];
    const aprov   = reg.aprovacoes  || {};

    let ocHtml = "";
    if (ocs.length) {
      const nRevisados = Object.keys(aprov).length;
      ocHtml += nRevisados < ocs.length
        ? `<div class="alert alert-warning">⚠ ${nRevisados} de ${ocs.length} ocorrência(s) revisada(s).</div>`
        : `<div class="alert alert-success">✅ Todas as ${ocs.length} ocorrência(s) revisadas.</div>`;

      ocs.forEach((oc, idx) => {
        const tipoRev = aprov[idx] || null;
        const trecho  = marcarTrecho(oc.trecho || "", oc.palavras || [], oc.motivo || "");
        const palavras = (oc.palavras || []).map(p => `<span class="tag">${p}</span>`).join(" ");
        ocHtml += `
          <div class="occurrence" id="hoc_${reg.id}_${idx}">
            <div class="occurrence-meta"><strong>Pág. ${oc.pagina||"?"}</strong> &nbsp;|&nbsp; ${palavras || oc.motivo || ""}</div>
            <div class="occurrence-text">${trecho}</div>
            <div class="occurrence-actions" id="hacoes_${reg.id}_${idx}">
              ${botoesRevisaoHist(reg.id, idx, tipoRev, ocs)}
            </div>
          </div>`;
      });
    }

    return `<div class="hist-item">
      <div class="hist-hd" onclick="toggleH(this)">
        <div class="flex gap8"><span class="muted">🗓 ${reg.data_verificacao}</span>${statusBadge}${modoTag}</div>
        <div class="muted" style="flex:1;margin:0 14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${reg.arquivo?.split("/").pop() || reg.arquivo} — ${reg.criterio}</div>
        <span class="muted">▼</span>
      </div>
      <div class="hist-bd">
        <div class="row mb8">
          <div class="col"><strong>Arquivo:</strong> ${reg.arquivo?.split("/").pop() || reg.arquivo}</div>
          <div class="col"><strong>Modo:</strong> ${reg.modo === "exata" ? "Busca Exata (SQL)" : "Moderação por LLM"}</div>
        </div>
        ${ocHtml}
        <div class="flex gap8 mt8">
          <button class="btn btn-secondary btn-sm" onclick="window.open('/api/download/verificacao/${reg.id}')">📄 Baixar PDF</button>
          <button class="btn btn-danger btn-sm" onclick="deletarVerificacao(${reg.id}, this)">🗑️ Apagar</button>
        </div>
      </div>
    </div>`;
  }).join("");
}

function botoesRevisaoHist(vid, idx, tipoAtual, ocorrencias) {
  if (tipoAtual === "aprovado") {
    return `<span class="badge b-ok">✅ Aprovado manualmente</span>
            <button class="btn btn-secondary btn-sm" onclick="revisarHist(${vid},${idx},'reprovado_confirmado')">🚫 Reprovar</button>`;
  }
  if (tipoAtual === "reprovado_confirmado") {
    return `<span class="badge b-conf">🚫 Reprovação confirmada</span>
            <button class="btn btn-ghost btn-sm" onclick="revisarHist(${vid},${idx},'aprovado')">✅ Aprovar manualmente</button>`;
  }
  return `<button class="btn btn-ghost btn-sm" onclick="revisarHist(${vid},${idx},'aprovado')">✅ Aprovar</button>
          <button class="btn btn-secondary btn-sm" onclick="revisarHist(${vid},${idx},'reprovado_confirmado')">🚫 Confirmar Reprovação</button>`;
}

async function revisarHist(vid, idx, tipo) {
  try {
    const data = await api("POST", `/api/verificar/${vid}/revisar`, { chunk_indice: idx, tipo, observacao: "" });
    toast(tipo === "aprovado" ? "✅ Aprovado!" : "🚫 Reprovação confirmada.");
    Object.entries(data.aprovacoes || {}).forEach(([i, t]) => {
      const el = document.getElementById(`hacoes_${vid}_${i}`);
      if (el) el.innerHTML = botoesRevisaoHist(vid, parseInt(i), t, null);
    });
  } catch (e) { toast(e.message, true); }
}

async function deletarVerificacao(id, btn) {
  try {
    await api("DELETE", `/api/verificar/${id}`);
    btn.closest(".hist-item").remove();
    toast("✅ Verificação removida.");
  } catch (e) { toast(e.message, true); }
}
