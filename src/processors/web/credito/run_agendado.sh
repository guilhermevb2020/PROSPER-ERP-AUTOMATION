#!/bin/sh
# Wrapper do robo de analise de credito (chamado pelo hub-orchestration).
# Garante o display :96 ISOLADO (Xvfb + x11vnc 5902 + noVNC 6082) — separado do
# :98 (doc2you) e :99 (boletos) — carrega credenciais/flags e roda o robo em LOOP.
# Idempotente: sobe so o que faltar (funciona mesmo apos restart do container, sem
# depender do boot e SEM tocar nos boletos/doc2you).
#
# O hub INICIA via cron (7:45 dias uteis); o robo PARA SOZINHO as 18:50 (opcao B,
# guarda de janela no loop). VNC de acompanhamento: vnc.prospereinvest.com.br/rc/
set -u
cd /app || exit 1
LOG=/app/logs/vnc
mkdir -p "$LOG"

# 1) credenciais + flags (arquivo montado, gitignored). SOBRESCREVE o SMART_EMAIL
#    do container (que e felipe_p de outra automacao) por Raphaelas.
if [ -f /app/config/credito.env ]; then
    set -a
    . /app/config/credito.env
    set +a
fi

# 2) limpa chrome residual do perfil do robo (de um run anterior que travou)
PERFIL="${USER_DATA_DIR:-/app/data/robo_credito/perfil_chrome}"
pkill -f "user-data-dir=$PERFIL" 2>/dev/null || true
sleep 1
rm -f "$PERFIL"/Singleton* 2>/dev/null || true

# 3) Xvfb :96
if ! pgrep -f "Xvfb :96" >/dev/null 2>&1; then
    rm -f /tmp/.X96-lock /tmp/.X11-unix/X96 2>/dev/null || true
    Xvfb :96 -screen 0 1920x1080x24 -ac -nolisten tcp > "$LOG/xvfb96.log" 2>&1 &
    sleep 3
fi

# 4) fluxbox :96 (window manager — Chrome abre melhor com WM)
pgrep -f "fluxbox.*:96" >/dev/null 2>&1 || (DISPLAY=:96 fluxbox > "$LOG/fluxbox96.log" 2>&1 &)

# 5) x11vnc :96 -> 5902 (debug via vnc.prospereinvest.com.br/rc/)
if ! pgrep -f "x11vnc.*-display :96" >/dev/null 2>&1; then
    [ -f /tmp/.vncpasswd ] && x11vnc -display :96 -rfbport 5902 -rfbauth /tmp/.vncpasswd \
        -forever -shared -bg -o "$LOG/x11vnc96.log" >/dev/null 2>&1 || true
fi

# 6) noVNC :96 -> 6082
pgrep -f "websockify.*6082" >/dev/null 2>&1 || \
    (websockify --web=/usr/share/novnc/ 6082 localhost:5902 > "$LOG/novnc96.log" 2>&1 &)

sleep 1

# 7) ambiente do robo
export DISPLAY=:96
export PYTHONPATH=/app                       # p/ resolver o `src.common.clients...`
export PYTHONUNBUFFERED=1
export USER_DATA_DIR="$PERFIL"
mkdir -p "$PERFIL"
# defaults de producao (o .env acima pode sobrescrever)
export USAR_BANCO_DOWNLOAD="${USAR_BANCO_DOWNLOAD:-False}"
export CLASSE_RISCO_APLICAR="${CLASSE_RISCO_APLICAR:-1}"
export SALVAR_NEXTCLOUD="${SALVAR_NEXTCLOUD:-True}"
export SKIP_DIGITAIS="${SKIP_DIGITAIS:-False}"
export DRY_RUN="${DRY_RUN:-False}"

# 8) roda o job (loop infinito; para sozinho as 18:50). Script direto: o dir do
#    script vira sys.path[0] (imports flat) e o PYTHONPATH=/app resolve `src.*`.
#    `tee` grava um LOG AO VIVO (observabilidade) alem do stdout capturado pelo hub.
LOG_JOB="/app/logs/credito_$(date +%Y-%m-%d).log"
echo "===== inicio $(date '+%F %T %Z') =====" >> "$LOG_JOB"
# BEGIN EXECUCAO_CREDITO
# sh nao possui PIPESTATUS: preservar o retorno do Python, como no retorno_cobranca.
RC_CREDITO=$(mktemp "${TMPDIR:-/tmp}/credito_rc.XXXXXX") || exit 1
trap 'rm -f "$RC_CREDITO"' EXIT
{ python /app/src/processors/web/credito/analisar_credito.py "$@";
  echo $? > "$RC_CREDITO";
} 2>&1 | tee -a "$LOG_JOB"
CODIGO_CREDITO=$(cat "$RC_CREDITO" 2>/dev/null)
case "$CODIGO_CREDITO" in ''|*[!0-9]*) CODIGO_CREDITO=1 ;; esac
echo "===== fim $(date '+%F %T %Z') exit=$CODIGO_CREDITO =====" >> "$LOG_JOB"
exit "$CODIGO_CREDITO"
