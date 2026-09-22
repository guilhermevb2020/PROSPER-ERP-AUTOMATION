# -*- coding: utf-8 -*-
"""
Healthcheck periodico da sessao Smart do robo de boletos.

Executado pelo hub-orchestration a cada 15 min. Detecta 3 estados:

  1) CHROME_DOWN  - CDP 9222 nao responde. Auto-religa o manter_sessao.
  2) NEEDS_LOGIN  - Chrome OK mas sessao nao esta logada. Notifica humano
                    via WhatsApp/email (uma vez por incidente).
  3) HEALTHY      - Chrome OK + sessao valida. Tudo bem, so loga e sai.

Registros em operacional.boleto_envio_log_healthcheck (tabela leve, criada
pela mesma migration). Auto-deduplica notificacoes: so manda nova quando
o estado muda (ex: era HEALTHY e virou NEEDS_LOGIN).

Variaveis de ambiente uteis:
  NOTIFY_EMAIL=guilherme@prospereinvest.com.br   (alvo de notificacao)
  NOTIFY_WHATSAPP=5511940414747                  (numero internacional)
  NOTIFY_INSTANCIA=GERENCIAL                     (instancia Evolution)
  AUTO_RELIGAR=true                              (se religa Chrome sozinho)
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg2

# Container roda em UTC; janela operacional do robo e em horario BRT.
TZ_OP = ZoneInfo("America/Sao_Paulo")


def _agora_brt() -> datetime:
    return datetime.now(TZ_OP)

from src.processors.web.boletos import _db


CDP_URL = "http://127.0.0.1:9222"
DISPLAY = os.environ.get("DISPLAY", ":99")

# Notificacao
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "guilherme@prospereinvest.com.br")
NOTIFY_WHATSAPP = os.environ.get("NOTIFY_WHATSAPP", "5511963226389")
NOTIFY_INSTANCIA = os.environ.get("NOTIFY_INSTANCIA", "Prosperito")
AUTO_RELIGAR = os.environ.get("AUTO_RELIGAR", "true").strip().lower() in ("1", "true", "sim")

# Janela de auto-relogin (Smart so e usado das 8h-12h; reabrir sessao fora
# disso e desperdicio de CapSolver). Inclusivo no inicio, exclusivo no fim.
# Default: 9h-12h (cron de envio e 10h; 1h de buffer caso CapSolver falhe).
AUTO_RELOGIN_HORA_INICIO = int(os.environ.get("AUTO_RELOGIN_HORA_INICIO", "9"))
AUTO_RELOGIN_HORA_FIM = int(os.environ.get("AUTO_RELOGIN_HORA_FIM", "12"))


def _dentro_janela_relogin() -> bool:
    """True se a hora atual (BRT) esta na janela em que o robo realmente sera usado."""
    h = _agora_brt().hour
    return AUTO_RELOGIN_HORA_INICIO <= h < AUTO_RELOGIN_HORA_FIM


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str) -> None:
    print(f"[{_now_iso()}] {msg}", flush=True)


# ----------------------------------------------------------------------------- #
# Chrome/CDP probe
# ----------------------------------------------------------------------------- #
# Teto do handshake CDP. Sem teto explicito o Playwright segura ~180s; duas
# conexoes travadas (sessao_logada + relogin) passam dos 240s de timeout da
# task no hub, e ela morre antes de registrar diagnostico ou chegar no
# CapSolver. Ver incidente 26-27/07/2026 em docs/BOLETOS_LOTE.md.
CDP_TIMEOUT_MS = 20_000


def chrome_ok() -> bool:
    """True se o CDP aceita conexao de verdade — WebSocket, nao so HTTP.

    O endpoint HTTP `/json/version` e servido por uma thread propria e segue
    respondendo 200 com o browser ja travado: em 26/07/2026 respondeu por 16h
    enquanto nenhum job conseguia conectar. Quem os jobs usam e o WebSocket
    (`connect_over_cdp`), entao e ele que precisa ser testado — senao o
    travamento vira `needs_login` e o `religar_chrome()`, que resolveria em um
    tick, nunca dispara.
    """
    import urllib.request
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=3) as r:
            if r.status != 200:
                return False
    except Exception:
        return False

    # HTTP respondeu. Agora o que de fato importa: o handshake do WebSocket.
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            b = p.chromium.connect_over_cdp(CDP_URL, timeout=CDP_TIMEOUT_MS)
            if not b.contexts:
                # Browser vivo mas sem contexto: `contexts[0]` estoura IndexError
                # nos entrypoints (emitir_lote sai com exit 2). Tratar como down
                # para que o religar_chrome() reconstrua o perfil.
                _log("CDP conectou mas o browser nao tem contexto — tratando como down")
                return False
            return True
    except Exception as e:
        _log(f"CDP HTTP ok mas WebSocket falhou ({type(e).__name__}) — browser travado")
        return False


def sessao_logada() -> bool:
    """True se Chrome esta logado no Smart (esta_logado=True)."""
    from playwright.sync_api import sync_playwright
    from src.processors.web.boletos._sessao import esta_logado
    try:
        with sync_playwright() as p:
            b = p.chromium.connect_over_cdp(CDP_URL, timeout=CDP_TIMEOUT_MS)
            return esta_logado(b.contexts[0])
    except Exception as e:
        _log(f"erro ao testar esta_logado: {e}")
        return False


def robo_smart_ativo() -> str | None:
    """Evita relogin da identidade compartilhada enquanto outro robo a usa."""
    for nome, padrao in (
        ("envio de boletos", r"src[.]processors[.]web[.]boletos[.]enviar_lote"),
        ("emissao de boletos", r"src[.]processors[.]web[.]boletos[.]emitir_lote"),
        ("Doc2You", r"src[.]processors[.]web[.]doc2you[.]baixar_dia"),
        ("remessa de cobranca", r"/remessa_cobranca/gerar_remessa_cobranca[.]py"),
        ("retorno de cobranca/deposito", r"/retorno_cobranca/processar_retorno_cobranca[.]py"),
    ):
        resultado = subprocess.run(["pgrep", "-f", padrao], capture_output=True, timeout=3)
        if resultado.returncode == 0:
            return nome
        if resultado.returncode != 1:
            raise RuntimeError("nao foi possivel conferir processos Smart ativos")
    return None


# ----------------------------------------------------------------------------- #
# Religar Chrome (auto-recovery)
# ----------------------------------------------------------------------------- #
def religar_chrome() -> bool:
    """Sobe manter_sessao em background. Retorna True se PID iniciou."""
    _log("religando Chrome via manter_sessao")
    try:
        # mata zumbis antes
        subprocess.run(["pkill", "-9", "-f", "manter_sessao"], check=False)
        subprocess.run(["pkill", "-9", "-f", "remote-debugging-port=9222"], check=False)
        # limpa locks do perfil
        for f in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            try:
                os.remove(f"/app/data/boletos/perfil_chrome/{f}")
            except FileNotFoundError:
                pass
        # sobe novo manter_sessao em background
        env = {**os.environ, "DISPLAY": DISPLAY}
        log_path = "/app/logs/vnc/manter_sessao.log"
        with open(log_path, "ab") as lf:
            p = subprocess.Popen(
                ["python", "-m", "src.processors.web.boletos.manter_sessao"],
                stdout=lf, stderr=lf, env=env, start_new_session=True,
            )
        _log(f"manter_sessao subindo (PID {p.pid})")
        return True
    except Exception as e:
        _log(f"falha ao religar: {e}")
        return False


# ----------------------------------------------------------------------------- #
# Histórico de estado (para deduplicar notificações)
# Tabela criada pela migration 080 (process-automation/database/).
# ----------------------------------------------------------------------------- #
def estado_anterior(conn) -> str | None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT estado FROM operacional.boleto_sessao_healthcheck
            ORDER BY quando DESC LIMIT 1
        """)
        row = cur.fetchone()
        return row[0] if row else None


