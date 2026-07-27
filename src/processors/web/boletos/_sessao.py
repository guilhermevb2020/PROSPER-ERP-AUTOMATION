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
import sys
import time
from datetime import datetime

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

from src.processors.web.boletos import _config as cfg


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


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
        print(f"[{_now()}] screenshot falhou: {e}")


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
                    "input[value='PROSSEGUIR']",
                    "a:has-text('PROSSEGUIR')",
                    "button:has-text('Prosseguir')"):
            try:
                b = fr.locator(sel)
                if b.count() > 0 and b.first.is_visible():
                    b.first.click(timeout=4_000)
                    print(f"[{_now()}] modal 'Procedimento de seguranca' -> PROSSEGUIR")
                    return True
            except Exception:
                continue
        try:
            ok = fr.evaluate("""()=>{
                const b=[...document.querySelectorAll('button,input[type=button],input[type=submit],a')]
                  .find(e=>((e.innerText||e.value||'').trim().toLowerCase())==='prosseguir');
                if(b){b.click();return true;} return false;
            }""")
            if ok:
                print(f"[{_now()}] modal 'Procedimento de seguranca' -> PROSSEGUIR (JS)")
                return True
        except Exception:
            continue
    return False


# ============================================================================ #
# Login AUTOMATICO via CapSolver
# ============================================================================ #
# Reusa CapSolverAPI ja em producao (src/common/captcha/captcha_solver.py).
# Como o solver e async e nosso codigo e sync, usamos asyncio.run.
# Site key do reCAPTCHA do login do Smart (mesma usada pelos outros
# processadores em src/processors/web/envio_boleto_*).
SITE_KEY_LOGIN_SMART = "6Le-JHwUAAAAAGZJWerkysOyQeo-Ehm7704vfT1q"


def _resolver_recaptcha_sync(site_url: str, site_key: str, timeout: int = 180) -> str | None:
    """Resolve reCAPTCHA v2 via CapSolver HTTP API (sync).

    Versao sync porque sync_playwright nao deixa rodar asyncio.run no mesmo
    contexto (event loop interno). Mesma logica do CapSolverAPI.resolver_recaptcha_v2,
    so que com `requests`:
       1) POST /createTask  -> taskId
       2) POLL /getTaskResult ate status=ready -> token (gRecaptchaResponse)

    Retorna o token g-recaptcha-response ou None se falhar.
    """
    import requests

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
        r = requests.post(create_url, json=payload, timeout=30)
        data = r.json() if r.status_code == 200 else {}
        if data.get("errorId") != 0:
            print(f"[{_now()}] CapSolver createTask falhou: {data.get('errorDescription', data)}")
            return None
        task_id = data.get("taskId")
        if not task_id:
            print(f"[{_now()}] CapSolver nao retornou taskId: {data}")
            return None
        print(f"[{_now()}] CapSolver taskId={task_id}, aguardando resolucao (max {timeout}s)")

        # 2) Poll resultado
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(2)
            try:
                rr = requests.post(poll_url, json={"clientKey": api_key, "taskId": task_id}, timeout=30)
                dd = rr.json() if rr.status_code == 200 else {}
            except Exception as exc:
                print(f"[{_now()}] CapSolver poll falhou (segue): {exc}")
                continue
            if dd.get("errorId") != 0:
                print(f"[{_now()}] CapSolver poll erro: {dd.get('errorDescription', dd)}")
                return None
            status = dd.get("status")
            if status == "ready":
                token = (dd.get("solution") or {}).get("gRecaptchaResponse")
                if token:
                    return token
                print(f"[{_now()}] CapSolver ready mas sem token: {dd}")
                return None
            # status == 'processing' -> continua
        print(f"[{_now()}] CapSolver timeout ({timeout}s) sem resposta ready")
        return None
    except Exception as exc:
        print(f"[{_now()}] CapSolver excecao: {exc}")
        return None


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

        # 1) iframe loginsec.php
        try:
            iframe = frame_com(page, cfg.SEL_LOGIN_EMAIL, timeout=30)
        except PWTimeout:
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
                print(f"[{_now()}] aviso ao clicar Entrar: {e}")
            esperar(cfg.WAIT_POS_LOGIN, "apos Entrar")
            _dispensar_seguranca(page)
        except Exception as e:
            print(f"[{_now()}] nao achei campos de login ({e}); preencha manual no VNC")
    except Exception as e:
        print(f"[{_now()}] aviso ao abrir tela de login: {e}")

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
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
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
                        print(f"[{_now()}] LOGIN PENDENTE: {e}")
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
                            print(f"[{_now()}] keepalive falhou: {e}")
                except KeyboardInterrupt:
                    print(f"\n[{_now()}] interrompido pelo usuario")
                    break
                except Exception as e:
                    print(f"[{_now()}] erro no loop: {e}")
                    break
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    print(f"[{_now()}] sessao encerrada")
