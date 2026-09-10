#!/bin/sh
# Retornos BB reconstruídos: conta exata, portão e recibos duráveis.
set -eu
RAIZ="${RAIZ_BB_RETORNO:-/app}"
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
if [ -f "$RAIZ/config/robo_retorno.env" ]; then
    set -a
    . "$RAIZ/config/robo_retorno.env"
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
exec python "$RAIZ/src/processors/web/robo_retorno/robo_retorno.py" "$@"
