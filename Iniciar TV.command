#!/bin/bash
# Script para iniciar a TV RARUS com servidor local (compatibilidade total com YouTube no Mac)
cd "$(dirname "$0")"

# Porta padrão
PORT=8080

# Verifica se a porta já está em uso, senão usa 8081
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    PORT=8081
fi

echo "========================================================"
echo "          INICIANDO TV RARUS - MODO SMART TV            "
echo "========================================================"
echo "Servidor rodando em: http://localhost:$PORT"
echo "Abrindo navegador..."
echo "Pressione CTRL+C para encerrar."
echo "========================================================"

# Abre no navegador padrão
sleep 1 && open "http://localhost:$PORT/index.html" &

# Inicia servidor web local leve do Python
python3 -m http.server $PORT
