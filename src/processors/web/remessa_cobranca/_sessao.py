# -*- coding: utf-8 -*-
"""
_sessao.py - como o robo de remessa consegue um contexto logado no Smart.

Dois modos, e o de producao e o primeiro:

  PROPRIA  (agendado)  - sobe o Chrome com perfil proprio no display :97, loga
                         via CapSolver, entrega o contexto e FECHA no fim. E o
                         mesmo desenho do doc2you: 1 login por run, nada de
                         keep-alive 24/7.
  ANEXADA  (--cdp)     - conecta num Chrome ja aberto (o que voce mesmo logou
                         pelo VNC). Serve para desenvolver e para o primeiro
                         login de um perfil novo; nunca e usado pelo agendado.

Por que o Chrome precisa de `--no-sandbox --disable-dev-shm-usage`: dentro do
container o processo roda como root e o sandbox do Chrome nao sobe; sem
`disable-dev-shm-usage` ele estoura o /dev/shm e morre no meio da navegacao.
Os dois ja sao padrao nos outros robos deste container.
"""
import contextlib
import os

import login as autenticacao
import remessa_config as cfg

# Resposta a alert/confirm. ATENCAO (pegadinha que custou tempo no Windows): com
# o Playwright anexado e SEM handler de 'dialog', ele DESCARTA o dialogo sozinho
# -> confirm() devolve False. A tela "Gerar Remessa" termina em
#   confirm("Foram selecionados N titulos ... Confirma a geracao do arquivo?")
# e o clique morria em silencio. O robo de hoje gera por HTTP e nao depende
# disso, mas o handler fica armado para quem abrir a tela pelo VNC.
#   DIALOGOS=aceitar -> OK (comportamento de navegador normal)
#   DIALOGOS=recusar -> Cancelar (seguro: nao gera arquivo)
DIALOGOS = os.environ.get("DIALOGOS", "aceitar").strip().lower()


class SemNavegador(RuntimeError):
    """Nao foi possivel abrir nem anexar um Chrome."""


class SemSessao(RuntimeError):
    """Abriu o Chrome, mas nao ficou logado no Smart."""


def _tratar_dialogo(d):
    """Mostra o texto do dialogo no log (senao ele some) e responde."""
    print(f"  [DIALOGO {d.type}] {d.message}", flush=True)
    try:
        if DIALOGOS.startswith("recus"):
            d.dismiss()
        else:
            d.accept()
    except Exception as e:
        print(f"  [DIALOGO] falha ao responder: {e}", flush=True)


def _armar_dialogos(pg):
    with contextlib.suppress(Exception):
        pg.on("dialog", _tratar_dialogo)


def abrir_propria(p, log=print):
    """Sobe o Chrome do robo (perfil e porta CDP proprios). Retorna o contexto.

    Perfil PROPRIO nao e preciosismo: dois Chromes no mesmo `user-data-dir`
    disputam o lock e um deles nao sobe. Idem para a porta CDP (9222=boletos,
    9223=doc2you, 9224=remessa).
    """
    cfg.ensure_dirs()
    # O Chrome herda o DISPLAY do processo. O container define DISPLAY=:99
    # (boletos) para todo mundo, entao publicamos o NOSSO antes de subir —
    # senao um `docker exec` sem `-e DISPLAY` poe este Chrome em cima do dos
    # boletos, e dois Chromes no mesmo display fazem o login quicar.
    os.environ["DISPLAY"] = cfg.DISPLAY
    # Medido em 31/07/2026: sem o Xvfb do display no ar o Chrome AINDA SOBE e o
    # Playwright devolve um contexto — a falha nao aparece aqui, aparece torta
    # la na frente. Quem sobe o Xvfb :97 e o run_agendado.sh; num teste manual
    # avulso ninguem sobe, entao avisamos em vez de deixar o robo mudo.
    if not cfg.HEADLESS:
        soquete = f"/tmp/.X11-unix/X{cfg.DISPLAY.lstrip(':')}"
        if not os.path.exists(soquete):
            log(f"  AVISO: o display {cfg.DISPLAY} nao esta no ar ({soquete} nao "
                "existe). Rode pelo run_agendado.sh, que sobe o Xvfb, ou use "
                "HEADLESS_REM=true.")
    log(f"  subindo Chrome | display={cfg.DISPLAY} perfil={cfg.USER_DATA_DIR}")
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=cfg.USER_DATA_DIR,
        headless=cfg.HEADLESS,
        channel="chrome",
        accept_downloads=True,
        downloads_path=cfg.PASTA_REMESSAS,
        args=[
            f"--remote-debugging-port={cfg.CDP_PORT}",
            "--start-maximized",
            "--no-sandbox",              # roda como root no container
            "--disable-dev-shm-usage",   # /dev/shm pequeno mata o Chrome
        ],
        no_viewport=True,
    )
    ctx.on("page", _armar_dialogos)
    for pg in ctx.pages:
        _armar_dialogos(pg)
    return ctx


def anexar(p, log=print):
    """Conecta num Chrome ja aberto (modo desenvolvimento). None se nao houver."""
    try:
        browser = p.chromium.connect_over_cdp(cfg.CDP_URL)
    except Exception as e:
        log(f"  ERRO: nao conectei no CDP {cfg.CDP_URL}: {e}")
        return None
    if not browser.contexts:
        log("  ERRO: CDP conectado mas sem janela aberta.")
        return None
    ctx = browser.contexts[0]
    for pg in ctx.pages:
        _armar_dialogos(pg)
    return ctx


@contextlib.contextmanager
def sessao(p, usar_cdp=False, logar=True, espera_manual=0, log=print):
    """Contexto logado, do jeito certo para cada modo.

    Fecha o Chrome ao sair APENAS quando foi este modulo que o abriu — nunca
    fecha a janela que voce deixou aberta no VNC.

    Levanta SemNavegador/SemSessao se nao conseguir: o agendado precisa MORRER
    com erro, e nao seguir e reportar "nenhuma conta com remessa".
    """
    proprio = not usar_cdp
    ctx = abrir_propria(p, log) if proprio else anexar(p, log)
    if ctx is None:
        raise SemNavegador("nao consegui um contexto de navegador")
    try:
        if logar and not autenticacao.login(ctx, log=log):
            manual_ok = espera_manual > 0 and autenticacao.aguardar_login_manual(
                ctx, espera_manual, log=log)
            if not manual_ok:
                raise SemSessao(
                    "sessao do Smart nao esta logada (auto-login falhou). "
                    "Veja o motivo no log; se for reCAPTCHA/janela de horario, "
                    f"acompanhe pelo VNC do display {cfg.DISPLAY}.")
        yield ctx
    finally:
        if proprio:
            with contextlib.suppress(Exception):
                ctx.close()
            log("  Chrome fechado.")
