#!/usr/bin/env bash
# -*- coding: utf-8 -*-
# Boot do display virtual + VNC + manter_sessao do robo de boletos.
#
# Stack iniciada (todos em background):
#   1) Xvfb :99    -> display virtual 1920x1080x24
#   2) fluxbox     -> window manager leve
#   3) x11vnc      -> servidor VNC na porta 5900
#   4) noVNC       -> bridge web na porta 6080
#   5) manter_sessao -> Chrome persistente + keepalive da sessao Smart
#
# Comportamento:
# - Idempotente: cada passo so sobe se ainda nao tiver instancia rodando.
# - Limpa locks orfaos (.X99-lock, SingletonLock) ANTES de iniciar Xvfb/Chrome,
#   evitando o erro "Server is already active for display 99" que acontece
#   quando alguma instancia anterior caiu sem limpar.
# - Chrome NAO se autentica sozinho (precisa reCAPTCHA humano). O manter_sessao
#   sobe o Chrome e fica fazendo keepalive. Quando voce loga via noVNC,
#   a sessao Smart fica viva ate o proximo restart.
#
# Logs ficam em /app/logs/vnc/.

set -uo pipefail

LOG_DIR=/app/logs/vnc
mkdir -p "$LOG_DIR"

# ---------------------------------------------------------------------------
# CA do access-guardian na base NSS do Chrome.
#
# O Chrome NAO usa SSL_CERT_FILE: ele tem a propria base (NSS). Sem a CA aqui, todo
# HTTPS que passar pelo tunel do guardian daria erro de certificado — e as sete tasks
# que logam no Smart parariam. As tasks entram por `docker exec`, que NAO herda o
# ambiente deste script; a base NSS resolve isso porque e ARQUIVO, nao variavel.
#
# ⛔ Instalar o pacote inteiro aqui seria errado: o `certutil -A` pega o PRIMEIRO
# certificado do arquivo, e em 06/09/2026 isso instalou uma raiz publica espanhola no
# lugar da nossa. Por isso o worker publica `guardian-ca.crt` — so a nossa.
#
# ⚠️ O certutil deveria vir da IMAGEM (o Dockerfile ja o pede), mas em 06/09/2026 a imagem
# do erp NAO pode ser reconstruida: `playwright` esta instalado no container e NAO esta no
# requirements.txt, entao `playwright install chromium` falha com exit 127 num build limpo.
# Enquanto isso nao for consertado, instalamos aqui na partida. E lento e depende de rede;
# quando a imagem voltar a construir, esta instalacao vira no-op.
GUARDIAN_CA=/run/guardian/guardian-ca.crt
if [ -f "$GUARDIAN_CA" ] && ! command -v certutil >/dev/null 2>&1; then
    echo "[boot_vnc] certutil ausente na imagem; instalando libnss3-tools…"
    apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq libnss3-tools >/dev/null 2>&1 || true
fi
if [ -f "$GUARDIAN_CA" ] && command -v certutil >/dev/null 2>&1; then
    mkdir -p /root/.pki/nssdb
    [ -f /root/.pki/nssdb/cert9.db ] || certutil -d sql:/root/.pki/nssdb -N --empty-password >/dev/null 2>&1
    certutil -d sql:/root/.pki/nssdb -D -n guardian-local >/dev/null 2>&1
    if certutil -d sql:/root/.pki/nssdb -A -t "C,," -n guardian-local -i "$GUARDIAN_CA" 2>/dev/null; then
        echo "[boot_vnc] CA do access-guardian instalada na base NSS do Chrome"
    else
        echo "[boot_vnc] AVISO: nao consegui instalar a CA do guardian; HTTPS pelo tunel vai falhar" >&2
    fi
elif [ -f "$GUARDIAN_CA" ]; then
    echo "[boot_vnc] AVISO: certutil ausente (libnss3-tools); a CA do guardian nao foi instalada" >&2
fi

DISPLAY_NUM="${DISPLAY_NUM:-99}"
SCREEN_GEOMETRY="${SCREEN_GEOMETRY:-1920x1080x24}"
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
# Sem default no fonte: este repo tem remote publico. Vem do .env via env_file.
if [ -z "${VNC_PASSWORD:-}" ]; then
    echo "[boot_vnc] ERRO: VNC_PASSWORD nao definida. Defina em .env (fora do git)." >&2
    exit 1
fi
PERFIL_DIR="${PERFIL_DIR:-/app/data/boletos/perfil_chrome}"

export DISPLAY=":$DISPLAY_NUM"

log() { echo "[boot_vnc $(date -u +'%H:%M:%S')] $*"; }

log "iniciando stack | DISPLAY=$DISPLAY VNC=$VNC_PORT noVNC=$NOVNC_PORT"

