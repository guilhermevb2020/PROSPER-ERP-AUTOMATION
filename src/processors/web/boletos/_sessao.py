# -*- coding: utf-8 -*-
"""
Modulo de sessao do robo de boletos (TESTES no servidor).

Responsabilidades:
- Verificar se a sessao do perfil persistente esta logada (esta_logado).
- Subir o Chrome com perfil persistente em /app/data/boletos/perfil_chrome
  e CDP exposto na porta CDP_PORT (default 9222) p/ outros scripts conectarem.
- Login interativo via VNC (operador faz o reCAPTCHA na tela).
- Mensagens claras quando estiver rodando sem display.

NAO contem logica de listar/enviar boletos. Isso fica em enviar_lote.py.
"""

from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

from src.processors.web.boletos import _config as cfg


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _resumo_excecao(e: BaseException, limite: int = 160) -> str:
    """Tipo e primeira linha da mensagem, cortada. O texto INTEIRO de uma excecao do
    Playwright traz o "call log" da requisicao — cabecalhos, cookie de sessao incluido — e
    este modulo escreve em log legivel pelo grupo (22/09/2026: PHPSESSID em 8 linhas do
    manter_sessao.log). Nunca imprimir `{e}` inteiro aqui; `smart_sessao` ja segue a regra."""
    texto = (str(e) or "").strip()
    primeira = texto.splitlines()[0] if texto else ""
    primeira = re.split(r"cookie\s*:", primeira, maxsplit=1, flags=re.IGNORECASE)[0]
    return f"{type(e).__name__}: {primeira[:limite]}".rstrip(": ")


def esperar(segundos: float, motivo: str = "") -> None:
    if motivo:
        print(f"[{_now()}] wait {segundos}s | {motivo}")
    time.sleep(segundos)


def frame_com(page: Page, seletor: str, timeout: float = 30.0):
    fim = time.time() + timeout
    while time.time() < fim:
        for fr in page.frames:
            try:
                if fr.locator(seletor).count() > 0:
                    return fr
            except Exception:
                continue
        time.sleep(0.5)
    raise PWTimeout(f"Seletor '{seletor}' nao encontrado em nenhum frame.")


def fechar_pagina(page) -> None:
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def screenshot(page, nome: str) -> None:
    if not cfg.DEBUG:
        return
    try:
        os.makedirs(cfg.DEBUG_DIR, exist_ok=True)
        page.screenshot(path=os.path.join(cfg.DEBUG_DIR, nome), full_page=True)
        print(f"[{_now()}] screenshot -> {cfg.DEBUG_DIR}/{nome}")
    except Exception as e:
        print(f"[{_now()}] screenshot falhou: {_resumo_excecao(e)}")


def esta_logado(ctx) -> bool:
    """Sessao valida = pagina interna nao redireciona p/ login/empresa/expirou."""
    try:
        r = ctx.request.get(cfg.URL_SESSAO, timeout=15_000)
    except Exception:
        return False
    if r.status >= 400:
        return False
    u = (r.url or "").lower()
    if ("sessaoexpirada" in u or "loginsec" in u
            or ("smartsecurities/" in u and "/smart/" not in u)):
        return False
    try:
        html = r.body().decode("iso-8859-1", errors="replace").lower()
    except Exception:
        html = ""
    if 'id="femail"' in html or "id='femail'" in html or 'name="email"' in html:
        return False
    if "selecione a empresa" in html or "acessar empresa" in html:
        return False
    if "expira.php" in html or "expirasessao" in html:
        return False
    if ("expirou" in html or "sessao expirada" in html or "sessÃ£o expirada" in html
            or "faÃ§a login" in html or "faca login" in html):
        return False
    return True


