#!/bin/sh
# Wrapper do robo que INSERE o retorno de PAGAMENTO no Smart (hub-orchestration chama isto).
# Garante o display :93 ISOLADO (Xvfb + x11vnc 5906 + noVNC 6086) — separado do
# :94 (remessa_pagamento), :95 (retorno_cobranca), :96 (credito), :97 (remessa), :98
# (doc2you) e :99 (boletos) — carrega credenciais e roda o robo UMA vez.
#
# O robo sobe o proprio Chrome, loga via CapSolver, insere cada .RET pendente
# em Processar Retorno e FECHA. Um login por run — mesmo desenho dos outros.
set -u
. /app/src/common/smart_financeiro_lock.sh
cd /app || exit 1
LOG=/app/logs/vnc
mkdir -p "$LOG"

# 1) credenciais do Smart — MESMA conta do remessa_pagamento (mesma tela, mesmo
#    modulo `pagtobmp`). Carrega o .env DELE primeiro (PAGAMENTO_EMAIL/SENHA),
#    depois o proprio (se existir), que so PRECISA ter DRY_RUN_RETPAG e afins —
#    nao duplica o segredo em dois arquivos.
if [ -f /app/config/remessa_pagamento.env ]; then
    set -a
    . /app/config/remessa_pagamento.env
    set +a
fi
if [ -f /app/config/retorno_pagamento.env ]; then
    set -a
    . /app/config/retorno_pagamento.env
    set +a
fi

# 2) limpa chrome residual do perfil do robo (de um run anterior que travou).
PERFIL="${USER_DATA_DIR_RETPAG:-/app/data/robo_retorno_pagamento/perfil_chrome}"
pkill -f "user-data-dir=$PERFIL" 2>/dev/null || true
sleep 1
rm -f "$PERFIL"/Singleton* 2>/dev/null || true

# 3) Xvfb :93
if ! pgrep -f "Xvfb :93" >/dev/null 2>&1; then
    rm -f /tmp/.X93-lock /tmp/.X11-unix/X93 2>/dev/null || true
    Xvfb :93 -screen 0 1920x1080x24 -ac -nolisten tcp > "$LOG/xvfb93.log" 2>&1 &
    sleep 3
fi

# 4) fluxbox :93 (window manager — Chrome abre melhor com WM)
pgrep -f "fluxbox.*:93" >/dev/null 2>&1 || (DISPLAY=:93 fluxbox > "$LOG/fluxbox93.log" 2>&1 &)

# 5) x11vnc :93 -> 5906 (debug: ver o robo trabalhando)
if ! pgrep -f "x11vnc.*-display :93" >/dev/null 2>&1; then
    [ -f /tmp/.vncpasswd ] && x11vnc -display :93 -rfbport 5906 -rfbauth /tmp/.vncpasswd \
        -forever -shared -bg -o "$LOG/x11vnc93.log" >/dev/null 2>&1 || true
fi

# 6) noVNC :93 -> 6086
pgrep -f "websockify.*6086" >/dev/null 2>&1 || \
    (websockify --web=/usr/share/novnc/ 6086 localhost:5906 > "$LOG/novnc93.log" 2>&1 &)

sleep 1

# 7) ambiente do robo
export DISPLAY=:93
export PYTHONPATH=/app
export PYTHONUNBUFFERED=1
export USER_DATA_DIR_RETPAG="$PERFIL"
mkdir -p "$PERFIL"
# DRY_RUN_RETPAG=True e o default do config: em dry-run o robo baixa o .RET do
# Nextcloud, monta o multipart e MOSTRA o que mandaria — nao faz o POST. Para
# valer, ponha DRY_RUN_RETPAG=false em retorno_pagamento.env — e confira
# o valor efetivo depois de editar (ver aviso de calibracao em retorno_pagamento.py).
export DRY_RUN_RETPAG="${DRY_RUN_RETPAG:-True}"

# 8) roda o robo (uma vez, e sai). exit code do PYTHON, nao do tee (que e
#    sempre 0) — o hub le o exit code; PIPESTATUS e bashism e este wrapper
#    roda em dash via `sh`.
LOGROBO="/app/logs/robo_retorno_pagamento_$(date +%Y-%m-%d).log"
RC="/tmp/robo_retorno_pagamento_rc.$$"
echo "===== inicio $(date '+%F %T %Z') =====" >> "$LOGROBO"
{ python /app/src/processors/web/retorno_pagamento/processar_retorno_pagamento.py \
      "$@"; echo $? > "$RC"; } 2>&1 | tee -a "$LOGROBO"
CODIGO=$(cat "$RC" 2>/dev/null || echo 1)
rm -f "$RC"
echo "===== fim $(date '+%F %T %Z') exit=$CODIGO =====" >> "$LOGROBO"
exit "$CODIGO"
