#!/bin/sh
# run_agendado.sh - wrapper do hub para o job finalizar_operacao.
#
# ⚠️ Sem `--executar` este job NAO finaliza: confere, avisa e sai. A task do
#    hub comeca assim de proposito. Ligar a finalizacao e mudar o comando da
#    task, decisao de quem opera - nao um default escondido aqui.
#
# Slot deste job (reservado em docs/COMO_SUBIR_UM_JOB.md):
#    DISPLAY :92 | VNC 5907 | noVNC 6087 | CDP 9228
set -u
cd /app || exit 1
LOG=/app/logs/vnc; mkdir -p "$LOG"

# 1) credenciais (arquivo montado, fora do git)
[ -f /app/config/finalizar_operacao.env ] && { set -a; . /app/config/finalizar_operacao.env; set +a; }

# 2) mata Chrome orfao SO do nosso perfil (nunca pkill generico de chrome!)
PERFIL="${USER_DATA_DIR_R7:-/app/data/robo_finalizar/perfil_chrome}"
pkill -f "user-data-dir=$PERFIL" 2>/dev/null || true
sleep 1; rm -f "$PERFIL"/Singleton* 2>/dev/null || true

# 3-6) Xvfb :92 + fluxbox + x11vnc 5907 + websockify 6087 (idempotente)
if ! pgrep -f "Xvfb :92" >/dev/null 2>&1; then
    rm -f /tmp/.X92-lock /tmp/.X11-unix/X92 2>/dev/null || true
    Xvfb :92 -screen 0 1920x1080x24 -ac -nolisten tcp > "$LOG/xvfb92.log" 2>&1 &
    sleep 3
fi
pgrep -f "fluxbox.*:92" >/dev/null 2>&1 || (DISPLAY=:92 fluxbox > "$LOG/fluxbox92.log" 2>&1 &)
pgrep -f "x11vnc.*:92" >/dev/null 2>&1 || \
    (x11vnc -display :92 -forever -shared -rfbport 5907 -nopw > "$LOG/x11vnc92.log" 2>&1 &)
pgrep -f "websockify.*6087" >/dev/null 2>&1 || \
    (websockify --web=/usr/share/novnc 6087 localhost:5907 > "$LOG/novnc92.log" 2>&1 &)

# 7) ambiente
export DISPLAY=:92
export PYTHONPATH=/app
export PYTHONUNBUFFERED=1

# 8) roda e PROPAGA O EXIT CODE do python.
#    O hub chama este wrapper com `sh` (= dash aqui): o shebang nao vale e
#    ${PIPESTATUS[0]} e bashism. Sem o truque do $RC o hub le o exit do `tee`,
#    que e SEMPRE 0 - o job falha e a task fica verde.
LOG_JOB="/app/logs/finalizar_operacao_$(date +%Y-%m-%d).log"
RC="/tmp/finalizar_operacao_rc.$$"
{ python /app/src/processors/web/finalizar_operacao/finalizar_operacao.py "$@"; echo $? > "$RC"; } 2>&1 \
    | tee -a "$LOG_JOB"
CODIGO=$(cat "$RC" 2>/dev/null || echo 1); rm -f "$RC"
exit "$CODIGO"