def _dispensar_seguranca(page) -> bool:
    if page is None:
        return False
    try:
        if page.is_closed():
            return False
    except Exception:
        return False
    for fr in page.frames:
        for sel in ("button:has-text('PROSSEGUIR')",
                    "input[value='prosseguir' i]",
                    "a:has-text('PROSSEGUIR')",
                    "button:has-text('Prosseguir')"):
            try:
                b = fr.locator(sel)
                if b.count() > 0 and b.first.is_visible() and b.first.is_enabled():
                    b.first.click(timeout=4_000)
                    print(f"[{_now()}] modal 'Procedimento de seguranca' -> PROSSEGUIR")
                    return True
            except Exception:
                continue
        # O Smart desabilita Prosseguir durante a verificacao por AJAX.
        # HTMLElement.click() nesse estado nao faz nada: nao registrar sucesso
        # nem forcar o estado do botao. O proximo ciclo aguarda a resposta do site.
    return False


# ============================================================================ #
# Login AUTOMATICO via CapSolver
# ============================================================================ #
# Usa a API HTTP sincrona para nao disputar o event loop do Playwright.
# Site key do reCAPTCHA do login do Smart (mesma usada pelos outros
# processadores em src/processors/web/envio_boleto_*).
SITE_KEY_LOGIN_SMART = "6Le-JHwUAAAAAGZJWerkysOyQeo-Ehm7704vfT1q"


class _CapSolverHTTPPermanente(RuntimeError):
    pass


def _capsolver_post(url, payload, etapa, *, tentativas=3, deadline=None):
    """Tolera falhas de transporte sem esconder HTTP nem registrar credenciais."""
    import requests

    for tentativa in range(1, tentativas + 1):
        restante = 30 if deadline is None else min(30, deadline - time.monotonic())
        if restante <= 0:
            return None
        transitorio = True
        try:
            resposta = requests.post(url, json=payload, timeout=restante)
            if resposta.status_code != 200:
                motivo = f"HTTP {resposta.status_code}"
                transitorio = resposta.status_code in (408, 429) or 500 <= resposta.status_code < 600
            else:
                try:
                    dados = resposta.json()
                except ValueError:
                    dados = None
                if isinstance(dados, dict) and isinstance(dados.get("errorId"), int):
                    return dados
                motivo = "resposta JSON ausente ou invalida"
        except requests.RequestException as exc:
            motivo = type(exc).__name__
        print(f"[{_now()}] CapSolver {etapa}: {motivo} (tentativa {tentativa}/{tentativas})")
        if not transitorio:
            raise _CapSolverHTTPPermanente(motivo)
        if tentativa == tentativas:
            return None
        pausa = 2 * tentativa
        if deadline is not None:
            pausa = min(pausa, max(0, deadline - time.monotonic()))
        time.sleep(pausa)
    return None


def _capsolver_erro(dados, etapa):
    # Nao imprimir errorDescription/corpo: o fornecedor pode ecoar o clientKey.
    codigo = str(dados.get("errorCode", ""))
    codigo = codigo if re.fullmatch(r"[A-Z_]{1,80}", codigo) else "nao informado"
    print(f"[{_now()}] CapSolver {etapa}: errorId={dados['errorId']} errorCode={codigo}")


