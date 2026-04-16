"""
web_search.py — Busca na internet via Gemini com Google Search grounding.

Uso como módulo:
    from web_search import buscar_na_web
    resposta, fontes = buscar_na_web("Qual é a cotação do dólar hoje?")
"""

import os
from dotenv import load_dotenv

load_dotenv()


def buscar_na_web(pergunta: str) -> tuple[str, list[dict]]:
    """
    Realiza busca na internet usando Gemini com Google Search grounding.

    Retorna:
        (resposta, fontes) onde fontes é lista de dicts {"title": ..., "url": ...}
    """
    from google import genai
    from google.genai import types

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError("GOOGLE_API_KEY não definida no .env")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=pergunta,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )

    resposta = response.text or ""

    fontes: list[dict] = []
    if response.candidates:
        candidate = response.candidates[0]
        metadata = getattr(candidate, "grounding_metadata", None)
        if metadata:
            chunks = getattr(metadata, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if web:
                    fontes.append({
                        "title": getattr(web, "title", "") or "",
                        "url":   getattr(web, "uri",   "") or "",
                    })

    return resposta, fontes
