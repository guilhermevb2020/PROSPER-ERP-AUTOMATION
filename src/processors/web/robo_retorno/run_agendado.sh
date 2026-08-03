#!/bin/sh
# Wrapper do robo de REMESSA CNAB (chamado pelo hub-orchestration).
# Garante o display :95 ISOLADO (Xvfb + x11vnc 5904 + noVNC 6084) — separado do
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
if [ -f /app/config/robo_retorno.env ]; then
    set -a
    . /app/config/robo_retorno.env
    set +a
fi

# 2) limpa chrome residual do perfil do robo (de um run anterior que travou).
#    Sem isso o perfil fica com lock e o launch_persistent_context nao sobe.
PERFIL="${USER_DATA_DIR_RET:-/app/data/robo_retorno/perfil_chrome}"
pkill -f "user-data-dir=$PERFIL" 2>/dev/null || true
sleep 1
rm -f "$PERFIL"/Singleton* 2>/dev/null || true

# 3) Xvfb :95
if ! pgrep -f "Xvfb :95" >/dev/null 2>&1; then
    rm -f /tmp/.X95-lock /tmp/.X11-unix/X95 2>/dev/null || true
    Xvfb :95 -screen 0 1920x1080x24 -ac -nolisten tcp > "$LOG/xvfb95.log" 2>&1 &
    sleep 3
fi

# 4) fluxbox :95 (window manager — Chrome abre melhor com WM)
pgrep -f "fluxbox.*:95" >/dev/null 2>&1 || (DISPLAY=:95 fluxbox > "$LOG/fluxbox95.log" 2>&1 &)

# 5) x11vnc :95 -> 5904 (debug: ver o robo trabalhando)
if ! pgrep -f "x11vnc.*-display :95" >/dev/null 2>&1; then
    [ -f /tmp/.vncpasswd ] && x11vnc -display :95 -rfbport 5904 -rfbauth /tmp/.vncpasswd \
        -forever -shared -bg -o "$LOG/x11vnc95.log" >/dev/null 2>&1 || true
fi

# 6) noVNC :95 -> 6084
pgrep -f "websockify.*6084" >/dev/null 2>&1 || \
    (websockify --web=/usr/share/novnc/ 6084 localhost:5904 > "$LOG/novnc95.log" 2>&1 &)

sleep 1

# 7) ambiente do robo
export DISPLAY=:95
export PYTHONPATH=/app                       # p/ resolver `src.processors.web.boletos...`
export PYTHONUNBUFFERED=1
export USER_DATA_DIR_RET="$PERFIL"
mkdir -p "$PERFIL"
# DRY_RUN_RET=True e o default do config: em dry-run o robo vai ate o UPLOAD
# (valida banco/conta e conta os titulos) e PARA antes do PROCESSAR_ARQUIVO, que
# e quem DA A BAIXA nos titulos. Para valer, ponha DRY_RUN_RET=false no
# robo_retorno.env — e confira o valor efetivo depois de editar o arquivo.
export DRY_RUN_RET="${DRY_RUN_RET:-True}"

# 8) roda o robo (uma vez, e sai). `tee` grava um log AO VIVO alem do stdout
#    capturado pelo hub.
#
#    O exit code que o hub precisa ver e o do PYTHON, nao o do `tee` (que e
#    sempre 0). `PIPESTATUS` resolveria, mas e bashism e o hub chama este
#    wrapper com `sh ...`, que aqui e DASH — o shebang nao vale nesse caso.
#    Dai o arquivo de retorno, que funciona nos dois shells.
LOGROBO="/app/logs/robo_retorno_$(date +%Y-%m-%d).log"
RC="/tmp/robo_retorno_rc.$$"
echo "===== inicio $(date '+%F %T %Z') =====" >> "$LOGROBO"
{ python /app/src/processors/web/robo_retorno/robo_retorno.py \
      "$@"; echo $? > "$RC"; } 2>&1 | tee -a "$LOGROBO"
CODIGO=$(cat "$RC" 2>/dev/null || echo 1)
rm -f "$RC"
echo "===== fim $(date '+%F %T %Z') exit=$CODIGO =====" >> "$LOGROBO"
exit "$CODIGO"
