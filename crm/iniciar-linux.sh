#!/bin/bash
cd "$(dirname "$0")"
echo "============================================"
echo "  CRM Mesa de Sales Trading -- iniciando..."
echo "============================================"
echo ""
echo "(primeira vez pode demorar alguns minutos)"
echo ""
if ! docker compose up -d --build; then
    echo ""
    echo "ERRO: nao foi possivel iniciar. O Docker esta instalado e rodando?"
    exit 1
fi
echo ""
echo "Aguardando o servidor ficar pronto..."
sleep 4
if command -v xdg-open > /dev/null; then
    xdg-open http://127.0.0.1:8000
fi
echo ""
echo "CRM rodando em http://127.0.0.1:8000"
echo "Para parar: ./parar-linux.sh"
