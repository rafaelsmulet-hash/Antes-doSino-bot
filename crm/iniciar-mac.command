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
    echo "ERRO: nao foi possivel iniciar. O Docker Desktop esta aberto e rodando?"
    read -p "Pressione Enter para fechar..."
    exit 1
fi
echo ""
echo "Aguardando o servidor ficar pronto..."
sleep 4
open http://127.0.0.1:8000
echo ""
echo "CRM rodando em http://127.0.0.1:8000"
echo "Para PARAR o CRM, clique duas vezes em parar-mac.command"
echo ""
read -p "Pressione Enter para fechar esta janela..."