def _resolver_recaptcha_sync(site_url: str, site_key: str, timeout: int = 180) -> str | None:
    """Resolve reCAPTCHA v2 via CapSolver HTTP API (sync).

    Versao sync porque sync_playwright nao deixa rodar asyncio.run no mesmo
    contexto (event loop interno). Mesma logica do CapSolverAPI.resolver_recaptcha_v2,
    so que com `requests`:
       1) POST /createTask  -> taskId
       2) POLL /getTaskResult ate status=ready -> token (gRecaptchaResponse)

    Retorna o token g-recaptcha-response ou None se falhar.
    """
    api_key = os.getenv("CAPSOLVER_API_KEY", "").strip()
    if not api_key:
        print(f"[{_now()}] CAPSOLVER_API_KEY nao configurada — pulando solver")
        return None

    create_url = "https://api.capsolver.com/createTask"
    poll_url = "https://api.capsolver.com/getTaskResult"

    try:
        # 1) Criar task
        payload = {
            "clientKey": api_key,
            "task": {
                "type": "ReCaptchaV2TaskProxyLess",
                "websiteURL": site_url,
                "websiteKey": site_key,
            },
        }
        # Um desafio pode falhar no fornecedor sem invalidar a credencial.
        # Duas tasks no máximo compartilham o mesmo prazo, inclusive o create.
        deadline = time.monotonic() + timeout
        for desafio in range(1, 3):
            if time.monotonic() >= deadline:
                break
            data = _capsolver_post(create_url, payload, "createTask", deadline=deadline)
            if data is None:
                return None
            if data.get("errorId") != 0:
                _capsolver_erro(data, "createTask")
                return None
            task_id = data.get("taskId")
            if not task_id:
                print(f"[{_now()}] CapSolver nao retornou taskId")
                return None
            print(f"[{_now()}] CapSolver taskId={task_id}, aguardando resolucao "
                  f"(desafio {desafio}/2, prazo total {timeout}s)")

            repetir_desafio = False
            while time.monotonic() < deadline:
                time.sleep(min(2, max(0, deadline - time.monotonic())))
                dd = _capsolver_post(poll_url, {"clientKey": api_key, "taskId": task_id},
                                     "getTaskResult", tentativas=1, deadline=deadline)
                if dd is None:
                    continue
                if dd.get("errorId") != 0:
                    _capsolver_erro(dd, "getTaskResult")
                    repetir_desafio = dd.get("errorCode") == "ERROR_CAPTCHA_SOLVE_FAILED"
                    if not repetir_desafio:
                        return None
                    break
                if dd.get("status") == "ready":
                    token = (dd.get("solution") or {}).get("gRecaptchaResponse")
                    if token:
                        return token
                    print(f"[{_now()}] CapSolver ready mas sem token")
                    return None
                # status == 'processing' -> continua na mesma task.
            if not repetir_desafio:
                break
            if desafio == 2:
                print(f"[{_now()}] CapSolver falhou ao resolver os dois desafios")
                return None
            restante = deadline - time.monotonic()
            if restante <= 5:
                break
            print(f"[{_now()}] CapSolver desafio nao resolvido; nova tentativa em 5s "
                  "dentro do prazo original")
            time.sleep(5)
        print(f"[{_now()}] CapSolver timeout ({timeout}s) sem resposta ready")
        return None
    except Exception as exc:
        print(f"[{_now()}] CapSolver excecao: {type(exc).__name__}")
        return None


def _retomada_expirada(ctx) -> bool:
    """Reconhece a pagina explicita de expiracao devolvida pelo Smart."""
    for pagina in ctx.pages:
        if "smartsecurities.com.br" not in pagina.url:
            continue
        titulo = pagina.title().strip().casefold()
        if titulo in ("sessão expirada", "sessao expirada"):
            return True
    return False


def _retomar_usuario_reconhecido(page, email: str) -> bool:
    """Retoma somente a identidade esperada na tela 'Usuario logado' do Smart."""
    for frame in page.frames:
        if "loginsec.php" not in frame.url:
            continue
        campos = frame.locator('input[type="text"][disabled]')
        for i in range(campos.count()):
            campo = campos.nth(i)
            if not campo.is_visible() or campo.input_value().strip().casefold() != email.strip().casefold():
                continue
            botao = frame.locator('button[name="Entrar"]').first
            if botao.count() and botao.is_visible():
                botao.click(timeout=5_000)
                return True
    return False


