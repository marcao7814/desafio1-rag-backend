"""
content_guard.py — Verificação centralizada de conteúdo proibido no banco RAG.
"""

import unicodedata


# Lista padrão de palavras proibidas (pode ser sobrescrita via parâmetro)
PALAVRAS_PROIBIDAS_PADRAO: list[str] = [
    "safado",
    "corno",
    "inutil",
]


def _normalizar(texto: str) -> str:
    """Remove acentos e converte para minúsculas para comparação uniforme."""
    return unicodedata.normalize("NFD", texto.lower()).encode("ascii", "ignore").decode()


def palavras_encontradas(texto: str, lista: list[str]) -> list[str]:
    """Retorna as palavras proibidas presentes no texto."""
    texto_norm = _normalizar(texto)
    return [p for p in lista if _normalizar(p) in texto_norm]


def auditar_banco(
    psycopg_url: str,
    collection: str,
    lista: list[str],
    source: str | None = None,
) -> list[dict]:
    """
    Varre chunks da coleção e retorna os que contêm palavras proibidas.

    Parâmetros:
        source : caminho do arquivo (cmetadata->>'source') para filtrar um PDF específico.
                 None = todos os arquivos.

    Retorna lista de dicts: id, arquivo, nome, pagina, trecho, palavras
    """
    import psycopg

    if not lista:
        return []

    termos_normalizados = [_normalizar(p) for p in lista]
    condicoes = " OR ".join(
        f"LOWER(document) LIKE '%%{t}%%'" for t in termos_normalizados
    )

    filtro_source = "AND cmetadata->>'source' = %s" if source else ""

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
        {filtro_source}
        AND ({condicoes})
        ORDER BY cmetadata->>'source', (cmetadata->>'page')::int NULLS LAST
    """

    params = (collection, source) if source else (collection,)
    with psycopg.connect(psycopg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    resultado = []
    for r in rows:
        chunk_id, arquivo, nome, pagina, document = r
        achadas = palavras_encontradas(document or "", lista)
        if achadas:
            resultado.append({
                "id":       chunk_id,
                "arquivo":  arquivo or "",
                "nome":     nome or (arquivo.split("/")[-1] if arquivo else ""),
                "pagina":   pagina or "?",
                "trecho":   document or "",
                "palavras": achadas,
            })

    return resultado


def auditar_banco_vetorial(
    vectorstore,
    lista: list[str],
    k: int = 5,
    limiar: float = 0.80,
    source: str | None = None,
) -> list[dict]:
    """
    Para cada palavra faz busca por similaridade no vectorstore e retorna
    os chunks cujo score esteja abaixo do limiar.

    Parâmetros:
        source : caminho do arquivo para filtrar um PDF específico. None = todos.
        k      : quantos chunks recuperar por palavra
        limiar : distância máxima para considerar similar (menor = mais restritivo)

    Retorna lista de dicts: palavra, arquivo, nome, pagina, trecho, score
    """
    vistos: set[str] = set()
    resultado = []

    filtro = {"source": source} if source else None

    for palavra in lista:
        hits = vectorstore.similarity_search_with_score(palavra, k=k, filter=filtro)
        for doc, score in hits:
            if score > limiar:
                continue
            chave = f"{palavra}|{doc.page_content[:80]}"
            if chave in vistos:
                continue
            vistos.add(chave)

            arquivo = doc.metadata.get("source", "")
            nome    = doc.metadata.get("original_name") or (arquivo.split("/")[-1] if arquivo else "")
            resultado.append({
                "palavra": palavra,
                "arquivo": arquivo,
                "nome":    nome,
                "pagina":  doc.metadata.get("page", "?"),
                "trecho":  doc.page_content[:400],
                "score":   score,
            })

    resultado.sort(key=lambda x: x["score"])
    return resultado


def auditar_banco_llm(
    psycopg_url: str,
    collection: str,
    criterio: str,
    llm,
    batch_size: int = 10,
    source: str | None = None,
) -> list[dict]:
    """
    Envia chunks em lotes ao LLM para classificação de conteúdo.

    Parâmetros:
        source : caminho do arquivo para filtrar um PDF específico. None = todos.

    Retorna lista de dicts dos chunks reprovados: arquivo, nome, pagina, trecho, motivo
    """
    import psycopg

    filtro_source = "AND cmetadata->>'source' = %s" if source else ""

    sql = f"""
        SELECT
            cmetadata->>'source'        AS arquivo,
            cmetadata->>'original_name' AS nome,
            cmetadata->>'page'          AS pagina,
            document
        FROM langchain_pg_embedding
        WHERE collection_id = (
            SELECT uuid FROM langchain_pg_collection WHERE name = %s
        )
        {filtro_source}
        ORDER BY cmetadata->>'source', (cmetadata->>'page')::int NULLS LAST
    """

    params = (collection, source) if source else (collection,)
    with psycopg.connect(psycopg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    if not rows:
        return []

    PROMPT_BATCH = """Para cada frase numerada abaixo, responda se ela contém "{criterio}" — isto é, se há algo errado, inadequado, informal, chulo, ofensivo ou fora do contexto do restante do texto.

