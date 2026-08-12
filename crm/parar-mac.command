#!/bin/bash
cd "$(dirname "$0")"
echo "Parando o CRM..."
docker compose down
echo ""
echo "CRM parado. Os dados continuam salvos na pasta \"data\"."
read -p "Pressione Enter para fechar..."
