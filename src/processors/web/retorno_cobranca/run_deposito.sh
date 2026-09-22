#!/bin/sh
# Wrapper da automação de retorno para a BAIXA POR DEPOSITO — chamado pelo hub-orchestration.
#
# ⭐ Irmao do `run_agendado.sh`, e as diferencas sao TODAS deliberadas:
#
#   run_agendado.sh   varre a arvore do Nextcloud (5 dias-pasta), retorno REAL do banco,
#                     sem portao (o arquivo e do banco: nao ha "nosso intento" a conferir)
#   run_deposito.sh   varre UMA pasta privada, arquivo que NOS fabricamos,
#                     ⭐ COM --portao SEMPRE
#
# ⛔ **O `--portao` aqui NAO e opcional, e por isso esta chumbado nesta linha e nao numa
# variavel.** O arquivo que entra por aqui foi montado por nos a partir de
# `financeiro.deposito_conciliado` — ou seja, tem intento nosso, e conferir o que o Smart
# resolveu contra o que mandamos e a unica defesa contra o `BUG-548` (a baixa que entrou
# no titulo de OUTRO sacado). No retorno do banco essa conferencia nao faz sentido;
# aqui ela e a razao de o passo existir.
#
# ⛔ A pasta e `_deposito`, SUBPASTA de propósito: a automação de retorno nao desce um nivel, entao
# nenhuma rodada agendada de retorno bancario a alcanca por acidente.
#
# ⚠️ Horario: `40 9,17 * * 1-5`, cinco minutos depois do `baixar_deposito_erp` (35) e
# DEZ minutos antes do `processar_retornos_cnab` (50). A folga dos dois lados existe
# porque os dois usam o MESMO perfil do Chrome, e o `run_agendado.sh` mata o perfil na
# largada — sobrepor as duas rodadas mata uma delas no meio.
set -u
# Trava por CONTA do Smart, nao por projeto: esta familia entra como `prosperito`; a de
# pagamento entra como `prosperito_financeiro` e fica na trava original. Uma trava so para
# as duas fazia a remessa de cobranca das 18h (18-29 min) derrubar o pagamento das
# 18h00-18h20 todo dia util, sem ganho nenhum: contas diferentes nao disputam sessao.
# Medido em 22/09/2026 sobre 10 dias. A variavel continua sobreponivel por ambiente.
TRAVA_SMART_FINANCEIRO="${TRAVA_SMART_FINANCEIRO:-/tmp/smart_cobranca.lock}"
. /app/src/common/smart_financeiro_lock.sh
cd /app || exit 1
LOG=/app/logs/vnc
mkdir -p "$LOG"

if [ -f /app/config/retorno_cobranca.env ]; then
    set -a
    . /app/config/retorno_cobranca.env
    set +a
fi

PERFIL="${USER_DATA_DIR_RET:-/app/data/robo_retorno/perfil_chrome}"
pkill -f "user-data-dir=$PERFIL" 2>/dev/null || true
sleep 1
rm -f "$PERFIL"/Singleton* 2>/dev/null || true

# Xvfb :95 — mesmo slot da automação de retorno de retorno, e e de propósito: e o mesmo automação, com o
# mesmo perfil e a mesma sessao do Smart. Slot proprio exigiria login proprio.
if ! pgrep -f "Xvfb :95" >/dev/null 2>&1; then
    rm -f /tmp/.X95-lock /tmp/.X11-unix/X95 2>/dev/null || true
    Xvfb :95 -screen 0 1920x1080x24 -ac -nolisten tcp > "$LOG/xvfb95.log" 2>&1 &
    sleep 3
fi
pgrep -f "fluxbox.*:95" >/dev/null 2>&1 || (DISPLAY=:95 fluxbox > "$LOG/fluxbox95.log" 2>&1 &)

export DISPLAY=:95
export PYTHONPATH=/app
export PYTHONUNBUFFERED=1
export USER_DATA_DIR_RET="$PERFIL"
mkdir -p "$PERFIL"

PASTA="${PASTA_DEPOSITO_RET:-/app/data/retornos_a_processar/_deposito}"
LOG_JOB="/app/logs/retorno_cobranca_deposito_$(date +%Y-%m-%d).log"

if [ ! -d "$PASTA" ]; then
    echo "[$(date '+%F %T')] sem pasta ($PASTA) — nada a processar" >> "$LOG_JOB"
    exit 0
fi

# ⭐ Sai 0 quando nao ha arquivo: fila vazia e o caso NORMAL (so ha arquivo quando um
# deposito conciliou e ainda nao foi baixado). Marcar falha num dia sem deposito
# ensinaria a ignorar o alarme.
if [ -z "$(ls "$PASTA"/*.RET "$PASTA"/*.ret 2>/dev/null)" ]; then
    echo "[$(date '+%F %T')] nenhum .RET em $PASTA — nada a baixar" >> "$LOG_JOB"
    exit 0
fi

echo "===== inicio $(date '+%F %T %Z') =====" >> "$LOG_JOB"
RC="/tmp/retorno_cobranca_deposito_rc.$$"
# ⛔ `--pular-processados` NAO e opcional aqui, e custou uma baixa dupla para eu
# aprender: em 21/08/2026 esta rodada reprocessou `DEP2108261035345.RET` porque o
# arquivo continua na pasta (`MOVER_PROCESSADOS_RET=False`, imposto pela montagem `:ro`
# do Nextcloud) e sem a flag a automação de retorno NAO consulta o hash do controle. O Smart aceitou de
# novo — contou em `refinan` em vez de `liquidacao` e por sorte nao criou segunda
# quitacao. ⚠️ Sorte nao e desenho: a flag e a trava.
{ python /app/src/processors/web/retorno_cobranca/processar_retorno_cobranca.py \
      --pasta "$PASTA" --deposito --portao --detalhes --pra-valer \
      --pular-processados --recibos-dir "$PASTA/_RESULTADOS" "$@"; \
  echo $? > "$RC"; } 2>&1 | tee -a "$LOG_JOB"
CODIGO=$(cat "$RC" 2>/dev/null || echo 1)
rm -f "$RC"

# O Python move CADA arquivo individualmente, sem sobrescrever:
#   aprovado e comprovado -> _PROCESSADOS
#   recusado antes da baixa -> _REJEITADOS
#   resposta inconclusiva depois do passo irreversivel -> _INCONCLUSIVOS
# Erro operacional anterior ao passo irreversivel permanece na entrada para retry.
# O recibo JSON fica em _RESULTADOS e e a ponte auditavel com process-automation.

echo "===== fim $(date '+%F %T %Z') exit=$CODIGO =====" >> "$LOG_JOB"
exit "$CODIGO"
