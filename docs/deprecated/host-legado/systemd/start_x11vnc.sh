#!/bin/bash
# Wrapper script para iniciar x11vnc com porta calculada

DISPLAY_NUM=$1
VNC_PORT=$((5899 + DISPLAY_NUM))

exec /usr/bin/x11vnc -display :${DISPLAY_NUM} -forever -nopw -shared -quiet -bg -rfbport ${VNC_PORT}
