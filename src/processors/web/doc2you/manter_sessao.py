# -*- coding: utf-8 -*-
"""Mantém viva a sessão do Doc2You num perfil persistente próprio (Raphaelas).

100% separado dos boletos:
  - perfil próprio:  data/doc2you/perfil_chrome   (NÃO o dos boletos)
  - CDP próprio:     porta 9223                    (NÃO a 9222 dos boletos)
  - display próprio: :98                            (NÃO o :99 dos boletos)

Fluxo ao subir:
  1) abre a tela de login e preenche login/senha (Raphaelas);
  2) tenta login AUTOMÁTICO via CapSolver (mesma lógica provada dos boletos:
     resolve o reCAPTCHA, injeta token + ACIONA os data-callbacks, clica Acessar,
     dispensa "Procedimento de segurança", escolhe a empresa);
  3) se o auto-login falhar, deixa o form pronto pro operador finalizar pelo VNC;
  4) keepalive idle — o job de download conecta via CDP 9223 e reusa a sessão.

Rodar destacado (sobrevive ao terminal):
  docker exec -d -e DISPLAY=:98 -w /app erp-automation \
    python -m src.processors.web.doc2you.manter_sessao
"""
import os
import time

from playwright.sync_api import sync_playwright

from src.processors.web.boletos._sessao import _resolver_recaptcha_sync, SITE_KEY_LOGIN_SMART

PERFIL = os.getenv("DOC2YOU_PERFIL", "/app/data/doc2you/perfil_chrome")
CDP_PORT = int(os.getenv("DOC2YOU_CDP_PORT", "9223"))
URL_LOGIN = os.getenv("URL_LOGIN", "https://www.smartsecurities.com.br/smartsecurities/")
SMART_PANEIS = (
    "https://wvw.smartsecurities.com.br/smart/smartsecurities.php",
    "https://www.smartsecurities.com.br/smart/smartsecurities.php",
)
NEGATIVOS = (
    'id="femail"', "id='femail'", 'name="email"', "selecione a empresa", "acessar empresa",
    "expira.php", "expirasessao", "sessaoexpirada", "sessao expirada", "expirou",
    "faca login", "top.location.href",
)


def _now():
    return time.strftime("%H:%M:%S")


def _credenciais():
    login, senha = os.getenv("DOC2YOU_LOGIN"), os.getenv("DOC2YOU_SENHA")
    if login and senha:
        return login, senha
    try:
        from src.common.core.config_loader import get_config_loader
        cred = get_config_loader().get_credentials("baixar_documentos_doc2you")
        if cred:
            return cred.usuario, cred.senha
    except Exception as e:
        print(f"[doc2you] aviso credentials.csv: {e}", flush=True)
    return login, senha


def _logado_smart(ctx) -> bool:
    """Logado no Smart? Via ctx.request — trata redirect JS p/ expira.php."""
    for url in SMART_PANEIS:
        try:
            r = ctx.request.get(url, timeout=20_000)
        except Exception:
            continue
        if r.status >= 400:
            continue
        u = (r.url or "").lower()
        if "loginsec" in u or "expira" in u or ("smartsecurities/" in u and "/smart/" not in u):
            continue
        try:
            t = r.text().lower()
        except Exception:
            t = ""
        if any(s in t for s in NEGATIVOS):
            continue
        return True
    return False


def _frame_login(page, timeout=25.0):
    fim = time.time() + timeout
    while time.time() < fim:
        for fr in page.frames:
            try:
                if fr.locator("#fEmail, [name='fEmail']").count() > 0:
                    return fr
            except Exception:
                continue
        time.sleep(0.5)
    return None


def _frame_recaptcha(page, timeout=30.0):
    """iframe loginsec.php que recarregou COM o reCAPTCHA (após o Entrar)."""
    fim = time.time() + timeout
    while time.time() < fim:
        for fr in page.frames:
            if "loginsec.php" in (fr.url or "").lower():
                try:
                    if fr.locator(".g-recaptcha, #g-recaptcha-response").count() > 0:
                        return fr
                except Exception:
                    continue
        time.sleep(0.5)
    return None


def _dispensar_seguranca(page):
    for fr in page.frames:
        try:
            ok = fr.evaluate(
                "()=>{const b=[...document.querySelectorAll('button,input[type=button],"
                "input[type=submit],a')].find(e=>((e.innerText||e.value||'').trim()"
                ".toLowerCase())==='prosseguir'); if(b){b.click();return true;} return false;}")
            if ok:
                print(f"[doc2you] modal segurança → PROSSEGUIR", flush=True)
                return True
        except Exception:
            continue
    return False