Use o NÚMERO da frase na resposta. Formato obrigatório, um resultado por linha:
numero: nao
ou
numero: sim - <motivo objetivo>

Exemplos:
1: nao
2: sim - expressão chula fora do contexto
3: nao

Frases:
{trechos}"""

    import re

    def _dividir_frases(texto: str) -> list[str]:
        """Divide o texto em frases pelo ponto final, exclamação ou interrogação."""
        frases = re.split(r'(?<=[.!?])\s+', texto.strip())
        return [f.strip() for f in frases if len(f.strip()) > 10]

    reprovados = []
    log_respostas = []

    for row in rows:
        arquivo_row = row[0] or ""
        nome_row    = row[1] or (arquivo_row.split("/")[-1] if arquivo_row else "")
        pagina_row  = row[2] or "?"
        documento   = row[3] or ""

        frases = _dividir_frases(documento)
        if not frases:
            continue

        # Processa as frases do chunk em lotes
        for i in range(0, len(frases), batch_size):
            lote_frases = frases[i : i + batch_size]
            trechos_texto = "\n".join(
                f"[{j + 1}] {f}" for j, f in enumerate(lote_frases)
            )
            prompt   = PROMPT_BATCH.format(criterio=criterio, trechos=trechos_texto)
            resposta = llm.invoke(prompt).content
            log_respostas.append({
                "lote": f"{nome_row} / frases {i+1}-{i+len(lote_frases)}",
                "resposta_bruta": resposta,
            })

            for linha in resposta.splitlines():
                linha = linha.strip()
                if not linha:
                    continue
                # Aceita: "7: sim - motivo" ou "[7] sim: motivo" ou "7. sim motivo"
                match = re.search(r'[\[(\s]?(\d+)[\])\s.:-]+\s*(sim|não|nao)([\s:,-](.*))?', linha, re.IGNORECASE)
                if not match:
                    continue
                try:
                    idx      = int(match.group(1)) - 1
                    resposta_bin = match.group(2).lower()
                    motivo   = (match.group(4) or "").strip()
                    if idx < 0 or idx >= len(lote_frases):
                        continue
                    if resposta_bin in ("não", "nao"):
                        continue
                    frase_reprovada = lote_frases[idx]
                    reprovados.append({
                        "arquivo": arquivo_row,
                        "nome":    nome_row,
                        "pagina":  pagina_row,
                        "trecho":  documento,
                        "motivo":  f'"{frase_reprovada}" — {motivo or "frase inadequada detectada"}',
                    })
                    break  # uma reprovação por chunk é suficiente
                except (ValueError, IndexError):
                    continue

    return reprovados, log_respostas