def registrar(conn, *, chrome_ok_: bool, logado: bool, estado: str, acao: str, detalhe: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO erp_automation.boleto_sessao_healthcheck
                (chrome_ok, logado, estado, acao, detalhe)
            VALUES (%s, %s, %s, %s, %s)
        """, (chrome_ok_, logado, estado, acao, detalhe))


# ----------------------------------------------------------------------------- #
# Notificacao para humano (whatsapp/email) quando precisa relogin
# ----------------------------------------------------------------------------- #
def notificar_humano(motivo: str) -> bool:
    """Envia WhatsApp pra avisar que precisa relogar. Retorna True se enviou."""
    enviado = False
    msg = (
        f"⚠️ Robô de boletos precisa de login manual no Smart.\n\n"
        f"Motivo: {motivo}\n"
        f"Acesse https://vnc.prospereinvest.com.br/vnc.html (login do Authelia; "
        f"a credencial do VNC e administrada pelo Access Guardian) e refaça o login.\n\n"
        f"Enquanto não logar, o envio diário das 10h não vai rodar."
    )

    # tentar WhatsApp
    try:
        url = os.environ.get("EVOLUTION_API_URL", "http://evolution-api:8080")
        key = os.environ.get("EVOLUTION_API_KEY", "")
        instancia_tag = NOTIFY_INSTANCIA.upper().replace(" ", "_").replace("-", "_")
        instancia_nome = os.environ.get(f"EVOLUTION_INST_{instancia_tag}_NAME", NOTIFY_INSTANCIA)
        import urllib.request, json as _json
        body = _json.dumps({"number": NOTIFY_WHATSAPP, "text": msg}).encode()
        req = urllib.request.Request(
            f"{url}/message/sendText/{instancia_nome}",
            data=body,
            headers={"content-type": "application/json", "apikey": key},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            if r.status in (200, 201):
                _log(f"WhatsApp enviado para {NOTIFY_WHATSAPP} via {instancia_nome}")
                enviado = True
            else:
                _log(f"WhatsApp HTTP {r.status}")
    except Exception as e:
        _log(f"falha WhatsApp: {e}")

    return enviado


# ----------------------------------------------------------------------------- #
# Loop principal (1 execucao)
# ----------------------------------------------------------------------------- #
def main():
    conn = _db.get_conn()
    anterior = estado_anterior(conn)

    ok_chrome = chrome_ok()
    ativo = robo_smart_ativo()
    if ativo:
        # A sessao e unica por identidade mesmo em perfis Chrome diferentes.
        # Nao afirmar que esta logada: esta verificacao foi adiada.
        registrar(conn, chrome_ok_=ok_chrome, logado=False, estado="busy",
                  acao="verificacao_adiada",
                  detalhe=f"{ativo} em andamento; sessao nao aferida, recuperacao adiada")
        _log(f"estado=busy ({ativo}; sem relogin ou reinicio de Chrome)")
        conn.close()
        return
    if not ok_chrome:
        # CHROME_DOWN — auto-religa
        estado = "chrome_down"
        if AUTO_RELIGAR:
            religar_chrome()
            acao = "religou_chrome"
            detalhe = "CDP 9222 nao respondia; manter_sessao reiniciado"
        else:
            acao = "nenhuma"
            detalhe = "CDP 9222 down; auto-religar desativado"
        # Se mudou de estado, notifica
        if anterior != estado:
            notificar_humano("Chrome do robo caiu. Religando, mas precisa logar via VNC depois.")
            acao = acao + "+notificou"
        registrar(conn, chrome_ok_=False, logado=False, estado=estado, acao=acao, detalhe=detalhe)
        _log(f"estado={estado} acao={acao}")
        conn.close()
        return

    logado = sessao_logada()
    if not logado:
        # Sessao caiu. Antes de tentar religar, verifica se estamos na janela em
        # que o robo realmente sera usado. Fora da janela, NAO consome CapSolver.
        if not _dentro_janela_relogin():
            agora_brt = _agora_brt()
            estado = "needs_login_fora_janela"
            detalhe = (
                f"esta_logado=False; fora da janela operacional BRT "
                f"({AUTO_RELOGIN_HORA_INICIO}h-{AUTO_RELOGIN_HORA_FIM}h). "
                f"Auto-relogin somente dentro da janela para economizar CapSolver."
            )
            registrar(conn, chrome_ok_=True, logado=False, estado=estado, acao="nenhuma", detalhe=detalhe)
            _log(f"estado={estado} (h_brt={agora_brt.hour})")
            conn.close()
            return

        # Dentro da janela — tenta auto-relogin
        _log(f"sessao down (dentro da janela {AUTO_RELOGIN_HORA_INICIO}-{AUTO_RELOGIN_HORA_FIM}h) — tentando login automatico")
        autologin_ok = False
        try:
            from playwright.sync_api import sync_playwright
            from src.processors.web.boletos._sessao import login_automatico_capsolver
            with sync_playwright() as p:
                b = p.chromium.connect_over_cdp(CDP_URL, timeout=CDP_TIMEOUT_MS)
                autologin_ok = login_automatico_capsolver(b.contexts[0])
        except Exception as exc:
            _log(f"erro no login_automatico: {exc}")

        if autologin_ok:
            estado = "auto_relogado"
            acao = "auto_relogou"
            detalhe = "esta_logado=False -> CapSolver resolveu reCAPTCHA -> sessao reativada"
            registrar(conn, chrome_ok_=True, logado=True, estado=estado, acao=acao, detalhe=detalhe)
            _log(f"estado={estado} acao={acao}")
            conn.close()
            return

        # Login automatico falhou DENTRO da janela — situacao critica, pede humano
        estado = "needs_login"
        acao = "nenhuma"
        detalhe = "Chrome vivo, CapSolver falhou dentro da janela operacional; precisa de humano (reCAPTCHA via VNC)"
        if anterior != estado:
            notificar_humano(
                f"Sessao do Smart expirou e CapSolver falhou ({datetime.now().strftime('%H:%M')}). "
                "Cron das 10h em risco — logar via VNC."
            )
            acao = "notificou"
        registrar(conn, chrome_ok_=True, logado=False, estado=estado, acao=acao, detalhe=detalhe)
        _log(f"estado={estado} acao={acao}")
        conn.close()
        return

    # tudo ok
    estado = "healthy"
    registrar(conn, chrome_ok_=True, logado=True, estado=estado, acao="nenhuma", detalhe=None)
    _log(f"estado=healthy")
    conn.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
