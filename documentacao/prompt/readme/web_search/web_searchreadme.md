# web_search.py — Busca na Internet via Gemini

## O que faz

Envia uma pergunta ao modelo `gemini-2.5-flash` com a ferramenta **Google Search grounding** ativada. O Gemini consulta o Google em tempo real, fundamenta a resposta em páginas reais e retorna as fontes utilizadas.

## Localização

```
src/web_search.py
```

## Função exportada

```python
from web_search import buscar_na_web

resposta, fontes = buscar_na_web("Qual é a cotação do dólar hoje?")
```

## Parâmetros

| Parâmetro  | Tipo  | Descrição         |
|------------|-------|-------------------|
| `pergunta` | `str` | Texto da pergunta |

**Retorno:** `tuple[str, list[dict]]`

| Campo     | Tipo         | Descrição                                      |
|-----------|--------------|------------------------------------------------|
| `resposta`| `str`        | Resposta gerada pelo Gemini com base na web    |
| `fontes`  | `list[dict]` | Lista de `{"title": str, "url": str}`          |

## Exemplo completo

```python
from web_search import buscar_na_web

resposta, fontes = buscar_na_web("Quem ganhou a Copa do Mundo 2022?")

print(resposta)
# "A Argentina ganhou a Copa do Mundo FIFA 2022..."

for fonte in fontes:
    print(fonte["title"], "→", fonte["url"])
# "FIFA World Cup Qatar 2022 → https://www.fifa.com/..."
```

## SDK utilizado

Usa o `google-genai` SDK diretamente (não via LangChain):

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=api_key)

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=pergunta,
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    ),
)
```

## Onde as fontes são extraídas

```
response.candidates[0]
    └─> grounding_metadata
           └─> grounding_chunks[]
                  └─> chunk.web.title  → fonte["title"]
                  └─> chunk.web.uri   → fonte["url"]
```

## Custo

| Item              | Custo aproximado                |
|-------------------|---------------------------------|
| Tokens de entrada | Conforme tabela Gemini API      |
| Tokens de saída   | Conforme tabela Gemini API      |
| Google Search     | ~$0,035 por consulta de busca   |

O cache na tabela `search_cache` (`tipo='web'`) elimina o custo em perguntas repetidas.

## Diferença em relação ao RAG

| Aspecto          | Busca RAG (`search.py`)          | Busca Web (`web_search.py`)          |
|------------------|----------------------------------|--------------------------------------|
| Fonte dos dados  | PDFs ingeridos no banco          | Internet em tempo real               |
| SDK              | LangChain + PGVector             | google-genai direto                  |
| Modelo           | `gemini-2.5-flash-lite` (LLM)   | `gemini-2.5-flash` (com grounding)  |
| Fontes retornadas| Chunks com score e página        | URLs e títulos das páginas web       |
| Atualidade       | Limitada aos PDFs carregados     | Tempo real                           |

## Variáveis de ambiente necessárias

| Variável         | Descrição                                      |
|------------------|------------------------------------------------|
| `GOOGLE_API_KEY` | Chave do Google AI Studio (obrigatória sempre) |

> `GOOGLE_API_KEY` é necessária independentemente do `LLM_PROVIDER` configurado para o RAG.

## Dependências

```python
from google import genai          # google-genai >= 1.0.0
from google.genai import types
```