def _concluir_login(ctx, page, timeout_total_s: int) -> bool:
    """Seleciona a empresa e confirma a sessao depois de autenticar ou retomar."""
    # 7) Tela de selecao de empresa — clicar ACESSAR da PROSPER VETOR
    # Procura em todos os frames; clica no primeiro 'Acessar' (PROSPER VETOR e a
    # primeira/unica para este usuario envioboletos)
    empresa_clicada = False
    for tentativa in range(3):
        for fr in page.frames:
            try:
                btn = fr.locator(cfg.SEL_ACESSAR_EMPRESA).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=5_000)
                    empresa_clicada = True
                    print(f"[{_now()}] [auto-login] ACESSAR empresa clicado")
                    break
            except Exception:
                continue
        if empresa_clicada:
            break
        esperar(2, f"aguardando tela de empresa (tent {tentativa+1}/3)")

    # 8) Aguarda esta_logado virar True (ate timeout_total)
    fim = time.time() + timeout_total_s
    while time.time() < fim:
        esperar(3)
        _dispensar_seguranca(page)
        if esta_logado(ctx):
            print(f"[{_now()}] [auto-login] >> LOGADO COM SUCESSO")
            fechar_pagina(page)
            return True

    print(f"[{_now()}] [auto-login] timeout aguardando esta_logado")
    screenshot(page, f"autologin_timeout_{int(time.time())}.png")
    return False


