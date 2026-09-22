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
. /app/src/common/smart_financeiro_lock.sh
cd /app || exit 1
LOG=/app/logs/vnc
mkdir -p "$LOG"

# 1) credenciais + flags (arquivo montado, gitignored). SOBRESCREVE o SMART_EMAIL
#    do container (que e felipe_p, de outra automacao).
if [ -f /app/config/retorno_cobranca.env ]; then
    set -a
    . /app/config/retorno_cobranca.env
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
# retorno_cobranca.env — e confira o valor efetivo depois de editar o arquivo.
export DRY_RUN_RET="${DRY_RUN_RET:-True}"

# 7b) ⭐ ONDE ESTA O RETORNO BANCARIO DE VERDADE
#
# ⛔ Ate 26/08/2026 esta task rodava SEM `--pasta` e caia no default
# `/app/data/retornos_a_processar`, onde o unico conteudo eram 13 `.RET` que o
# `gerar_retorno_erp` deixou em 18/08 e que ja estavam processados. Resultado
# medido: 0 processados e `exit=6` em toda rodada, enquanto o retorno bancario
# real esperava em `cnab_nextcloud/Retornos`, que o robo nunca alcancava. Em
# 26/08 eram 60 titulos, R$ 155.957,53, casados pela conciliacao e ainda abertos.
#
# ⚠️ Quem fazia o trabalho era UMA PESSOA, a mao, dia a dia: os logs de 21 e
# 25/08 trazem `--pasta .../<dia>/MoneyPlus` repetido, andando para tras. Esta
# etapa automatiza exatamente isso — as MESMAS pastas, com os MESMOS nomes.
#
# ⛔ MESMA PASTA E REQUISITO, NAO CONVENIENCIA. O robo so pula um arquivo quando
# o Smart diz "ja processado" (comparando o NOME saneado por `nome_limpo`) **E**
# o hash esta no controle — as duas condicoes, no `if` do `pular_se_processado`.
# Copiar o `.RET` para outra pasta com outro nome quebraria a metade do NOME, o
# Smart o veria como novo, e o mesmo pagamento entraria DUAS vezes.
#
# ⭐ So entra pasta com arquivo GENUINAMENTE NOVO. Sem esse filtro a rodada
# revisita dias inteiros ja processados, paga ~1,5 s por arquivo pulado e ainda
# termina em `exit=6` — porque "ja processado" entra em `com_erro` no somatorio
# do robo e vira pendencia.
#
# ⚠️ O hash e do conteudo com as quebras NORMALIZADAS: o robo abre o arquivo em
# modo texto, entao `\r\n` vira `\n` antes do md5. O md5 do arquivo cru nao casa
# com nada — conferido em 26/08/2026 contra o proprio controle.
ARVORE_RET="${ARVORE_RETORNO_RET:-/app/data/cnab_nextcloud/Retornos}"
DIAS_RET="${DIAS_RETORNO_RET:-3}"
ENTRADA_RET="${PASTA_ENTRADA_RET:-/app/data/retornos_a_processar}"
CONTROLE_RET="${ARQ_CONTROLE_RET:-/app/data/robo_retorno/controle_processados.csv}"

# ⚠️ `--pasta` do chamador MANDA. Quem roda a mao apontando uma pasta especifica
# nao pode ser sequestrado pela descoberta automatica.
TEM_PASTA=0
for _a in "$@"; do
    case "$_a" in --pasta|--pasta=*) TEM_PASTA=1 ;; esac
done

PASTAS_RET="/tmp/robo_retorno_pastas.$$"
: > "$PASTAS_RET"
if [ "$TEM_PASTA" -eq 0 ]; then
    # ⚠️ `-maxdepth`/`-mtime` limitam a varredura; sem eles seriam 534 arquivos.
    # A entrada classica entra junto: quem largar um `.RET` la continua atendido.
    # O BB entrega .ret e o MoneyPlus .RET. Preserve os nomes: o Smart os usa
    # no controle de processamento. A descoberta aceita ambas as extensoes.
    { find "$ARVORE_RET" -type f -iname '*.ret' -mtime -"$DIAS_RET" 2>/dev/null
      find "$ENTRADA_RET" -maxdepth 1 -type f -iname '*.ret' 2>/dev/null
    } | while IFS= read -r _f; do
        [ -n "$_f" ] || continue
        _h=$(tr -d '\r' < "$_f" | md5sum | cut -d' ' -f1)
        grep -qa "$_h" "$CONTROLE_RET" 2>/dev/null || dirname "$_f"
    done | sort -u > "$PASTAS_RET"
fi

# 8) roda o robo — uma vez por pasta com novidade — e sai. `tee` grava um log AO
#    VIVO alem do stdout capturado pelo hub.
#
#    O exit code que o hub precisa ver e o do PYTHON, nao o do `tee` (que e
#    sempre 0). `PIPESTATUS` resolveria, mas e bashism e o hub chama este
#    wrapper com `sh ...`, que aqui e DASH — o shebang nao vale nesse caso.
#    Dai o arquivo de retorno, que funciona nos dois shells.
LOGROBO="/app/logs/robo_retorno_$(date +%Y-%m-%d).log"
RC="/tmp/robo_retorno_rc.$$"
PIOR="/tmp/robo_retorno_pior.$$"
echo 0 > "$PIOR"

rodar() {   # $1 = pasta ou vazio; demais argumentos vao depois
    _p="$1"; shift
    echo "===== inicio $(date '+%F %T %Z') ${_p:+pasta=$_p} =====" >> "$LOGROBO"
    # ⚠️ `--pasta` vai ANTES de "$@": se o chamador tambem passou um, o dele
    # vence no argparse, que fica com o ultimo.
    if [ -n "$_p" ]; then
        { python /app/src/processors/web/retorno_cobranca/processar_retorno_cobranca.py \
              --pasta "$_p" "$@"; echo $? > "$RC"; } 2>&1 | tee -a "$LOGROBO"
    else
        { python /app/src/processors/web/retorno_cobranca/processar_retorno_cobranca.py \
              "$@"; echo $? > "$RC"; } 2>&1 | tee -a "$LOGROBO"
    fi
    _c=$(cat "$RC" 2>/dev/null || echo 1)
    echo "===== fim $(date '+%F %T %Z') exit=$_c =====" >> "$LOGROBO"
    [ "$_c" -gt "$(cat "$PIOR")" ] && echo "$_c" > "$PIOR"
    return 0
}

if [ "$TEM_PASTA" -eq 1 ] || [ ! -s "$PASTAS_RET" ]; then
    if [ "$TEM_PASTA" -eq 0 ]; then
        # ⭐ Nada novo NAO e falha. Antes disto a task terminava em `exit=6` todo
        # dia por reler arquivo velho, e aviso que sempre falha se aprende a ignorar.
        echo "nenhum retorno bancario novo em $ARVORE_RET (janela de $DIAS_RET dias)" \
            | tee -a "$LOGROBO"
        rm -f "$RC" "$PIOR" "$PASTAS_RET"
        exit 0
    fi
    rodar "" "$@"
else
    while IFS= read -r _pasta; do
        [ -n "$_pasta" ] || continue
        rodar "$_pasta" "$@"
    done < "$PASTAS_RET"
fi

CODIGO=$(cat "$PIOR" 2>/dev/null || echo 1)
rm -f "$RC" "$PIOR" "$PASTAS_RET"
exit "$CODIGO"
