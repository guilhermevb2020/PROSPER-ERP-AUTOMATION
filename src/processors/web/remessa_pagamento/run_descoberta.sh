#!/bin/sh
# Wrapper da FASE 0 (reconhecimento da tela) — uso MANUAL, nunca agendado.
#
# Irmao do `run_agendado.sh`, e as diferencas sao deliberadas:
#   run_agendado.sh    trabalho de verdade, tem TRAVA (roda de 30 em 30 min)
#   run_descoberta.sh  so LE telas, e chamado a mao, sem trava
#
# Sem trava porque ninguem o dispara sozinho — mas ele USA O MESMO PERFIL do
# robo. Nao rode enquanto uma rodada agendada estiver em curso: o passo 2 mata o
# Chrome do perfil e mataria a rodada no meio. Confira antes:
#     cat /tmp/remessa_pagamento.lock 2>/dev/null && echo "TEM RODADA EM CURSO"
#
# Uso:
#   sh /app/src/processors/web/remessa_pagamento/run_descoberta.sh --links pagamento
#   sh .../run_descoberta.sh --url https://wvw.smartsecurities.com.br/smart/<tela>.php
set -u
cd /app || exit 1
LOG=/app/logs/vnc
mkdir -p "$LOG"

if [ -f /app/config/remessa_pagamento.env ]; then
    set -a
    . /app/config/remessa_pagamento.env
    set +a
fi

PERFIL="${USER_DATA_DIR_PAG:-/app/data/robo_pagamento/perfil_chrome}"
pkill -f "user-data-dir=$PERFIL" 2>/dev/null || true
sleep 1
rm -f "$PERFIL"/Singleton* 2>/dev/null || true

# Xvfb :94 + fluxbox + x11vnc 5905 + noVNC 6085 (idempotente, igual ao agendado)
if ! pgrep -f "Xvfb :94" >/dev/null 2>&1; then
    rm -f /tmp/.X94-lock /tmp/.X11-unix/X94 2>/dev/null || true
    Xvfb :94 -screen 0 1920x1080x24 -ac -nolisten tcp > "$LOG/xvfb94.log" 2>&1 &
    sleep 3
fi
pgrep -f "fluxbox.*:94" >/dev/null 2>&1 || (DISPLAY=:94 fluxbox > "$LOG/fluxbox94.log" 2>&1 &)
if ! pgrep -f "x11vnc.*-display :94" >/dev/null 2>&1; then
    [ -f /tmp/.vncpasswd ] && x11vnc -display :94 -rfbport 5905 -rfbauth /tmp/.vncpasswd \
        -forever -shared -bg -o "$LOG/x11vnc94.log" >/dev/null 2>&1 || true
fi
pgrep -f "websockify.*6085" >/dev/null 2>&1 || \
    (websockify --web=/usr/share/novnc/ 6085 localhost:5905 > "$LOG/novnc94.log" 2>&1 &)
sleep 1

export DISPLAY=:94
export PYTHONPATH=/app
export PYTHONUNBUFFERED=1
export USER_DATA_DIR_PAG="$PERFIL"
mkdir -p "$PERFIL"

LOGROBO="/app/logs/robo_pagamento_descoberta_$(date +%Y-%m-%d).log"
RC="/tmp/robo_pagamento_desc_rc.$$"
{ python /app/src/processors/web/remessa_pagamento/descobrir.py "$@"; echo $? > "$RC"; } \
    2>&1 | tee -a "$LOGROBO"
CODIGO=$(cat "$RC" 2>/dev/null || echo 1)
rm -f "$RC"
exit "$CODIGO"