def login_automatico_capsolver(ctx, timeout_total_s: int = 300) -> bool:
    """Faz login no Smart automaticamente usando CapSolver (sem intervencao humana).

    Fluxo:
        1) Abre tela de login
        2) Acha iframe loginsec.php, preenche email/senha
        3) Clica OK (primeira tela) — Smart entao recarrega com reCAPTCHA
        4) Resolve reCAPTCHA via CapSolver
        5) Injeta token em g-recaptcha-response
        6) Clica OKExtra (segunda tela) — Smart vai pra selecao de empresa
        7) Clica ACESSAR na linha da PROSPER VETOR
        8) Aguarda esta_logado() retornar True

    Retorna True se conseguiu logar, False caso contrario.
    """
    if esta_logado(ctx):
        print(f"[{_now()}] sessao ja valida")
        return True

    cfg.exigir_credenciais()
    print(f"[{_now()}] [auto-login] iniciando login automatico via CapSolver")
    page = ctx.new_page()
    try:
        page.goto(cfg.URL_LOGIN, wait_until="domcontentloaded", timeout=60_000)
        esperar(3, "tela de login carregando")

        # Iframe e identidade reconhecida carregam de forma assincrona.
        # Esperar os dois estados evita perder a retomada que aparece depois
        # da primeira consulta, sem procurar #fEmail por mais 30s inutilmente.
        iframe = None
        prazo_formulario = time.monotonic() + 30
        cookie_reiniciado = False
        while time.monotonic() < prazo_formulario:
            if _retomar_usuario_reconhecido(page, cfg.EMAIL):
                print(f"[{_now()}] [auto-login] retomando usuario reconhecido pelo Smart")
                esperar(5, "retomada — aguardando selecao de empresa")
                _dispensar_seguranca(page)
                if _retomada_expirada(ctx):
                    if cookie_reiniciado:
                        print(f"[{_now()}] [auto-login] retomada continuou expirada apos reiniciar cookie")
                        return False
                    cookie_reiniciado = True
                    print(f"[{_now()}] [auto-login] cookie Smart expirado; reiniciando autenticacao deste perfil")
                    ctx.clear_cookies(domain=re.compile(r"(^|\.)smartsecurities\.com\.br$"))
                    page.goto(cfg.URL_LOGIN, wait_until="domcontentloaded", timeout=60_000)
                    prazo_formulario = time.monotonic() + 30
                    continue
                return _concluir_login(ctx, page, timeout_total_s)
            try:
                iframe = frame_com(page, cfg.SEL_LOGIN_EMAIL, timeout=1)
                break
            except PWTimeout:
                continue
        if iframe is None:
            print(f"[{_now()}] [auto-login] iframe loginsec nao encontrado")
            return False

        # 2) Preenche email/senha
        try:
            iframe.locator(cfg.SEL_LOGIN_EMAIL).first.fill(cfg.EMAIL)
            esperar(0.5)
            iframe.locator(cfg.SEL_LOGIN_SENHA).first.fill(cfg.SENHA)
        except Exception as exc:
            print(f"[{_now()}] [auto-login] falhou ao preencher credenciais: {exc}")
            return False
        print(f"[{_now()}] [auto-login] credenciais preenchidas")

        # 3) Clica OK (primeira tela)
        try:
            iframe.locator(cfg.SEL_LOGIN_ENTRAR).first.click(timeout=8_000)
        except Exception as exc:
            print(f"[{_now()}] [auto-login] falhou ao clicar #OK: {exc}")
            return False
        print(f"[{_now()}] [auto-login] OK clicado — aguardando iframe recarregar com reCAPTCHA")
        esperar(4, "iframe recarregando")

        # iframe loginsec.php recarregou com reCAPTCHA — busca POR URL
        # (importante: NAO usar o iframe da HOME que tambem tem .g-recaptcha;
        # so o loginsec.php tem o form de login real)
        iframe = None
        fim = time.time() + 30
        while time.time() < fim:
            for fr in page.frames:
                if "loginsec.php" in (fr.url or "").lower():
                    try:
                        if fr.locator(".g-recaptcha, #g-recaptcha-response").count() > 0:
                            iframe = fr
                            break
                    except Exception:
                        continue
            if iframe:
                break
            time.sleep(0.5)
        if iframe is None:
            if esta_logado(ctx):
                fechar_pagina(page)
                return True
            print(f"[{_now()}] [auto-login] iframe loginsec.php com reCAPTCHA nao apareceu")
            return False

        # 4) Resolve reCAPTCHA
        site_url = cfg.URL_LOGIN
        print(f"[{_now()}] [auto-login] chamando CapSolver (pode levar 30-90s)")
        token = _resolver_recaptcha_sync(site_url, SITE_KEY_LOGIN_SMART, timeout=180)
        if not token:
            print(f"[{_now()}] [auto-login] CapSolver nao devolveu token")
            return False
        print(f"[{_now()}] [auto-login] token recebido ({len(token)} chars)")

        # 5) Injeta token em TODOS os textareas g-recaptcha-response + aciona callbacks
        # Sem os callbacks, o reCAPTCHA do Smart NAO habilita o botao OKExtra
        # (mesmo padrao do PlaywrightCaptchaManager que ja roda em producao).
        try:
            ok = iframe.evaluate(
                """(token) => {
                    let acoes = 0;
                    // 1) Atualiza TODAS as textareas g-recaptcha-response (varias podem existir)
                    document.querySelectorAll('textarea[name="g-recaptcha-response"], textarea[id^="g-recaptcha-response"]').forEach(ta => {
                        ta.value = token;
                        ta.innerHTML = token;
                        acoes++;
                    });
                    // 2) Aciona callbacks do reCAPTCHA — chave pra o site saber que o captcha
                    //    foi resolvido (habilita o botao Acessar/OKExtra)
                    const win = document.defaultView || window;
                    document.querySelectorAll('.g-recaptcha').forEach(el => {
                        const cb = el.getAttribute('data-callback');
                        if (cb && typeof win[cb] === 'function') {
                            try { win[cb](token); acoes++; } catch (e) {}
                        }
                    });
                    return acoes;
                }""",
                token,
            )
            print(f"[{_now()}] [auto-login] token injetado + callbacks acionados ({ok} acoes)")
            if not ok:
                print(f"[{_now()}] [auto-login] nenhum textarea/callback acionado")
                return False
        except Exception as exc:
            print(f"[{_now()}] [auto-login] falhou ao injetar token: {exc}")
            return False

        # Dispensar modal "Procedimento de seguranca" se aparecer
        esperar(1)
        _dispensar_seguranca(page)

        # 6) Clica OKExtra/Acessar (segunda tela — pos-captcha)
        # Re-busca em TODOS os frames + tenta varias vezes (iframe pode ter recarregado)
        clicou_extra = False
        for tentativa in range(15):  # ate 30s
            for fr in page.frames:
                for sel in ("#OKExtra", "[name='OKExtra']", "#OK", "[name='OK']", "input[type='submit']"):
                    try:
                        btn = fr.locator(sel).first
                        if btn.count() > 0 and btn.is_visible():
                            btn.click(timeout=3_000)
                            print(f"[{_now()}] [auto-login] botao pos-captcha clicado ({sel} no frame {fr.url[:60]})")
                            clicou_extra = True
                            break
                    except Exception:
                        continue
                if clicou_extra:
                    break
            if clicou_extra:
                break
            esperar(2, f"aguardando botao pos-captcha (tent {tentativa+1}/15)")
        if not clicou_extra:
            print(f"[{_now()}] [auto-login] nao consegui clicar OKExtra")
            screenshot(page, f"autologin_sem_okextra_{int(time.time())}.png")
            return False

        esperar(5, "pos-captcha — aguardando selecao de empresa")
        _dispensar_seguranca(page)

        return _concluir_login(ctx, page, timeout_total_s)

    except Exception as exc:
        print(f"[{_now()}] [auto-login] erro inesperado: {exc}")
        screenshot(page, f"autologin_erro_{int(time.time())}.png")
        return False
    finally:
        fechar_pagina(page)


