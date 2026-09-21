#!/bin/bash
# ================================================================================
# Configurar display :2 para segundo processador (Relatórios/Operações)
# ================================================================================

echo "==================================================="
echo "Configurando Display :2 para processador paralelo"
echo "==================================================="

# Parar processos anteriores se existirem
pkill -f "Xvfb :2" 2>/dev/null
pkill -f "x11vnc.*5901" 2>/dev/null
pkill -f "novnc_proxy.*6081" 2>/dev/null
sleep 2

# 1. Iniciar Xvfb no display :2
echo "[1/3] Iniciando Xvfb no display :2..."
Xvfb :2 -screen 0 1920x1080x24 > /dev/null 2>&1 &
sleep 2
echo "  ✅ Xvfb iniciado"

# 2. Iniciar x11vnc na porta 5901 (sem senha)
echo "[2/3] Iniciando x11vnc na porta 5901 (SEM SENHA)..."
x11vnc -display :2 -forever -nopw -shared -quiet -bg -rfbport 5901
echo "  ✅ x11vnc iniciado (porta 5901, display :2)"

# 3. Iniciar noVNC na porta 6081
echo "[3/3] Iniciando noVNC na porta 6081..."
cd /home/ubuntu/noVNC
nohup ./utils/novnc_proxy --vnc localhost:5901 --listen 6081 > /tmp/novnc_6081.log 2>&1 &
sleep 3
echo "  ✅ noVNC iniciado (porta 6081)"

echo ""
echo "============================"
echo "✅ AMBIENTE CONFIGURADO!"
echo "============================"
echo ""
echo "  Display :1 → VNC 6080 (Títulos Abertos)"
echo "  Display :2 → VNC 6081 (Relatórios/Operações)"
echo ""
echo "  Acesse: http://3.148.126.73:6081/vnc.html"
echo ""