# -------------------------------------------------------------------------- #
# Cleanup de locks orfaos (preventivo) antes de iniciar Xvfb
# -------------------------------------------------------------------------- #
if ! pgrep -f "Xvfb $DISPLAY" >/dev/null 2>&1; then
    if [ -e "/tmp/.X${DISPLAY_NUM}-lock" ]; then
        log "removendo lock orfao /tmp/.X${DISPLAY_NUM}-lock"
        rm -f "/tmp/.X${DISPLAY_NUM}-lock"
    fi
    if [ -e "/tmp/.X11-unix/X${DISPLAY_NUM}" ]; then
        rm -f "/tmp/.X11-unix/X${DISPLAY_NUM}" 2>/dev/null || true
    fi
fi

# -------------------------------------------------------------------------- #
# 1) Xvfb
# -------------------------------------------------------------------------- #
if ! pgrep -f "Xvfb $DISPLAY" >/dev/null 2>&1; then
    log "subindo Xvfb"
    Xvfb "$DISPLAY" -screen 0 "$SCREEN_GEOMETRY" -ac -nolisten tcp \
        > "$LOG_DIR/xvfb.log" 2>&1 &
    sleep 2
else
    log "Xvfb ja rodando"
fi

# -------------------------------------------------------------------------- #
# 2) fluxbox
# -------------------------------------------------------------------------- #
if ! pgrep -f "fluxbox" >/dev/null 2>&1; then
    log "subindo fluxbox"
    DISPLAY="$DISPLAY" fluxbox > "$LOG_DIR/fluxbox.log" 2>&1 &
    sleep 1
else
    log "fluxbox ja rodando"
fi

# -------------------------------------------------------------------------- #
# 3) x11vnc
# -------------------------------------------------------------------------- #
VNC_PASSWD_FILE=/tmp/.vncpasswd
x11vnc -storepasswd "$VNC_PASSWORD" "$VNC_PASSWD_FILE" >/dev/null 2>&1
chmod 600 "$VNC_PASSWD_FILE"

if ! pgrep -f "x11vnc.*-display $DISPLAY" >/dev/null 2>&1; then
    log "subindo x11vnc na porta $VNC_PORT"
    x11vnc \
        -display "$DISPLAY" \
        -rfbport "$VNC_PORT" \
        -rfbauth "$VNC_PASSWD_FILE" \
        -forever \
        -shared \
        -bg \
        -o "$LOG_DIR/x11vnc.log" \
        >/dev/null 2>&1 || true
    sleep 1
else
    log "x11vnc ja rodando"
fi

# -------------------------------------------------------------------------- #
# 4) noVNC
# -------------------------------------------------------------------------- #
if ! pgrep -f "websockify.*:$NOVNC_PORT" >/dev/null 2>&1; then
    log "subindo noVNC (websockify) na porta $NOVNC_PORT"
    websockify --web=/usr/share/novnc/ "$NOVNC_PORT" "localhost:$VNC_PORT" \
        > "$LOG_DIR/novnc.log" 2>&1 &
    sleep 1
else
    log "noVNC ja rodando"
fi

# -------------------------------------------------------------------------- #
# 5) manter_sessao do robo de boletos
# -------------------------------------------------------------------------- #
# Limpa lock do perfil Chrome se nao tiver Chrome vivo (crash sujo do ultimo run)
if ! pgrep -f "remote-debugging-port=9222" >/dev/null 2>&1; then
    # Locks do Chrome sao symlinks; -e ignora os que ficaram quebrados no recreate.
    if [ -e "$PERFIL_DIR/SingletonLock" ] || [ -L "$PERFIL_DIR/SingletonLock" ] || \
       [ -e "$PERFIL_DIR/SingletonCookie" ] || [ -L "$PERFIL_DIR/SingletonCookie" ] || \
       [ -e "$PERFIL_DIR/SingletonSocket" ] || [ -L "$PERFIL_DIR/SingletonSocket" ]; then
        log "removendo locks orfaos do perfil Chrome"
        rm -f "$PERFIL_DIR/SingletonLock" \
              "$PERFIL_DIR/SingletonCookie" \
              "$PERFIL_DIR/SingletonSocket" 2>/dev/null || true
    fi
fi

if ! pgrep -f "src.processors.web.boletos.manter_sessao" >/dev/null 2>&1; then
    log "subindo manter_sessao (Chrome + CDP 9222 + keepalive)"
    DISPLAY="$DISPLAY" python -m src.processors.web.boletos.manter_sessao \
        > "$LOG_DIR/manter_sessao.log" 2>&1 &
    sleep 3
else
    log "manter_sessao ja rodando"
fi

log "OK. noVNC: http://<host>:$NOVNC_PORT/vnc.html"
log "Para usar a sessao Smart, conecte via noVNC e faca login UMA vez."
log "mantendo container vivo..."

# Mantem PID 1 vivo. SIGTERM do `docker stop` desce limpo.
exec tail -f /dev/null
