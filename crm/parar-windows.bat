@echo off
cd /d "%~dp0"
echo Parando o CRM...
docker compose down
echo.
echo CRM parado. Os dados continuam salvos na pasta "data".
pause
