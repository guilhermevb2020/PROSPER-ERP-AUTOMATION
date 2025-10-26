#!/bin/bash
# ============================================================================
# SCRIPT: restart_environment.sh
# DESCRIÇÃO: Para tudo e reinicia ambiente completo (Xvfb + VNC + Automação)
# USO: ./restart_environment.sh
# ============================================================================

set -e  # Parar se houver erro

echo "================================================================================"
echo "🔄 REINICIANDO AMBIENTE COMPLETO"
echo "================================================================================"
echo

# ============================================================================
# PASSO 1: PARAR TUDO
# ============================================================================
echo "[1/6] 🛑 Parando todos os processos..."

pkill -9 chrome 2>/dev/null || true
pkill -9 chromium 2>/dev/null || true
pkill -9 Xvfb 2>/dev/null || true
pkill -9 x11vnc 2>/dev/null || true
pkill -f novnc_proxy 2>/dev/null || true
pkill -f websockify 2>/dev/null || true
pkill -f "python.*titulos_abertos" 2>/dev/null || true

echo "   ✅ Processos antigos encerrados"

# Limpar locks do X11
rm -f /tmp/.X1-lock 2>/dev/null || true
rm -rf /tmp/.X11-unix/X1 2>/dev/null || true

echo "   ✅ Locks do X11 removidos"
echo

# Aguardar tudo fechar
sleep 3

# ============================================================================
# PASSO 2: INICIAR XVFB
# ============================================================================
echo "[2/6] 🖥️  Iniciando Xvfb (Display Virtual :1)..."

Xvfb :1 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset 2>/dev/null &
XVFB_PID=$!

sleep 3

# Verificar se Xvfb iniciou
if ps -p $XVFB_PID > /dev/null; then
    echo "   ✅ Xvfb iniciado (PID: $XVFB_PID)"
else
    echo "   ❌ ERRO: Xvfb não iniciou!"
    exit 1
fi
echo

# ============================================================================
# PASSO 3: INICIAR X11VNC
# ============================================================================
echo "[3/6] 📺 Iniciando x11vnc (Porta 5900)..."

x11vnc -display :1 -forever -nopw -quiet -bg -rfbport 5900 2>/dev/null

sleep 2

# Verificar se x11vnc está rodando
if netstat -tlnp 2>/dev/null | grep -q ":5900"; then
    echo "   ✅ x11vnc rodando na porta 5900"
else
    echo "   ⚠️  AVISO: x11vnc pode não ter iniciado corretamente"
fi
echo

# ============================================================================
# PASSO 4: INICIAR NOVNC
# ============================================================================
echo "[4/6] 🌐 Iniciando noVNC (Porta 6080)..."

# Tentar encontrar novnc_proxy
NOVNC_PROXY=""

if [ -f "/usr/share/novnc/utils/novnc_proxy" ]; then
    NOVNC_PROXY="/usr/share/novnc/utils/novnc_proxy"
elif [ -f "/usr/share/novnc/utils/launch.sh" ]; then
    NOVNC_PROXY="/usr/share/novnc/utils/launch.sh"
elif command -v websockify &> /dev/null; then
    # Usar websockify diretamente
    websockify --web=/usr/share/novnc/ 6080 localhost:5900 &>/dev/null &
    sleep 2
    NOVNC_PROXY="websockify"
fi

if [ -n "$NOVNC_PROXY" ] && [ "$NOVNC_PROXY" != "websockify" ]; then
    $NOVNC_PROXY --vnc localhost:5900 --listen 6080 &>/dev/null &
    sleep 2
fi

# Verificar se noVNC está rodando
if netstat -tlnp 2>/dev/null | grep -q ":6080"; then
    echo "   ✅ noVNC rodando na porta 6080"
else
    echo "   ⚠️  AVISO: noVNC pode não ter iniciado"
    echo "   💡 Tente acessar diretamente: vncviewer 3.148.126.73:5900"
fi
echo

# ============================================================================
# PASSO 5: CONFIGURAR AMBIENTE PYTHON
# ============================================================================
echo "[5/6] 🐍 Configurando ambiente Python..."

cd /home/ubuntu/PROSPER-ERP-AUTOMATION

# Ativar venv
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "   ✅ Ambiente virtual ativado"
else
    echo "   ⚠️  AVISO: venv não encontrado"
fi

# Configurar variáveis
export PYTHONPATH=/home/ubuntu/PROSPER-ERP-AUTOMATION
export DISPLAY=:1

echo "   ✅ PYTHONPATH configurado"
echo "   ✅ DISPLAY=:1 configurado"
echo

# ============================================================================
# PASSO 6: RESUMO E PRÓXIMOS PASSOS
# ============================================================================
echo "[6/6] ✅ AMBIENTE PRONTO!"
echo
echo "================================================================================"
echo "📊 STATUS DOS SERVIÇOS:"
echo "================================================================================"

# Verificar Xvfb
if ps aux | grep -v grep | grep -q "Xvfb :1"; then
    echo "   ✅ Xvfb       : Rodando"
else
    echo "   ❌ Xvfb       : NÃO está rodando!"
fi

# Verificar x11vnc
if netstat -tlnp 2>/dev/null | grep -q ":5900"; then
    echo "   ✅ x11vnc     : Rodando (porta 5900)"
else
    echo "   ❌ x11vnc     : NÃO está rodando!"
fi

# Verificar noVNC
if netstat -tlnp 2>/dev/null | grep -q ":6080"; then
    echo "   ✅ noVNC      : Rodando (porta 6080)"
else
    echo "   ❌ noVNC      : NÃO está rodando!"
fi

echo
echo "================================================================================"
echo "🚀 PRÓXIMOS PASSOS:"
echo "================================================================================"
echo
echo "1. Acesse o VNC no navegador:"
echo "   👉 http://3.148.126.73:6080/vnc.html"
echo
echo "2. Execute a automação:"
echo "   👉 ./run_processor.sh"
echo
echo "   OU diretamente:"
echo "   👉 python3 src/processors/web/titulos_abertos_e_marcados_recompras.py"
echo
echo "================================================================================"
echo "✅ SCRIPT CONCLUÍDO!"
echo "================================================================================"
