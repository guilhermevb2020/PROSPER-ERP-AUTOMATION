#!/bin/sh
# Sourced pelos dois wrappers ANTES de tocar no Chrome. A conta financeira
# permite uma unica sessao, mesmo com perfis e displays diferentes.
if [ "${1:-}" = "--sessao-financeira-serializada" ]; then
    shift
    echo "[sessao financeira] exclusividade adquirida"
else
    echo "[sessao financeira] aguardando exclusividade (limite 300s)"
    # --close impede Xvfb/Chrome/noVNC de herdarem o descritor: a trava pertence
    # ao supervisor flock e termina com o wrapper, sem arquivo PID orfao.
    # Nao apagar este arquivo: trocar seu inode quebraria a exclusao mutua.
    exec flock --close --wait 300 --conflict-exit-code 6 \
        "${TRAVA_SMART_FINANCEIRO:-/tmp/smart_financeiro.lock}" \
        sh "$0" --sessao-financeira-serializada "$@"
fi
