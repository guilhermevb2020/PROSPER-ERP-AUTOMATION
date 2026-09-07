# -*- coding: utf-8 -*-
"""
smart_sessao.py - sessao do Smart para robos self-contained (COMPARTILHADO).

Um robo "self-contained" sobe o proprio Chrome num display isolado, loga via
CapSolver, faz o trabalho por HTTP e FECHA. E o desenho do doc2you e do
robo_remessa — nada de keep-alive 24/7.

O que este modulo resolve, e que todo robo do Smart precisa:

  parece_deslogado()  a deteccao do `expira.php`, que e a armadilha nº 1 aqui
  esta_logado()       ping autenticado contra a tela QUE O ROBO PRECISA
  login()             delega para o fluxo CapSolver ja em producao (boletos)
  abrir_chrome()      launch com perfil/porta/display proprios e os 2 args do container
  sessao()            context manager: entrega ctx logado e fecha no fim

NAO reimplementa o login. `boletos._sessao.login_automatico_capsolver` ja resolve
o iframe `loginsec.php`, o acionamento dos `data-callback` do reCAPTCHA e a
selecao de empresa. Como aquele modulo le credencial e ping de `boletos._config`
— que resolve tudo NO IMPORT — as envs do robo chamador sao publicadas ANTES, e
por isso o import e preguicoso (dentro da funcao).

Uso:
    from src.common.clients import smart_sessao

    with smart_sessao.sessao(p, cfg, log=log) as ctx:
        ...   # ctx.request.get/post autenticados

`cfg` e o modulo de config do robo. Precisa expor:
    EMAIL, SENHA, URL_PING, URL_LOGIN, USER_DATA_DIR, CDP_PORT, CDP_URL,
    DISPLAY, HEADLESS  e  ensure_dirs()
"""
import contextlib
import os
import time


class SemNavegador(RuntimeError):
    """Nao foi possivel abrir nem anexar um Chrome."""


class SemSessao(RuntimeError):
    """Abriu o Chrome, mas nao ficou logado no Smart."""


class SmartIndisponivel(RuntimeError):
    """Nao foi possivel confirmar a sessao; nao implica credencial recusada."""


def parece_deslogado(html) -> bool:
    """True se a resposta do Smart e, na verdade, 'voce nao esta logado'.

    ARMADILHA Nº 1 DESTE ERP: quando a sessao expira, o Smart responde
    **HTTP 200** com um corpo de 93 bytes:

        <script>top.location.href='.../smart/php/expira.php';</script>

    Sem 'recaptcha', sem status de erro, e sem a palavra 'expirou' — e
    "expira", sem o U. Quem nao checa isso ve TODA tela como vazia e conclui
    "nao ha nada a fazer": a rodada termina com cara de sucesso sem ter olhado
    nada. Chame isto em TODO ponto que le resposta do Smart.

    Resposta vazia tambem conta como deslogado — melhor abortar do que tratar
    como "sem trabalho".
    """
    if not html:
        return True
    baixo = html.lower()
    return ("expira.php" in baixo
            or "recaptcha" in baixo
            or "loginsec" in baixo
            or "sessão expirou" in baixo or "sessao expirou" in baixo
            or "faça login" in baixo or "faca login" in baixo)


def esta_logado(ctx, cfg) -> bool:
    """Ping HTTP autenticado (nao abre aba nem navega).

    `cfg.URL_PING` deve apontar para a tela QUE O ROBO PRECISA. Assim "logado"
    significa "alcanca a tela", e um usuario sem permissao falha aqui, cedo e
    com mensagem clara, em vez de virar "nada a fazer" la na frente.
    """
    try:
        r = ctx.request.get(cfg.URL_PING, timeout=20_000)
        corpo = r.body().decode("iso-8859-1", errors="replace")
    except Exception:
        return False
    if r.status != 200:
        return False
    return not parece_deslogado(corpo)


def sessao_viva(ctx, cfg, tentativas: int = 3, timeout_ms: int = 45_000, log=print):
    """Estado da sessao com RETRY. Retorna 'ok' | 'deslogado' | None.

    TIMEOUT NAO E DESLOGADO — e a distincao que evita o falso alarme mais comum
    aqui: o Smart fica lento logo depois de processar algo pesado, o ping de 20s
    estoura e o robo anuncia "sessao nao esta logada" com a sessao perfeita.
    So declara deslogado quando A RESPOSTA diz isso; None = consulta inconclusiva
    (timeout, falha de transporte, HTTP diferente de 200 ou resposta vazia).
    """
    ultimo = None
    for tentativa in range(1, tentativas + 1):
        try:
            r = ctx.request.get(cfg.URL_PING, timeout=timeout_ms)
            corpo = r.body().decode("iso-8859-1", errors="replace")
        except Exception as e:
            # O detalhe da excecao pode conter cabecalhos/cookies da requisicao.
            ultimo = type(e).__name__
        else:
            if r.status != 200:
                ultimo = f"HTTP {r.status}"
            elif not corpo.strip():
                ultimo = "resposta vazia"
            else:
                return "deslogado" if parece_deslogado(corpo) else "ok"
        log(f"  (ping da sessao inconclusivo, tentativa {tentativa}/{tentativas}: "
            f"{ultimo})")
        if tentativa < tentativas:
            time.sleep(3)
    log(f"  ultimo erro do ping: {ultimo}")
    return None


