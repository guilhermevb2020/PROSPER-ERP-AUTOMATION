#!/bin/sh
# Retornos BB reconstruídos: conta exata, portão e recibos duráveis.
set -eu
RAIZ="${RAIZ_BB_RETORNO:-/app}"
# Trava por CONTA do Smart, nao por projeto: esta familia entra como `prosperito`; a de
# pagamento entra como `prosperito_financeiro` e fica na trava original. Uma trava so para
# as duas fazia a remessa de cobranca das 18h (18-29 min) derrubar o pagamento das
# 18h00-18h20 todo dia util, sem ganho nenhum: contas diferentes nao disputam sessao.
# Medido em 22/09/2026 sobre 10 dias. A variavel continua sobreponivel por ambiente.
TRAVA_SMART_FINANCEIRO="${TRAVA_SMART_FINANCEIRO:-/tmp/smart_cobranca.lock}"
. "$RAIZ/src/common/smart_financeiro_lock.sh"
cd "$RAIZ"
if [ "$#" -gt 1 ]; then
    echo 'uso: run_bb.sh [--simular|--pra-valer]' >&2
    exit 2
fi
MODO="${1:---simular}"
case "$MODO" in
    --simular|--pra-valer) ;;
    *) echo 'uso: run_bb.sh [--simular|--pra-valer]' >&2; exit 2 ;;
esac
if [ -f "$RAIZ/config/retorno_cobranca.env" ]; then
    set -a
    . "$RAIZ/config/retorno_cobranca.env"
    set +a
fi
export PYTHONPATH="$RAIZ"
export PYTHONUNBUFFERED=1
export HEADLESS_RET=true
export DRY_RUN_RET=True
export ACEITAR_CONTA_DESCONHECIDA_RET=False
PASTA="$RAIZ/data/retornos_a_processar/bb_api/retornos/producao/3770013/395"
set -- --pasta "$PASTA" --conta-bb-api 395 --portao --pular-processados \
    --recibos-dir "$PASTA/_RESULTADOS"
if [ "$MODO" = '--pra-valer' ]; then
    set -- "$@" --pra-valer
fi
exec python "$RAIZ/src/processors/web/retorno_cobranca/processar_retorno_cobranca.py" "$@"
