#!/bin/sh
# Geração BB pelo processador existente. Sem argumento, consulta a fila.
# A trava também protege o perfil usado pela remessa MoneyPlus.
set -eu
RAIZ="${RAIZ_BB_REMESSA:-/app}"
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

# Mesma entrega de identidade do robô de remessa, via Guardian.
if [ -f "$RAIZ/config/remessa_cobranca.env" ]; then
    set -a
    . "$RAIZ/config/remessa_cobranca.env"
    set +a
fi
CARTEIRA="${BB_REMESSA_CARTEIRA:-17}"
case "$CARTEIRA" in
    11|17|18) ;;
    *) echo 'carteira BB deve ser 11, 17 ou 18' >&2; exit 2 ;;
esac

export PYTHONPATH="$RAIZ"
export PYTHONUNBUFFERED=1
export HEADLESS_REM=true
# O modo BB só gera com a flag explícita, mesmo se o env legado disser false.
export DRY_RUN_REM=True
exec python "$RAIZ/src/processors/web/remessa_cobranca/gerar_remessa_cobranca.py" \
    --gerar --conta 395 --carteira "$CARTEIRA" \
    --bb-api-convenio 3770013 --bb-api-ambiente producao \
    --bb-api-origem "$RAIZ/data/retornos_a_processar/bb_api/origens" "$MODO"
