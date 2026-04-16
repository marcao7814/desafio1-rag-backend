"""
ingest.py - Ingere um arquivo PDF no banco vetorial PostgreSQL + pgVector.

Uso standalone:
    python src/ingest.py

Uso como módulo (importado por frontEnd.py):
    from ingest import ingerir
    n = ingerir("documento.pdf", nome_original="documento.pdf", pre_delete=False)
"""

import os
import time
from dotenv import load_dotenv
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception

load_dotenv()


def _is_quota_error(e: BaseException) -> bool:
    msg = str(e).lower()
    return "429" in str(e) or "quota" in msg or "resource exhausted" in msg

# ---------------------------------------------------------------------------
# Variáveis de ambiente
# ---------------------------------------------------------------------------
PROVIDER     = os.getenv("LLM_PROVIDER", "openai").lower()
DATABASE_URL = os.getenv("DATABASE_URL")
COLLECTION   = os.getenv("COLLECTION_NAME", "documentos_rag")
PDF_PATH     = os.getenv("PDF_PATH", "document.pdf")


# ---------------------------------------------------------------------------
# Seleção do provedor de embeddings (lazy — só inicializa quando chamado)
# ---------------------------------------------------------------------------
def _get_embeddings():
    if PROVIDER == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model="text-embedding-3-small")
    elif PROVIDER == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        base = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

        class _WithRetry(type(base)):
            @retry(
                retry=retry_if_exception(_is_quota_error),
                wait=wait_exponential(multiplier=1, min=25, max=90),
                stop=stop_after_attempt(6),
                reraise=True,
            )
            def embed_documents(self, texts, *args, **kwargs):
                return super().embed_documents(texts, *args, **kwargs)

            @retry(
                retry=retry_if_exception(_is_quota_error),
                wait=wait_exponential(multiplier=1, min=25, max=90),
                stop=stop_after_attempt(6),
                reraise=True,
            )
            def embed_query(self, text, *args, **kwargs):
                return super().embed_query(text, *args, **kwargs)

        base.__class__ = _WithRetry
        return base
    else:
        raise ValueError(f"LLM_PROVIDER inválido: '{PROVIDER}'. Use 'openai' ou 'gemini'.")


# ---------------------------------------------------------------------------
# Função principal de ingestão (exportada para uso no frontEnd.py)
# ---------------------------------------------------------------------------
def ingerir(pdf_path: str, nome_original: str = None, pre_delete: bool = True) -> int:
    """
    Carrega pdf_path, divide em chunks e grava no banco vetorial.

    Parâmetros:
        pdf_path      : caminho do arquivo PDF no disco.
        nome_original : nome amigável gravado nos metadados (ex.: nome do upload).
        pre_delete    : True  = apaga a coleção antes de gravar (substituir tudo).
                        False = acrescenta à coleção existente (adicionar).

    Retorna o número de chunks gravados.
    """
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_postgres import PGVector

    # 1. Carregamento
    print(f"Carregando PDF: {pdf_path}")
    loader = PyPDFLoader(pdf_path)
    pages  = loader.load()
    print(f"  {len(pages)} página(s) carregada(s).")

    # 2. Metadata extra: nome original do arquivo
    if nome_original:
        for page in pages:
            page.metadata["original_name"] = nome_original

    # 3. Chunking
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    chunks   = splitter.split_documents(pages)
    print(f"  {len(chunks)} chunk(s) gerado(s).")

    # 4. Persistência — mesmo método que o script standalone usa
    print("Conectando ao banco e salvando vetores...")
    PGVector.from_documents(
        documents=chunks,
        embedding=_get_embeddings(),
        collection_name=COLLECTION,
        connection=DATABASE_URL,
        use_jsonb=True,
        pre_delete_collection=pre_delete,
    )
    print("Ingestão concluída com sucesso.")
    return len(chunks)


# ---------------------------------------------------------------------------
# Execução direta (comportamento original preservado)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not DATABASE_URL:
        raise EnvironmentError("DATABASE_URL não definida no .env")
    n = ingerir(PDF_PATH, pre_delete=True)
    print(f"Total: {n} chunk(s) gravados.")
