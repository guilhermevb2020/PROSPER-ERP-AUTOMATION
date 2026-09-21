#!/bin/sh
# Wrapper do job agendado do doc2you (chamado pelo hub-orchestration).
# Garante o display :98 ISOLADO (Xvfb + x11vnc 5901 + noVNC 6081) — separado do :99
# dos boletos — e roda o job. Idempotente: sobe só o que faltar. Assim funciona
# mesmo após um restart do container, SEM depender do boot e SEM tocar nos boletos.
set -u
cd /app || exit 1
LOG=/app/logs/vnc
mkdir -p "$LOG"

# 1) limpa chrome residual do perfil doc2you (de algum run anterior que travou)
pkill -f "user-data-dir=/app/data/doc2you/perfil_chrome" 2>/dev/null || true
sleep 1

# 2) Xvfb :98
if ! pgrep -f "Xvfb :98" >/dev/null 2>&1; then
    rm -f /tmp/.X98-lock /tmp/.X11-unix/X98 2>/dev/null || true
    Xvfb :98 -screen 0 1920x1080x24 -ac -nolisten tcp > "$LOG/xvfb98.log" 2>&1 &
    sleep 3
fi

# 3) fluxbox :98 (window manager — ajuda no VNC de debug)
pgrep -f "fluxbox" >/dev/null 2>&1 || (DISPLAY=:98 fluxbox > "$LOG/fluxbox98.log" 2>&1 &)

# 4) x11vnc :98 -> 5901 (debug via vnc.prospereinvest.com.br/d2/)
if ! pgrep -f "x11vnc.*-display :98" >/dev/null 2>&1; then
    [ -f /tmp/.vncpasswd ] && x11vnc -display :98 -rfbport 5901 -rfbauth /tmp/.vncpasswd \
        -forever -shared -bg -o "$LOG/x11vnc98.log" >/dev/null 2>&1 || true
fi

# 5) noVNC :98 -> 6081
pgrep -f "websockify.*6081" >/dev/null 2>&1 || \
    (websockify --web=/usr/share/novnc/ 6081 localhost:5901 > "$LOG/novnc98.log" 2>&1 &)

sleep 1
export DISPLAY=:98
exec python -m src.processors.web.doc2you.baixar_dia "$@"