def login_interativo(ctx, espera_manual_s: int = 600) -> None:
    """Login: preenche email/senha, depois deixa o operador (via VNC) fazer
    o reCAPTCHA + escolher a empresa. Loop ate detectar sessao valida ou timeout.

    espera_manual_s: tempo total de espera do operador no VNC (default 10 min).
    """
    if esta_logado(ctx):
        print(f"[{_now()}] sessao ja valida -> nao precisa logar")
        return

    cfg.exigir_credenciais()

    if cfg.HEADLESS:
        raise RuntimeError(
            "HEADLESS=true mas a sessao nao esta logada e o login exige reCAPTCHA "
            "manual. Suba o Chrome com HEADLESS=false e DISPLAY=:99 (Xvfb + VNC) "
            "para fazer o login pela primeira vez."
        )

    page = ctx.new_page()
    try:
        page.goto(cfg.URL_LOGIN, wait_until="domcontentloaded", timeout=60_000)
        try:
            fr = frame_com(page, cfg.SEL_LOGIN_EMAIL, timeout=20)
            fr.locator(cfg.SEL_LOGIN_EMAIL).first.fill(cfg.EMAIL)
            esperar(1)
            try:
                fr.locator(cfg.SEL_LOGIN_SENHA).first.fill(cfg.SENHA)
            except Exception:
                fr.locator(cfg.SEL_LOGIN_EMAIL).first.press("Tab")
                page.keyboard.type(cfg.SENHA, delay=10)
            print(f"[{_now()}] email/senha preenchidos automaticamente")
            try:
                fr.locator(cfg.SEL_LOGIN_ENTRAR).first.click(timeout=8_000)
                print(f"[{_now()}] 'Entrar' clicado")
            except Exception as e:
                print(f"[{_now()}] aviso ao clicar Entrar: {_resumo_excecao(e)}")
            esperar(cfg.WAIT_POS_LOGIN, "apos Entrar")
            _dispensar_seguranca(page)
        except Exception as e:
            print(f"[{_now()}] nao achei campos de login ({_resumo_excecao(e)}); preencha manual no VNC")
    except Exception as e:
        print(f"[{_now()}] aviso ao abrir tela de login: {_resumo_excecao(e)}")

    print("\n" + "=" * 70)
    print("  AGUARDANDO ACAO MANUAL DO OPERADOR (VNC)")
    print("  1) Se aparecer reCAPTCHA: marque 'NAO SOU ROBO'")
    print("  2) Se aparecer 'Procedimento de seguranca': clique PROSSEGUIR")
    print(f"  3) Clique ACESSAR na empresa '{cfg.EMPRESA}'")
    print(f"  Timeout total: {espera_manual_s}s")
    print("=" * 70 + "\n")

    fim = time.time() + espera_manual_s
    while time.time() < fim:
        time.sleep(5)
        try:
            _dispensar_seguranca(page)
        except Exception:
            pass
        try:
            if esta_logado(ctx):
                restantes = int(fim - time.time())
                print(f"[{_now()}] >> LOGIN DETECTADO! sessao valida (sobrou {restantes}s)")
                fechar_pagina(page)
                return
        except Exception:
            pass

    raise RuntimeError(
        f"Login nao concluido em {espera_manual_s}s. Conclua o login pelo VNC e "
        "rode de novo. Quando estiver logado, o perfil persistente em "
        f"{cfg.USER_DATA_DIR} guarda os cookies."
    )


