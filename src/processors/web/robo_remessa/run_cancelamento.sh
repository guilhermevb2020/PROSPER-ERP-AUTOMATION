#!/bin/sh
# Wrapper do CANCELAMENTO de remessa recusada (chamado pelo hub-orchestration).
#
# ⛔ POR QUE ELE EXISTE, e nao basta chamar o python direto: a conta financeira
# do Smart permite UMA sessao, mesmo com perfis e displays diferentes. Os outros
# cinco robos entram pelo `smart_financeiro_lock.sh`; um cancelamento fora dele
# brigaria pela sessao com a geracao das 18:00 e com o `emitir_lote_boletos_tarde`
# das 17:30, no mesmo container.
#
# ⛔ E ELE NAO CANCELA SEM `--pra-valer`. Diferente da geracao, o cancelamento
# nao herda o `DRY_RUN_REM` do ambiente — e a unica acao deste robo assim. Gerar
# de novo e recuperavel: a remessa sai e alguem a cancela. Cancelar NAO e: os
# titulos voltam a fila e o sequencial daquela remessa morre.
#
# ⚠️ A LISTA MANDA. Quem decide o que cancelar e o `apontar_cancelamentos_remessa_400`
# (process-automation), que pergunta ao banco quais boletos existem. Lista vencida
# (12 h) o robo recusa sozinho: a prova de que o boleto nao esta no banco caduca.
#
# Display :97 — o MESMO da geracao, de proposito: as duas mexem na mesma tela e
# o lock ja as serializa. Subir um display novo so criaria Chrome orfao.
set -u
. /app/src/common/smart_financeiro_lock.sh
cd /app || exit 1
LOG=/app/logs/vnc
mkdir -p "$LOG"

if [ -f /app/config/robo_remessa.env ]; then
    set -a
    . /app/config/robo_remessa.env
    set +a
fi

PERFIL="${USER_DATA_DIR_REM:-/app/data/robo_remessa/perfil_chrome}"
pkill -f "user-data-dir=$PERFIL" 2>/dev/null || true
sleep 1
rm -f "$PERFIL"/Singleton* 2>/dev/null || true

if ! pgrep -f "Xvfb :97" >/dev/null 2>&1; then
    rm -f /tmp/.X97-lock /tmp/.X11-unix/X97 2>/dev/null || true
    Xvfb :97 -screen 0 1920x1080x24 -ac -nolisten tcp > "$LOG/xvfb97.log" 2>&1 &
    sleep 3
fi
pgrep -f "fluxbox.*:97" >/dev/null 2>&1 || (DISPLAY=:97 fluxbox > "$LOG/fluxbox97.log" 2>&1 &)

export DISPLAY=:97
export PYTHONPATH=/app
export PYTHONUNBUFFERED=1
export USER_DATA_DIR_REM="$PERFIL"
mkdir -p "$PERFIL"

# ⚠️ O exit code que o hub precisa ver e o do PYTHON, nao o do `tee`. `PIPESTATUS`
# e bashism e o hub chama com `sh`, que aqui e DASH — dai o arquivo de retorno.
LOGROBO="/app/logs/robo_remessa_$(date +%Y-%m-%d).log"
RC="/tmp/robo_cancelamento_rc.$$"
echo "===== cancelamento inicio $(date '+%F %T %Z') =====" >> "$LOGROBO"
{ python /app/src/processors/web/robo_remessa/robo_remessa.py --cancelar "$@"; echo $? > "$RC"; } 2>&1 | tee -a "$LOGROBO"
CODIGO=$(cat "$RC" 2>/dev/null || echo 1)
rm -f "$RC"
echo "===== cancelamento fim $(date '+%F %T %Z') exit=$CODIGO =====" >> "$LOGROBO"
exit "$CODIGO"
