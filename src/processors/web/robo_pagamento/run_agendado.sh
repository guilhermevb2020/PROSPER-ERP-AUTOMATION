#!/bin/sh
# Wrapper do robo de REMESSA DE PAGAMENTO (BMP Money Plus) — chamado pelo hub.
#
# Garante o display :94 ISOLADO (Xvfb + x11vnc 5905 + noVNC 6085) — separado do
# :95 (retorno), :96 (credito), :97 (remessa), :98 (doc2you) e :99 (boletos) —
# carrega credenciais e roda o robo UMA vez. Idempotente: sobe so o que faltar
# (funciona apos restart do container, sem depender do boot e SEM tocar nos
# outros robos).
#
# ⭐ A TRAVA DE SOBREPOSICAO E A DIFERENCA DESTE WRAPPER PARA OS OUTROS
# ---------------------------------------------------------------------
# Este robo roda de 30 em 30 minutos — cadencia que nenhum outro robo daqui tem.
# O passo 2 abaixo mata o Chrome do proprio perfil na largada (e o que destrava
# um perfil que ficou preso num run anterior). Sem trava, uma rodada que passe de
# 30 min seria MORTA PELA SEGUINTE, possivelmente entre o "gerar" e o "baixar" —
# e a remessa ficaria orfa no Smart: gerada, nao baixada, e invisivel na proxima
# rodada porque os itens ja sairam da fila.
#
# O mesmo modo de falha ja e conhecido aqui: o `robo_retorno` tem dois wrappers
# no mesmo perfil e se defende com FOLGA DE HORARIO (`run_deposito.sh`, 10 min
# antes do agendado). Folga nao resolve para quem roda a cada 30 min: precisa de
# trava de verdade.
set -u
# RAIZ_PAG e o que torna este wrapper util nos DOIS lugares: `/app` dentro do
# container (como o hub chamaria) e a arvore do host quando quem agenda e a
# crontab do proprio `operacional2` — que nao tem docker e nao vai ter. Tudo
# abaixo pendura daqui; nenhum caminho /app sobrou solto.
RAIZ="${RAIZ_PAG:-/app}"
cd "$RAIZ" || exit 1
LOG="$RAIZ/logs/vnc"
mkdir -p "$LOG"

# --------------------------------------------------------------------------- #
# 0) TRAVA — antes de qualquer coisa, e principalmente antes do pkill
# --------------------------------------------------------------------------- #
# `exit 0` quando ja ha rodada em curso e deliberado: com cron de 30 min, marcar
# FALHA a cada sobreposicao normal encheria o hub de alarme falso, e alarme falso
# diario ensina a ignorar o alerta. Mas rodada PRESA precisa de gente — dai o
# limite de idade, que sai != 0.
#
# ⚠️ Os marcadores `>>> TRAVA` / `<<< TRAVA` NAO sao decoracao: o teste
# `tests/unit/test_pagamento_trava.py` recorta exatamente este trecho e o roda
# em `dash` e `sh`. Mexeu aqui, rode o teste — e nao apague os marcadores.
# >>> TRAVA
TRAVA="${TRAVA_PAG:-/tmp/robo_pagamento.lock}"
IDADE_ALERTA_MIN="${IDADE_ALERTA_MIN_PAG:-45}"

if [ -e "$TRAVA" ]; then
    DONO=$(cat "$TRAVA" 2>/dev/null || echo "")
    if [ -n "$DONO" ] && kill -0 "$DONO" 2>/dev/null; then
        AGORA=$(date +%s)
        NASCEU=$(stat -c %Y "$TRAVA" 2>/dev/null || echo "$AGORA")
        MIN=$(( (AGORA - NASCEU) / 60 ))
        if [ "$MIN" -ge "$IDADE_ALERTA_MIN" ]; then
            echo "TRAVADO: a rodada do pid $DONO comecou ha ${MIN} min, acima do"
            echo "         limite de ${IDADE_ALERTA_MIN}. Isso NAO e sobreposicao normal."
            echo "         Veja o log e o VNC do display :94 antes de matar nada."
            exit 6
        fi
        echo "ja ha uma rodada em curso (pid $DONO, ha ${MIN} min) — saindo sem fazer nada"
        exit 0
    fi
    echo "trava orfa (pid ${DONO:-?} nao existe mais) — removendo"
    rm -f "$TRAVA"
fi
echo $$ > "$TRAVA"
# INT/TERM tambem, senao um timeout do hub deixa a trava para tras e a proxima
# rodada so entra quando o limite de idade estourar.
trap 'rm -f "$TRAVA"' EXIT INT TERM
# <<< TRAVA

# --------------------------------------------------------------------------- #
# 1) credenciais + flags (arquivo montado, gitignored). SOBRESCREVE o SMART_EMAIL
#    do container (que e felipe_p, de outra automacao).
# --------------------------------------------------------------------------- #
if [ -f "$RAIZ/config/robo_pagamento.env" ]; then
    set -a
    . "$RAIZ/config/robo_pagamento.env"
    set +a
fi

# Headless decide se ha display a montar. No host nao existe Xvfb/x11vnc/
# websockify instalado (conferido em 25/08/2026), entao la e SEMPRE True e os
# passos 3-6 sao pulados por inteiro.
HEADLESS="${HEADLESS_PAG:-False}"

# 2) limpa chrome residual do perfil DESTE robo (nunca `pkill chrome` generico:
#    derrubaria os outros cinco). So chega aqui quem tem a trava.
PERFIL="${USER_DATA_DIR_PAG:-$RAIZ/data/robo_pagamento/perfil_chrome}"
pkill -f "user-data-dir=$PERFIL" 2>/dev/null || true
sleep 1
rm -f "$PERFIL"/Singleton* 2>/dev/null || true