def login(ctx, cfg, timeout_total_s: int = 300, log=print) -> bool:
    """Garante sessao logada; consulta inconclusiva levanta SmartIndisponivel.

    Nao confundir transporte com autenticacao: um timeout nao justifica novo
    login (que pode invalidar outra sessao da conta), nem invalida o login feito.
    """
    estado = sessao_viva(ctx, cfg, log=log)
    if estado == "ok":
        log("  sessao ja valida -> sem novo login")
        return True
    if estado is None:
        raise SmartIndisponivel(
            "nao consegui confirmar a sessao do Smart apos as tentativas de ping; "
            "login nao foi iniciado. Veja o diagnostico do ping acima.")

    faltando = [n for n, v in (("EMAIL", cfg.EMAIL), ("SENHA", cfg.SENHA))
                if not (v or "").strip()]
    if faltando:
        log(f"  [login] ERRO: credencial ausente ({', '.join(faltando)}) — "
            "defina no arquivo .env do robo, em /app/config/")
        return False

    # `boletos._config` resolve credencial/ping NO IMPORT, e o load_dotenv dele
    # NAO sobrescreve env ja definida -> publicar antes, importar depois.
    os.environ["BOLETO_EMAIL"] = cfg.EMAIL
    os.environ["BOLETO_SENHA"] = cfg.SENHA
    os.environ["URL_SESSAO"] = cfg.URL_PING
    os.environ.setdefault("URL_LOGIN", cfg.URL_LOGIN)

    try:
        from src.processors.web.boletos._sessao import login_automatico_capsolver
        log(f"  sessao nao valida -> auto-login via CapSolver ({cfg.EMAIL})")
        ok = login_automatico_capsolver(ctx, timeout_total_s=timeout_total_s)
    except RuntimeError as e:
        log(f"  [login] ERRO: {e}")
        return False

    # Em 07/09 o login confirmou sucesso, mas o ping seguinte falhou 20s depois
    # e virou exit=2 (esta_logado() ocultava a causa). Repetir so a leitura.
    if ok:
        estado = sessao_viva(ctx, cfg, log=log)
        if estado == "ok":
            log("  login OK")
            return True
        if estado is None:
            raise SmartIndisponivel(
                "auto-login concluiu, mas a tela do Smart nao pode ser validada "
                "apos as tentativas de ping; isto nao confirma sessao expirada.")
        log("  [login] o auto-login disse OK mas a tela do robo respondeu "
            "sessao expirada/login (usuario sem acesso? janela de horario do Smart?)")
    else:
        log("  [login] auto-login FALHOU")
    return False


def abrir_chrome(p, cfg, log=print):
    """Sobe o Chrome do robo: perfil, porta CDP e display PROPRIOS."""
    cfg.ensure_dirs()
    # O Chrome herda o DISPLAY do processo, e o compose define DISPLAY=:99
    # (boletos) para todo mundo. Publicar o nosso evita que um `docker exec` sem
    # `-e` suba este Chrome em cima do dos boletos — 2 Chromes no mesmo display
    # fazem o login quicar de volta para a landing.
    os.environ["DISPLAY"] = cfg.DISPLAY
    if not cfg.HEADLESS:
        soquete = f"/tmp/.X11-unix/X{cfg.DISPLAY.lstrip(':')}"
        if not os.path.exists(soquete):
            log(f"  AVISO: display {cfg.DISPLAY} nao esta no ar ({soquete} nao "
                "existe). Rode pelo run_agendado.sh, que sobe o Xvfb.")
    # O canal 'chrome' e o Google Chrome de verdade, em /opt/google/chrome —
    # existe no container e NAO existe no host (instala-lo pede root, que o
    # `operacional2` nao tem). Com SMART_CHROME_CANAL="" cai no Chromium que o
    # Playwright baixou na venv, que e o que o `scripts/sandbox/_ambiente.py` ja
    # fazia. O default segue "chrome": nada muda para quem roda no container.
    canal = os.getenv("SMART_CHROME_CANAL", "chrome")
    log(f"  subindo Chrome | display={cfg.DISPLAY} perfil={cfg.USER_DATA_DIR}"
        f" canal={canal or 'chromium (bundled)'}")
    kwargs = dict(
        user_data_dir=cfg.USER_DATA_DIR,
        headless=cfg.HEADLESS,
        args=[
            f"--remote-debugging-port={cfg.CDP_PORT}",
            "--start-maximized",
            "--no-sandbox",              # roda como root no container
            "--disable-dev-shm-usage",   # /dev/shm pequeno mata o Chrome
        ],
        no_viewport=True,
    )
    if canal:
        kwargs["channel"] = canal
    return p.chromium.launch_persistent_context(**kwargs)


def anexar(p, cfg, log=print):
    """Conecta num Chrome ja aberto (modo desenvolvimento/VNC). None se nao houver."""
    try:
        browser = p.chromium.connect_over_cdp(cfg.CDP_URL)
    except Exception as e:
        log(f"  ERRO: nao conectei no CDP {cfg.CDP_URL}: {e}")
        return None
    if not browser.contexts:
        log("  ERRO: CDP conectado mas sem janela aberta.")
        return None
    return browser.contexts[0]


@contextlib.contextmanager
def sessao(p, cfg, usar_cdp: bool = False, logar: bool = True, log=print):
    """Contexto logado. Fecha o Chrome APENAS quando foi este modulo que o abriu.

    Levanta SemNavegador/SemSessao/SmartIndisponivel: o robo agendado precisa
    MORRER com erro, e nao seguir reportando "nada a fazer".
    """
    proprio = not usar_cdp
    ctx = abrir_chrome(p, cfg, log) if proprio else anexar(p, cfg, log)
    if ctx is None:
        raise SemNavegador("nao consegui um contexto de navegador")
    try:
        if logar and not login(ctx, cfg, log=log):
            raise SemSessao(
                "sessao do Smart nao esta logada (auto-login falhou). Veja o "
                f"motivo no log; acompanhe pelo VNC do display {cfg.DISPLAY}.")
        yield ctx
    finally:
        if proprio:
            with contextlib.suppress(Exception):
                ctx.close()
            log("  Chrome fechado.")
