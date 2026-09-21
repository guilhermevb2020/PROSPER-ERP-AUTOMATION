# -*- coding: utf-8 -*-
"""Auto-login no Smart (Doc2You) via CapSolver — versão ASYNC.

Porta async da lógica provada em boletos/_sessao + manter_sessao: preenche
Raphaelas, clica Entrar, resolve o reCAPTCHA (CapSolver), injeta token + ACIONA os
data-callbacks (senão o Smart não habilita "Acessar"), dispensa "Procedimento de
segurança" e escolhe a empresa. Deve rodar num display ISOLADO (:98) — nunca junto
dos boletos no :99 (2 Chromes no mesmo display = bounce).
"""
import asyncio
import time

from src.processors.web.boletos._sessao import _resolver_recaptcha_sync, SITE_KEY_LOGIN_SMART

URL_LOGIN = "https://www.smartsecurities.com.br/smartsecurities/"
SMART_PANEIS = (
    "https://wvw.smartsecurities.com.br/smart/smartsecurities.php",
    "https://www.smartsecurities.com.br/smart/smartsecurities.php",
)
NEGATIVOS = (
    'id="femail"', "id='femail'", 'name="email"', "selecione a empresa", "acessar empresa",
    "expira.php", "expirasessao", "sessaoexpirada", "sessao expirada", "expirou",
    "faca login", "top.location.href",
)


async def logado(ctx) -> bool:
    """Logado no Smart? Via ctx.request — trata o redirect JS p/ expira.php."""
    for url in SMART_PANEIS:
        try:
            r = await ctx.request.get(url, timeout=20000)
        except Exception:
            continue
        if r.status >= 400:
            continue
        u = (r.url or "").lower()
        if "loginsec" in u or "expira" in u or ("smartsecurities/" in u and "/smart/" not in u):
            continue
        try:
            t = (await r.text()).lower()
        except Exception:
            t = ""
        if any(s in t for s in NEGATIVOS):
            continue
        return True
    return False


async def _frame_login(page, timeout=25.0):
    fim = time.time() + timeout
    while time.time() < fim:
        for fr in page.frames:
            try:
                if await fr.locator("#fEmail, [name='fEmail']").count() > 0:
                    return fr
            except Exception:
                continue
        await asyncio.sleep(0.5)
    return None


async def _frame_recaptcha(page, timeout=30.0):
    fim = time.time() + timeout
    while time.time() < fim:
        for fr in page.frames:
            if "loginsec.php" in (fr.url or "").lower():
                try:
                    if await fr.locator(".g-recaptcha, #g-recaptcha-response").count() > 0:
                        return fr
                except Exception:
                    continue
        await asyncio.sleep(0.5)
    return None


async def _dispensar_seguranca(page):
    for fr in page.frames:
        try:
            ok = await fr.evaluate(
                "()=>{const b=[...document.querySelectorAll('button,input[type=button],"
                "input[type=submit],a')].find(e=>((e.innerText||e.value||'').trim()"
                ".toLowerCase())==='prosseguir'); if(b){b.click();return true;} return false;}")
            if ok:
                return True
        except Exception:
            continue
    return False


async def _motivo_recusa(respostas, log) -> None:
    """Loga o MOTIVO real da recusa, lido da resposta do `dologin.php` do Smart.

    Ex.: `2|Usuário com acesso restrito.` = o usuário está FORA da janela de horário
    de acesso configurada no cadastro dele no Smart (não é captcha nem senha). Sem
    isso, toda falha vira um genérico "auto-login falhou" e o diagnóstico fica cego.
    """
    for r in reversed(respostas):
        try:
            t = ((await r.text()) or "").strip()
        except Exception:
            continue
        if t:
            log(f"[doc2you] Smart recusou o login -> {t[:200]!r}")
            return


async def login(ctx, page, usuario, senha, timeout_total=240, log=print) -> bool:
    if await logado(ctx):
        log("[doc2you] sessão já válida")
        return True
    # Escuta PASSIVA das respostas do dologin.php (não altera o fluxo): se o login
    # falhar, mostramos o motivo que o Smart devolveu.
    respostas = []

    def _cap(r):
        if "dologin" in ((r.url or "").lower()):
            respostas.append(r)

    page.on("response", _cap)
    try:
        ok = await _login_fluxo(ctx, page, usuario, senha, timeout_total, log)
        if not ok:
            await _motivo_recusa(respostas, log)
        return ok
    finally:
        try:
            page.remove_listener("response", _cap)
        except Exception:
            pass


async def _login_fluxo(ctx, page, usuario, senha, timeout_total=240, log=print) -> bool:
    await page.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(3)

    fr = await _frame_login(page)
    if not fr:
        log("[doc2you] iframe de login não encontrado")
        return False
    await fr.locator("#fEmail, [name='fEmail']").first.fill(usuario)
    await asyncio.sleep(0.5)
    await fr.locator("#fPassword, [name='fPassword']").first.fill(senha)
    log(f"[doc2you] login/senha preenchidos ({usuario})")
    await fr.locator("#OK, [name='OK']").first.click(timeout=8000)
    log("[doc2you] 'Entrar' clicado — aguardando reCAPTCHA")
    await asyncio.sleep(4)

    fr = await _frame_recaptcha(page)
    if not fr:
        return await logado(ctx)

    log("[doc2you] chamando CapSolver (30-90s)...")
    token = await asyncio.to_thread(_resolver_recaptcha_sync, URL_LOGIN, SITE_KEY_LOGIN_SMART, 180)
    if not token:
        log("[doc2you] CapSolver não devolveu token")
        return False
    log(f"[doc2you] token ({len(token)} chars) — injetando + callbacks")

    for f in page.frames:
        try:
            await f.evaluate(
                "(token)=>{let n=0;"
                "document.querySelectorAll('textarea[name=\"g-recaptcha-response\"],"
                "textarea[id^=\"g-recaptcha-response\"]').forEach(ta=>{ta.value=token;ta.innerHTML=token;n++;});"
                "const win=document.defaultView||window;"
                "document.querySelectorAll('.g-recaptcha').forEach(el=>{const cb=el.getAttribute('data-callback');"
                "if(cb&&typeof win[cb]==='function'){try{win[cb](token);n++;}catch(e){}}});return n;}", token)
        except Exception:
            continue

    await asyncio.sleep(1)
    await _dispensar_seguranca(page)

    clicou = False
    for _ in range(15):
        for f in page.frames:
            for sel in ("#OKExtra", "[name='OKExtra']", "#OK", "[name='OK']", "input[type='submit']"):
                try:
                    b = f.locator(sel).first
                    if await b.count() > 0 and await b.is_visible():
                        await b.click(timeout=3000)
                        clicou = True
                        break
                except Exception:
                    continue
            if clicou:
                break
        if clicou:
            break
        await asyncio.sleep(2)
    log(f"[doc2you] Acessar pós-captcha: {'clicado' if clicou else 'NÃO achei'}")

    await asyncio.sleep(5)
    await _dispensar_seguranca(page)
    for _ in range(3):
        emp = False
        for f in page.frames:
            try:
                b = f.locator("a:has-text('Acessar'), button:has-text('Acessar'), input[value='Acessar']").first
                if await b.count() > 0 and await b.is_visible():
                    await b.click(timeout=5000)
                    emp = True
                    break
            except Exception:
                continue
        if emp:
            break
        await asyncio.sleep(2)

    fim = time.time() + timeout_total
    while time.time() < fim:
        await asyncio.sleep(3)
        await _dispensar_seguranca(page)
        if await logado(ctx):
            return True
    return False
