#!/bin/bash
# Wrapper script para iniciar noVNC com portas calculadas

DISPLAY_NUM=$1
VNC_PORT=$((5899 + DISPLAY_NUM))
WEB_PORT=$((6079 + DISPLAY_NUM))

cd /home/ubuntu/noVNC

if [ -f /home/ubuntu/noVNC/utils/novnc_proxy ]; then
    exec /home/ubuntu/noVNC/utils/novnc_proxy --vnc localhost:${VNC_PORT} --listen ${WEB_PORT}
elif command -v websockify >/dev/null 2>&1; then
    exec websockify --web=/usr/share/novnc/ ${WEB_PORT} localhost:${VNC_PORT}
else
    echo "noVNC não encontrado"
    exit 1
fi
