FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 5000

# --timeout alto porque, com LLM_PROVIDER=ollama rodando em CPU, uma geração
# pode levar bem mais que os 30s padrão do gunicorn antes de responder.
CMD ["gunicorn", "--chdir", "src", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "300", "app:app"]