if [ "$HEADLESS" = "True" ]; then
    echo "headless: sem Xvfb/x11vnc/noVNC (nao ha o que ver pelo VNC)"
else
    # 3) Xvfb :94
    if ! pgrep -f "Xvfb :94" >/dev/null 2>&1; then
        rm -f /tmp/.X94-lock /tmp/.X11-unix/X94 2>/dev/null || true
        Xvfb :94 -screen 0 1920x1080x24 -ac -nolisten tcp > "$LOG/xvfb94.log" 2>&1 &
        sleep 3
    fi

    # 4) fluxbox :94 (window manager — Chrome abre melhor com WM)
    pgrep -f "fluxbox.*:94" >/dev/null 2>&1 || (DISPLAY=:94 fluxbox > "$LOG/fluxbox94.log" 2>&1 &)

    # 5) x11vnc :94 -> 5905 (debug: ver o robo trabalhando)
    if ! pgrep -f "x11vnc.*-display :94" >/dev/null 2>&1; then
        [ -f /tmp/.vncpasswd ] && x11vnc -display :94 -rfbport 5905 -rfbauth /tmp/.vncpasswd \
            -forever -shared -bg -o "$LOG/x11vnc94.log" >/dev/null 2>&1 || true
    fi

    # 6) noVNC :94 -> 6085
    pgrep -f "websockify.*6085" >/dev/null 2>&1 || \
        (websockify --web=/usr/share/novnc/ 6085 localhost:5905 > "$LOG/novnc94.log" 2>&1 &)

    sleep 1
fi

# 7) ambiente do robo
[ "$HEADLESS" = "True" ] || export DISPLAY=:94
export PYTHONPATH="$RAIZ"                    # p/ resolver `src.processors.web.boletos...`
export PYTHONUNBUFFERED=1
export USER_DATA_DIR_PAG="$PERFIL"
mkdir -p "$PERFIL"
# DRY_RUN_PAG=True e o default do config e o certo ate o run supervisionado:
# gerar remessa de PAGAMENTO move dinheiro. Para valer, ponha DRY_RUN_PAG=false
# no robo_pagamento.env — e confira o valor EFETIVO depois de editar:
#   docker exec -e PYTHONPATH=/app erp-automation python -c \
#     "import sys; sys.path.insert(0,'/app/src/processors/web/robo_pagamento'); \
#      import pagamento_config as c; print(c.DRY_RUN)"
export DRY_RUN_PAG="${DRY_RUN_PAG:-True}"

# Pasta de saida. ⚠️ O NOME TEM ESPACOS — sempre entre aspas. `$PASTA` solto
# viraria tres argumentos e o `mkdir` criaria tres pastas erradas.
PASTA_SAIDA_PAG="${PASTA_SAIDA_PAG:-$RAIZ/temp/remessas de pagamento}"
export PASTA_SAIDA_PAG
mkdir -p "$PASTA_SAIDA_PAG"

# As outras duas pastas que o `ensure_dirs()` cria. No container elas caem no
# default `/app/...` e ninguem precisou exporta-las; no host, `/app` nao existe e
# o import de `pagamento_config` morre com PermissionError antes de qualquer log.
ARQ_CONTROLE_PAG="${ARQ_CONTROLE_PAG:-$RAIZ/data/robo_pagamento/controle_pagamentos.csv}"
DEBUG_DIR_PAG="${DEBUG_DIR_PAG:-$RAIZ/data/robo_pagamento/debug}"
export ARQ_CONTROLE_PAG DEBUG_DIR_PAG

# ⛔ A FLAG VAI AQUI, EXPLICITA, e a razao e a armadilha nº 2 do
# docs/COMO_SUBIR_UM_ROBO.md: o robo de remessa ficou com DRY_RUN no `.env` e a
# task chamando o wrapper SEM `--pra-valer`. Toda execucao saia com exit=0 e um
# resumo bonito, sem gerar nada — falha que parece sucesso.
#
# Enquanto o robo estiver em homologacao, deixe VAZIO. Para valer, troque para
#   PRA_VALER="--pra-valer"
# e confira o valor efetivo depois:
#   docker exec -e PYTHONPATH=/app erp-automation python -c \
#     "import sys; sys.path.insert(0,'/app/src/processors/web/robo_pagamento'); \
#      import pagamento_config as c; print('DRY_RUN =', c.DRY_RUN)"
PRA_VALER="${PRA_VALER_PAG:-}"

# 8) roda o robo (uma vez, e sai). `tee` grava um log AO VIVO alem do stdout
#    capturado pelo hub.
#
#    O exit code que o hub precisa ver e o do PYTHON, nao o do `tee` (que e
#    sempre 0). `PIPESTATUS` resolveria, mas e bashism e o hub chama este
#    wrapper com `sh ...`, que aqui e DASH — o shebang nao vale nesse caso.
#    Dai o arquivo de retorno, que funciona nos dois shells.
LOGROBO="$RAIZ/logs/robo_pagamento_$(date +%Y-%m-%d).log"
RC="/tmp/robo_pagamento_rc.$$"
echo "===== inicio $(date '+%F %T %Z') =====" >> "$LOGROBO"
# shellcheck disable=SC2086  # $PRA_VALER e uma flag ou vazio: nao pode ir com aspas
{ "${PYTHON_PAG:-python}" "$RAIZ/src/processors/web/robo_pagamento/robo_pagamento.py" $PRA_VALER "$@"; \
  echo $? > "$RC"; } 2>&1 | tee -a "$LOGROBO"
CODIGO=$(cat "$RC" 2>/dev/null || echo 1)
rm -f "$RC"
echo "===== fim $(date '+%F %T %Z') exit=$CODIGO =====" >> "$LOGROBO"
exit "$CODIGO"
