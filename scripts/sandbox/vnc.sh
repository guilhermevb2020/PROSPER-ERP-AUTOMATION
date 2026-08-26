#!/bin/sh
# vnc.sh - display proprio + VNC para o sandbox, NO HOST.
#
# Sobe, de forma idempotente:
#   Xvfb :90            display grafico proprio (nao colide com o :99 do container)
#   fluxbox             window manager (ajuda a ver o Chrome no VNC)
#   x11vnc  :0 -> 5910  servidor VNC do display :90
#   websockify 6090     noVNC web -> abre no navegador em http://HOST:6090/vnc.html
#
# SLOT DO SANDBOX (nao mexer sem conferir que esta livre no host):
#   display :90 | VNC 5910 | noVNC 6090
#   O container usa :99/5900/6080 (publicados no host) — por isso :90/5910/6090.
#
# PRE-REQUISITO (uma vez, com root):
#   sudo apt-get update && sudo apt-get install -y \
#        xvfb x11vnc websockify novnc fluxbox
#
# Sem esses binarios este script NAO instala nada (nao tem root) — ele avisa e
# sai. O sandbox continua funcionando headless (com video+trace) enquanto isso.
set -u

DISPLAY_NUM="${SANDBOX_DISPLAY_NUM:-90}"
VNC_PORT="${SANDBOX_VNC_PORT:-5910}"
NOVNC_PORT="${SANDBOX_NOVNC_PORT:-6090}"
GEOM="${SANDBOX_GEOM:-1920x1080x24}"
LOG="${SANDBOX_LOG_DIR:-/home/prospere/docker/automation/erp-automation/data/sandbox/vnc}"
mkdir -p "$LOG"

faltando=""
for bin in Xvfb x11vnc websockify fluxbox; do
    command -v "$bin" >/dev/null 2>&1 || faltando="$faltando $bin"
done
if [ -n "$faltando" ]; then
    echo "⛔ faltam binarios no host:$faltando"
    echo "   instale uma vez (com root):"
    echo "   sudo apt-get update && sudo apt-get install -y xvfb x11vnc websockify novnc fluxbox"
    echo "   ate la, use o sandbox headless (video+trace ja funcionam)."
    exit 3
fi

# 1) Xvfb :90
if ! pgrep -f "Xvfb :$DISPLAY_NUM" >/dev/null 2>&1; then
    rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}" 2>/dev/null || true
    Xvfb ":$DISPLAY_NUM" -screen 0 "$GEOM" -ac -nolisten tcp > "$LOG/xvfb${DISPLAY_NUM}.log" 2>&1 &
    sleep 3
    echo "Xvfb :$DISPLAY_NUM no ar"
else
    echo "Xvfb :$DISPLAY_NUM ja rodando"
fi

# 2) fluxbox (window manager)
pgrep -f "fluxbox.*:$DISPLAY_NUM" >/dev/null 2>&1 || \
    (DISPLAY=":$DISPLAY_NUM" fluxbox > "$LOG/fluxbox${DISPLAY_NUM}.log" 2>&1 &)

# 3) x11vnc do display :90 -> porta VNC
if ! pgrep -f "x11vnc.*-rfbport $VNC_PORT" >/dev/null 2>&1; then
    x11vnc -display ":$DISPLAY_NUM" -rfbport "$VNC_PORT" -forever -shared -nopw \
           -quiet -bg -o "$LOG/x11vnc${DISPLAY_NUM}.log" >/dev/null 2>&1
    echo "x11vnc no ar (porta $VNC_PORT)"
else
    echo "x11vnc ja rodando (porta $VNC_PORT)"
fi

# 4) noVNC web -> porta HTTP
if ! pgrep -f "websockify.*$NOVNC_PORT" >/dev/null 2>&1; then
    WEB=/usr/share/novnc
    [ -d "$WEB" ] || WEB=""
    websockify ${WEB:+--web=$WEB} "$NOVNC_PORT" "localhost:$VNC_PORT" \
        > "$LOG/novnc${DISPLAY_NUM}.log" 2>&1 &
    sleep 1
    echo "noVNC no ar (porta $NOVNC_PORT)"
else
    echo "noVNC ja rodando (porta $NOVNC_PORT)"
fi

echo ""
echo "pronto. Para o sandbox pintar aqui:  export SANDBOX_DISPLAY=:$DISPLAY_NUM  SANDBOX_HEADLESS=false"
echo "assista em:  http://<host>:$NOVNC_PORT/vnc.html   (ou VNC nativo na porta $VNC_PORT)"
