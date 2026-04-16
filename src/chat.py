"""
chat.py - CLI de chat com RAG.

Uso:
    python src/chat.py

Digite 'sair' ou pressione Ctrl+C para encerrar.
"""

import os
import sys
import pathlib
from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()

# ---------------------------------------------------------------------------
# 1. Seleção do LLM
# ---------------------------------------------------------------------------
if PROVIDER == "openai":
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model="gpt-5-nano", temperature=0)

elif PROVIDER == "gemini":
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)

else:
    raise ValueError(f"LLM_PROVIDER inválido: '{PROVIDER}'. Use 'openai' ou 'gemini'.")

# ---------------------------------------------------------------------------
# 2. Template do prompt
# ---------------------------------------------------------------------------
PROMPT_TEMPLATE = """CONTEXTO:
{contexto}

REGRAS:
- Responda somente com base no CONTEXTO.
- Se a informação não estiver explicitamente no CONTEXTO, responda:
  "Não tenho informações necessárias para responder sua pergunta."
- Nunca invente ou use conhecimento externo.
- Nunca produza opiniões ou interpretações além do que está escrito.

EXEMPLOS DE PERGUNTAS FORA DO CONTEXTO:
Pergunta: "Qual é a capital da França?"
Resposta: "Não tenho informações necessárias para responder sua pergunta."

Pergunta: "Quantos clientes temos em 2024?"
Resposta: "Não tenho informações necessárias para responder sua pergunta."

Pergunta: "Você acha isso bom ou ruim?"
Resposta: "Não tenho informações necessárias para responder sua pergunta."

PERGUNTA DO USUÁRIO:
{pergunta}

RESPONDA A "PERGUNTA DO USUÁRIO"
"""

# ---------------------------------------------------------------------------
# 3. Importa a função de busca
# ---------------------------------------------------------------------------
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from search import buscar


# ---------------------------------------------------------------------------
# 4. Função de resposta
# ---------------------------------------------------------------------------
def responder(pergunta: str) -> str:
    resultados = buscar(pergunta, k=15)

    if not resultados:
        return "Não tenho informações necessárias para responder sua pergunta."

    contexto = "\n\n---\n\n".join(doc.page_content for doc, _ in resultados)
    prompt   = PROMPT_TEMPLATE.format(contexto=contexto, pergunta=pergunta)

    return llm.invoke(prompt).content


# ---------------------------------------------------------------------------
# 5. Loop principal de chat
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  Chat RAG — Digite 'sair' para encerrar")
    print("=" * 60)

    while True:
        try:
            pergunta = input("\nVocê: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nEncerrando...")
            break

        if not pergunta:
            continue

        if pergunta.lower() in {"sair", "exit", "quit"}:
            print("Até mais!")
            break

        resposta = responder(pergunta)
        print(f"\nAssistente: {resposta}")


if __name__ == "__main__":
    main()
