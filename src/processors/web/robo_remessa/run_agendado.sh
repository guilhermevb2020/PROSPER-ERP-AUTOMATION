#!/bin/sh
# Wrapper do robo de REMESSA CNAB (chamado pelo hub-orchestration).
# Garante o display :97 ISOLADO (Xvfb + x11vnc 5903 + noVNC 6083) — separado do
# :96 (credito), :98 (doc2you) e :99 (boletos) — carrega credenciais e roda o
# robo UMA vez. Idempotente: sobe so o que faltar (funciona mesmo apos restart
# do container, sem depender do boot e SEM tocar nos outros robos).
#
# O robo sobe o proprio Chrome, loga via CapSolver, percorre as contas, baixa os
# .REM e FECHA. Um login por run — mesmo desenho do doc2you.
set -u
cd /app || exit 1
LOG=/app/logs/vnc
mkdir -p "$LOG"

# 1) credenciais + flags (arquivo montado, gitignored). SOBRESCREVE o SMART_EMAIL
#    do container (que e felipe_p, de outra automacao).
if [ -f /app/config/robo_remessa.env ]; then
    set -a
    . /app/config/robo_remessa.env
    set +a
fi

# 2) limpa chrome residual do perfil do robo (de um run anterior que travou).
#    Sem isso o perfil fica com lock e o launch_persistent_context nao sobe.
PERFIL="${USER_DATA_DIR_REM:-/app/data/robo_remessa/perfil_chrome}"
pkill -f "user-data-dir=$PERFIL" 2>/dev/null || true
sleep 1
rm -f "$PERFIL"/Singleton* 2>/dev/null || true

# 3) Xvfb :97
if ! pgrep -f "Xvfb :97" >/dev/null 2>&1; then
    rm -f /tmp/.X97-lock /tmp/.X11-unix/X97 2>/dev/null || true
    Xvfb :97 -screen 0 1920x1080x24 -ac -nolisten tcp > "$LOG/xvfb97.log" 2>&1 &
    sleep 3
fi

# 4) fluxbox :97 (window manager — Chrome abre melhor com WM)
pgrep -f "fluxbox.*:97" >/dev/null 2>&1 || (DISPLAY=:97 fluxbox > "$LOG/fluxbox97.log" 2>&1 &)

# 5) x11vnc :97 -> 5903 (debug: ver o robo trabalhando)
if ! pgrep -f "x11vnc.*-display :97" >/dev/null 2>&1; then
    [ -f /tmp/.vncpasswd ] && x11vnc -display :97 -rfbport 5903 -rfbauth /tmp/.vncpasswd \
        -forever -shared -bg -o "$LOG/x11vnc97.log" >/dev/null 2>&1 || true
fi

# 6) noVNC :97 -> 6083
pgrep -f "websockify.*6083" >/dev/null 2>&1 || \
    (websockify --web=/usr/share/novnc/ 6083 localhost:5903 > "$LOG/novnc97.log" 2>&1 &)

sleep 1

# 7) ambiente do robo
export DISPLAY=:97
export PYTHONPATH=/app                       # p/ resolver `src.processors.web.boletos...`
export PYTHONUNBUFFERED=1
export USER_DATA_DIR_REM="$PERFIL"
mkdir -p "$PERFIL"
# DRY_RUN_REM=True e o default do config: gerar consome sequencial e tira titulo
# da fila. Para valer, ponha DRY_RUN_REM=false no robo_remessa.env.
export DRY_RUN_REM="${DRY_RUN_REM:-True}"

# 8) roda o robo (uma vez, e sai). `tee` grava um log AO VIVO alem do stdout
#    capturado pelo hub.
#
#    O exit code que o hub precisa ver e o do PYTHON, nao o do `tee` (que e
#    sempre 0). `PIPESTATUS` resolveria, mas e bashism e o hub chama este
#    wrapper com `sh ...`, que aqui e DASH — o shebang nao vale nesse caso.
#    Dai o arquivo de retorno, que funciona nos dois shells.
LOGROBO="/app/logs/robo_remessa_$(date +%Y-%m-%d).log"
RC="/tmp/robo_remessa_rc.$$"
echo "===== inicio $(date '+%F %T %Z') =====" >> "$LOGROBO"
{ python /app/src/processors/web/robo_remessa/robo_remessa.py \
      --gerar --todas-contas "$@"; echo $? > "$RC"; } 2>&1 | tee -a "$LOGROBO"
CODIGO=$(cat "$RC" 2>/dev/null || echo 1)
rm -f "$RC"
echo "===== fim $(date '+%F %T %Z') exit=$CODIGO =====" >> "$LOGROBO"
exit "$CODIGO"