def _launch_persistent(p):
    """Sobe Chrome com perfil persistente + CDP exposto na porta CDP_PORT."""
    cfg.ensure_dirs()
    return p.chromium.launch_persistent_context(
        user_data_dir=cfg.USER_DATA_DIR,
        headless=cfg.HEADLESS,
        channel="chrome",
        args=[
            f"--remote-debugging-port={cfg.CDP_PORT}",
            "--start-maximized",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
        no_viewport=True,
    )


def manter_sessao_viva(intervalo_keepalive_s: int = 120) -> None:
    """Sobe a sessao + faz keepalive ate o processo ser morto.

    Quando esta_logado() volta False, NAO tenta logar de novo automaticamente:
    apenas avisa que precisa de intervencao manual via VNC. Isso evita loops
    indesejados de reCAPTCHA.
    """
    # line_buffering: o log do mantenedor e redirecionado para arquivo (boot_vnc, religar do
    # healthcheck, docker exec -d). Sem isso a saida fica em buffer de bloco e o keepalive so
    # aparece horas depois — um travamento passa despercebido (22/09/2026, log vazio por minutos).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    print(f"[{_now()}] subindo Chrome | display={cfg.DISPLAY} headless={cfg.HEADLESS}")
    print(f"[{_now()}] perfil persistente: {cfg.USER_DATA_DIR}")
    print(f"[{_now()}] CDP exposto em {cfg.CDP_URL}")

    with sync_playwright() as p:
        ctx = _launch_persistent(p)
        try:
            # 1) tenta login automatico via CapSolver primeiro
            if not esta_logado(ctx):
                print(f"[{_now()}] sessao nao valida — tentando login AUTOMATICO via CapSolver")
                if login_automatico_capsolver(ctx):
                    print(f"[{_now()}] login automatico OK")
                else:
                    print(f"[{_now()}] login automatico FALHOU — caindo para fluxo interativo (VNC)")
                    try:
                        login_interativo(ctx)
                    except RuntimeError as e:
                        print(f"[{_now()}] LOGIN PENDENTE: {_resumo_excecao(e)}")
                        print(f"[{_now()}] processo SEGUE rodando — conecte no VNC e finalize o login.")
            else:
                print(f"[{_now()}] sessao ja valida ao subir")

            print(f"[{_now()}] keepalive a cada {intervalo_keepalive_s}s. Ctrl+C para parar.")
            ultimo_ping = 0.0
            ultimo_status = None
            while True:
                time.sleep(5)
                try:
                    if not ctx.pages:
                        ctx.new_page()
                    if time.time() - ultimo_ping > intervalo_keepalive_s:
                        try:
                            r = ctx.request.get(cfg.URL_SESSAO, timeout=30_000)
                            ok = r.status < 400 and esta_logado(ctx)
                            ultimo_ping = time.time()
                            if ok != ultimo_status:
                                ultimo_status = ok
                                print(f"[{_now()}] keepalive: logado={ok} status={r.status}")
                            else:
                                print(f"[{_now()}] keepalive ok (logado={ok})")
                        except Exception as e:
                            print(f"[{_now()}] keepalive falhou: {_resumo_excecao(e)}")
                except KeyboardInterrupt:
                    print(f"\n[{_now()}] interrompido pelo usuario")
                    break
                except Exception as e:
                    print(f"[{_now()}] erro no loop: {_resumo_excecao(e)}")
                    break
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    print(f"[{_now()}] sessao encerrada")
