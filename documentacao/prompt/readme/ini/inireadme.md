# ini.bat — Script de Inicialização (Windows)

## O que faz

Script batch que automatiza toda a sequência de startup do sistema RAG no Windows: ativa o ambiente virtual, garante que o banco de dados está rodando, verifica dependências e inicia o Streamlit abrindo o Chrome automaticamente.

## Localização

```
ini.bat
```

## Como executar

```bat
ini.bat
```

Basta dar duplo clique no arquivo ou executar no terminal. Não requer argumentos.

## Sequência de execução

```
ini.bat
  │
  ├─ 1. cd /d "%~dp0"
  │       Garante que o diretório de trabalho é a raiz do projeto,
  │       independente de onde o script foi chamado.
  │
  ├─ 2. call venv\Scripts\activate.bat
  │       Ativa o ambiente virtual Python.
  │
  ├─ 3. docker ps --filter name=rag_postgres
  │       Verifica se o container está rodando.
  │       ├─ Não está → docker compose up -d + aguarda 5s
  │       └─ Está     → continua imediatamente
  │
  ├─ 4. pip show streamlit
  │       Verifica se o Streamlit está instalado.
  │       └─ Não está → pip install streamlit>=1.35.0 --quiet
  │
  ├─ 5. start /b cmd /c "ping -n 4 ... && start chrome http://localhost:8501"
  │       Abre o Chrome em background após ~3 segundos
  │       (tempo para o Streamlit subir).
  │
  └─ 6. streamlit run src/frontEnd.py ...
          Inicia o Streamlit em modo headless na porta 8501.
          O terminal fica bloqueado aqui até o usuário encerrar (Ctrl+C).
```

## Parâmetros do Streamlit usados

| Parâmetro                       | Valor   | Descrição                                         |
|---------------------------------|---------|---------------------------------------------------|
| `--server.port`                 | `8501`  | Porta HTTP do Streamlit                           |
| `--server.headless`             | `true`  | Não abre navegador automaticamente (Chrome é aberto separado) |
| `--browser.gatherUsageStats`    | `false` | Desabilita telemetria do Streamlit                |

## Detecção do container Docker

```bat
docker ps --filter name=rag_postgres --filter status=running --format "{{.Names}}" | findstr rag_postgres
```

- Filtra por nome `rag_postgres` e status `running`
- Se o container não for encontrado: executa `docker compose up -d` e aguarda 5 segundos (`ping -n 6 127.0.0.1`)
- O wait de 5s evita que o Streamlit tente conectar antes do PostgreSQL estar pronto

## Acesso após inicialização

| Endereço                  | Descrição                   |
|---------------------------|-----------------------------|
| `http://localhost:8501`   | Interface Streamlit         |

## Requisitos

| Requisito         | Mínimo                                              |
|-------------------|-----------------------------------------------------|
| Sistema operacional | Windows (usa `cmd`, `findstr`, `start`, `ping`)  |
| Python            | 3.11+ com `venv\` criado na raiz do projeto         |
| Docker Desktop    | Instalado e rodando                                 |
| Chrome            | Instalado (para abertura automática)                |

## Encerramento

Pressione `Ctrl+C` no terminal onde o `ini.bat` está rodando. O Streamlit para. O container Docker continua rodando (não é derrubado pelo script).

Para parar o banco:

```bat
docker compose down
```

Para parar e remover todos os dados:

```bat
docker compose down -v
```
