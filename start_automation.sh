#!/bin/bash
# =============================================================================================
# Script de Inicialização - Automação PROSPER ERP
# =============================================================================================
# Este script:
# 1. Inicia Xvfb (display virtual :1)
# 2. Inicia x11vnc (VNC para visualização remota na porta 5900)
# 3. Ativa o ambiente virtual Python
# 4. Executa o processador Nodriver
# =============================================================================================

set -e  # Para na primeira falha

echo "=========================================="
echo "PROSPER-ERP-AUTOMATION - INICIANDO"
echo "=========================================="
echo ""

# Diretório do projeto
PROJECT_DIR="/home/ubuntu/automacoes/PROSPER-ERP-AUTOMATION"
cd "$PROJECT_DIR"

echo "[1/5] Verificando se Xvfb já está rodando..."
if pgrep -x "Xvfb" > /dev/null; then
    echo "  ⚠️  Xvfb já está rodando. Matando processo antigo..."
    pkill Xvfb || true
    sleep 2
fi

echo "[2/5] Iniciando Xvfb (display virtual :1)..."
Xvfb :1 -screen 0 1920x1080x24 &
XVFB_PID=$!
echo "  ✅ Xvfb iniciado (PID: $XVFB_PID) no display :1"
sleep 2

echo "[3/5] Verificando se x11vnc já está rodando..."
if pgrep -x "x11vnc" > /dev/null; then
    echo "  ⚠️  x11vnc já está rodando. Matando processo antigo..."
    pkill x11vnc || true
    sleep 2
fi

echo "[4/5] Iniciando x11vnc (VNC na porta 5900)..."
x11vnc -display :1 -forever -nopw -quiet -bg
echo "  ✅ x11vnc iniciado na porta 5900"
echo "  📺 Conecte via VNC: <IP_SERVIDOR>:5900"

echo "[5/5] Configurando ambiente Python..."
export DISPLAY=:1
export PYTHONPATH="$PROJECT_DIR"
source venv/bin/activate
echo "  ✅ Ambiente virtual ativado"
echo "  ✅ DISPLAY=:1 configurado"
echo "  ✅ PYTHONPATH=$PYTHONPATH"

echo ""
echo "=========================================="
echo "✅ AMBIENTE PRONTO!"
echo "=========================================="
echo ""
echo "📋 Próximos passos:"
echo "   1. Conecte via VNC: <seu-ip>:5900"
echo "   2. Execute o processador:"
echo "      python src/processors/web/titulos_abertos_e_marcados_recompras.py"
echo ""
echo "🛑 Para parar os serviços:"
echo "   pkill Xvfb && pkill x11vnc"
echo ""
echo "=========================================="
echo ""

# Manter o shell com ambiente ativado
exec bash