def login_automatico(ctx, page, login, senha, timeout_total=240) -> bool:
    """Auto-login via CapSolver (espelha boletos/_sessao.login_automatico_capsolver)."""
    fr = _frame_login(page)
    if not fr:
        print("[doc2you] iframe de login não encontrado", flush=True)
        return False
    try:
        fr.locator("#fEmail, [name='fEmail']").first.fill(login)
        time.sleep(0.5)
        fr.locator("#fPassword, [name='fPassword']").first.fill(senha)
        print(f"[doc2you] login/senha preenchidos ({login})", flush=True)
        fr.locator("#OK, [name='OK']").first.click(timeout=8_000)
        print("[doc2you] 'Entrar' clicado — aguardando reCAPTCHA...", flush=True)
    except Exception as e:
        print(f"[doc2you] falha ao preencher/clicar Entrar: {e}", flush=True)
        return False

    time.sleep(4)
    fr = _frame_recaptcha(page)
    if not fr:
        if _logado_smart(ctx):
            return True
        print("[doc2you] reCAPTCHA não apareceu após Entrar", flush=True)
        return False

    print(f"[doc2you] chamando CapSolver (30-90s)...", flush=True)
    token = _resolver_recaptcha_sync(URL_LOGIN, SITE_KEY_LOGIN_SMART, timeout=180)
    if not token:
        print("[doc2you] CapSolver não devolveu token", flush=True)
        return False
    print(f"[doc2you] token recebido ({len(token)} chars) — injetando + callbacks", flush=True)

    # injeta token em TODAS as textareas + ACIONA data-callbacks (habilita o Acessar)
    for f in page.frames:
        try:
            f.evaluate(
                "(token)=>{let n=0;"
                "document.querySelectorAll('textarea[name=\"g-recaptcha-response\"],"
                "textarea[id^=\"g-recaptcha-response\"]').forEach(ta=>{ta.value=token;ta.innerHTML=token;n++;});"
                "const win=document.defaultView||window;"
                "document.querySelectorAll('.g-recaptcha').forEach(el=>{const cb=el.getAttribute('data-callback');"
                "if(cb&&typeof win[cb]==='function'){try{win[cb](token);n++;}catch(e){}}});return n;}", token)
        except Exception:
            continue

    time.sleep(1)
    _dispensar_seguranca(page)

    # clica Acessar/OKExtra (todos os frames, retry)
    clicou = False
    for _ in range(15):
        for f in page.frames:
            for sel in ("#OKExtra", "[name='OKExtra']", "#OK", "[name='OK']", "input[type='submit']"):
                try:
                    b = f.locator(sel).first
                    if b.count() > 0 and b.is_visible():
                        b.click(timeout=3_000)
                        clicou = True
                        break
                except Exception:
                    continue
            if clicou:
                break
        if clicou:
            break
        time.sleep(2)
    print(f"[doc2you] Acessar pós-captcha: {'clicado' if clicou else 'NÃO achei'}", flush=True)

    # seleção de empresa
    time.sleep(5)
    _dispensar_seguranca(page)
    for _ in range(3):
        sel_emp = False
        for f in page.frames:
            try:
                b = f.locator("a:has-text('Acessar'), button:has-text('Acessar'), input[value='Acessar']").first
                if b.count() > 0 and b.is_visible():
                    b.click(timeout=5_000)
                    sel_emp = True
                    print("[doc2you] ACESSAR empresa clicado", flush=True)
                    break
            except Exception:
                continue
        if sel_emp:
            break
        time.sleep(2)

    # aguarda logar
    fim = time.time() + timeout_total
    while time.time() < fim:
        time.sleep(3)
        _dispensar_seguranca(page)
        if _logado_smart(ctx):
            return True
    return False


def main():
    os.makedirs(PERFIL, exist_ok=True)
    login, senha = _credenciais()
    print(f"[doc2you] subindo Chrome | perfil={PERFIL} | CDP={CDP_PORT} | display={os.getenv('DISPLAY')}", flush=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PERFIL, headless=False, channel="chrome",
            args=[f"--remote-debugging-port={CDP_PORT}", "--start-maximized",
                  "--no-sandbox", "--disable-dev-shm-usage"],
            no_viewport=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        if _logado_smart(ctx):
            print("[doc2you] sessão já válida — reusando.", flush=True)
        else:
            try:
                page.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=60_000)
            except Exception as e:
                print(f"[doc2you] aviso ao abrir login: {e}", flush=True)
            time.sleep(3)
            if login and senha:
                try:
                    ok = login_automatico(ctx, page, login, senha)
                except Exception as e:
                    print(f"[doc2you] erro no auto-login: {e}", flush=True)
                    ok = False
                if ok:
                    print("[doc2you] >> LOGADO AUTOMATICAMENTE (CapSolver). Sessão pronta.", flush=True)
                else:
                    print("[doc2you] auto-login FALHOU — form pré-preenchido; finalize o reCAPTCHA + empresa pelo VNC.", flush=True)
                    fr = _frame_login(page)
                    if fr:
                        try:
                            fr.locator("#fEmail, [name='fEmail']").first.fill(login)
                            fr.locator("#fPassword, [name='fPassword']").first.fill(senha)
                        except Exception:
                            pass
            else:
                print("[doc2you] sem credencial — preencha manual no VNC.", flush=True)

        print(f"[doc2you] CDP em 127.0.0.1:{CDP_PORT}. keepalive: ping 120s + relogin se cair.", flush=True)
        ultimo_ping = 0.0
        ultimo_status = None
        while True:
            time.sleep(15)
            try:
                _ = ctx.pages
            except Exception as e:
                print(f"[doc2you] browser encerrado ({e}) — saindo.", flush=True)
                break
            if time.time() - ultimo_ping < 120:
                continue
            ultimo_ping = time.time()
            try:
                if _logado_smart(ctx):
                    if ultimo_status is not True:
                        print("[doc2you] keepalive: logado=True", flush=True)
                    ultimo_status = True
                    continue
                # sessão caiu — re-logar via CapSolver
                ultimo_status = False
                print("[doc2you] keepalive: sessão caiu — re-logando via CapSolver...", flush=True)
                if not (login and senha):
                    continue
                try:
                    if page.is_closed():
                        page = ctx.new_page()
                    page.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=60_000)
                    time.sleep(2)
                except Exception:
                    page = ctx.new_page()
                if login_automatico(ctx, page, login, senha):
                    print("[doc2you] keepalive: re-login OK", flush=True)
                    ultimo_status = True
                else:
                    print("[doc2you] keepalive: re-login FALHOU", flush=True)
            except Exception as e:
                print(f"[doc2you] keepalive erro: {e}", flush=True)


if __name__ == "__main__":
    main()
