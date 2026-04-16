# -*- coding: utf-8 -*-
"""
search.py - Busca por similaridade no banco vetorial.

Uso standalone (teste):
    python src/search.py "Qual é o prazo de entrega?"

Uso como módulo (importado por chat.py):
    from search import buscar
    resultados = buscar("minha pergunta")
"""

import os
import sys
import io
from dotenv import load_dotenv

# Garante UTF-8 no terminal Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

load_dotenv()

PROVIDER     = os.getenv("LLM_PROVIDER", "openai").lower()
DATABASE_URL = os.getenv("DATABASE_URL")
COLLECTION   = os.getenv("COLLECTION_NAME", "documentos_rag")

if not DATABASE_URL:
    raise EnvironmentError("DATABASE_URL não definida no .env")

# ---------------------------------------------------------------------------
# Seleção do provedor de embeddings
# ---------------------------------------------------------------------------
if PROVIDER == "openai":
    from langchain_openai import OpenAIEmbeddings
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

elif PROVIDER == "gemini":
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

else:
    raise ValueError(f"LLM_PROVIDER inválido: '{PROVIDER}'. Use 'openai' ou 'gemini'.")

# ---------------------------------------------------------------------------
# Conexão com o vectorstore (somente leitura)
# ---------------------------------------------------------------------------
from langchain_postgres import PGVector

vectorstore = PGVector(
    embeddings=embeddings,
    collection_name=COLLECTION,
    connection=DATABASE_URL,
    use_jsonb=True,
)


# ---------------------------------------------------------------------------
# Função principal de busca
# ---------------------------------------------------------------------------
def buscar(query: str, k: int = 10) -> list:
    """Retorna lista de (Document, score) ordenada por relevância."""
    return vectorstore.similarity_search_with_score(query, k=k)


# ---------------------------------------------------------------------------
# Execução direta para testes manuais
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python src/search.py '<pergunta>'")
        sys.exit(1)

    query = sys.argv[1]
    resultados = buscar(query)

    print(f"\n{len(resultados)} resultado(s) para: '{query}'\n")
    for i, (doc, score) in enumerate(resultados, 1):
        fonte  = doc.metadata.get("source", "desconhecida")
        pagina = doc.metadata.get("page", "?")
        print(f"[{i}] Score: {score:.4f} | Fonte: {fonte} | Página: {pagina}")
        print(f"     {doc.page_content[:200]}...")
        print()
