@echo off
title RAG Front-End

cd /d "%~dp0"

echo ============================================================
echo  Ativando ambiente virtual...
echo ============================================================
call venv\Scripts\activate.bat

echo ============================================================
echo  Verificando banco de dados (Docker)...
echo ============================================================
docker ps --filter name=rag_postgres --filter status=running --format "{{.Names}}" | findstr rag_postgres >nul 2>&1
if errorlevel 1 (
    echo  Container rag_postgres nao esta rodando. Subindo com docker compose...
    docker compose up -d
    echo  Aguardando banco ficar pronto...
    ping -n 6 127.0.0.1 >nul
) else (
    echo  Banco OK.
)

echo ============================================================
echo  Verificando dependencias...
echo ============================================================
pip show streamlit >nul 2>&1
if errorlevel 1 (
    echo  Instalando streamlit...
    pip install streamlit>=1.35.0 --quiet
)

echo ============================================================
echo  Iniciando servidor Streamlit...
echo  Acesse: http://localhost:8501
echo ============================================================

REM Abre o Chrome apos 3 segundos (enquanto o Streamlit sobe)
start /b cmd /c "ping -n 4 127.0.0.1 >nul && start chrome http://localhost:8501"

REM Inicia o Streamlit sem abrir navegador automatico (Chrome ja sera aberto acima)
streamlit run src/frontEnd.py ^
    --server.port 8501 ^
    --server.headless true ^
    --browser.gatherUsageStats false

pause
