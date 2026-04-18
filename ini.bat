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
pip show flask >nul 2>&1
if errorlevel 1 (
    echo  Instalando Flask...
    pip install flask>=3.0.0 --quiet
)

echo ============================================================
echo  Iniciando servidor Flask (orquestrador Python)...
echo  Acesse: http://localhost:5000
echo ============================================================

REM Abre o Chrome apos 3 segundos (enquanto o Flask sobe)
start /b cmd /c "ping -n 4 127.0.0.1 >nul && start chrome http://localhost:5000"

REM Inicia o Flask
python src\app.py

pause
