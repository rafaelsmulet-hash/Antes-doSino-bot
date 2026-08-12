@echo off
cd /d "%~dp0"
echo ============================================
echo   CRM Mesa de Sales Trading -- iniciando...
echo ============================================
echo.
echo (primeira vez pode demorar alguns minutos)
echo.
docker compose up -d --build
if errorlevel 1 (
    echo.
    echo ERRO: nao foi possivel iniciar. O Docker Desktop esta aberto e rodando?
    pause
    exit /b 1
)
echo.
echo Aguardando o servidor ficar pronto...
timeout /t 4 /nobreak > NUL
start http://127.0.0.1:8000
echo.
echo CRM rodando em http://127.0.0.1:8000
echo Para PARAR o CRM, clique duas vezes em parar-windows.bat
echo.
pause
