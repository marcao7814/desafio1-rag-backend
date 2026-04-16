# chat.py — Geração de Resposta RAG

## O que faz

Recebe uma pergunta, busca os chunks mais relevantes no banco vetorial e envia o contexto para o LLM gerar uma resposta fundamentada apenas nos documentos ingeridos.

## Localização

```
src/chat.py
```

## Função exportada

```python
from chat import responder

resposta = responder("Qual é o prazo de entrega?")
# retorna: str com a resposta gerada pelo LLM
```

## Parâmetros

| Parâmetro  | Tipo  | Descrição            |
|------------|-------|----------------------|
| `pergunta` | `str` | Texto da pergunta    |

**Retorno:** `str` — resposta gerada pelo LLM.

## Fluxo interno

```
pergunta
   └─> buscar(pergunta, k=15)        ← search.py
          └─> sem resultados: retorna mensagem padrão
          └─> com resultados:
                 contexto = chunks concatenados
                 prompt   = PROMPT_TEMPLATE.format(contexto, pergunta)
                 └─> llm.invoke(prompt).content  → resposta
```

## Prompt utilizado

```
CONTEXTO:
{chunks concatenados separados por "---"}

REGRAS:
- Responda somente com base no CONTEXTO.
- Se a informação não estiver no CONTEXTO, responda:
  "Não tenho informações necessárias para responder sua pergunta."
- Nunca invente ou use conhecimento externo.
- Nunca produza opiniões além do que está escrito.

PERGUNTA DO USUÁRIO:
{pergunta}

RESPONDA A "PERGUNTA DO USUÁRIO"
```

## Modelos LLM por provider

| `LLM_PROVIDER` | Modelo              |
|----------------|---------------------|
| `openai`       | `gpt-5-nano`        |
| `gemini`       | `gemini-2.5-flash-lite` |

Configurado via variável de ambiente `LLM_PROVIDER` no `.env`.

## Uso standalone (terminal)

```bash
python src/chat.py
# Abre um loop interativo; digite "sair" para encerrar
```

## Dependências

```python
from langchain_openai import ChatOpenAI          # se openai
from langchain_google_genai import ChatGoogleGenerativeAI  # se gemini
from search import buscar
```

## Variáveis de ambiente necessárias

| Variável         | Quando obrigatória        |
|------------------|---------------------------|
| `LLM_PROVIDER`   | Sempre                    |
| `OPENAI_API_KEY` | Se `LLM_PROVIDER=openai`  |
| `GOOGLE_API_KEY` | Se `LLM_PROVIDER=gemini`  |
| `DATABASE_URL`   | Sempre (via search.py)    |
