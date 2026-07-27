# -*- coding: utf-8 -*-
"""Login MANUAL (via VNC) em perfil persistente + download de validação.

Mesmo padrão do robô original e dos boletos: o operador loga UMA vez no Smart pela
tela do VNC (resolve o reCAPTCHA e escolhe a empresa). O perfil persistente guarda
os cookies; o robô reusa a sessão — sem CapSolver e sem o problema de bounce do
auto-login.

IMPORTANTE: a aba de login NÃO é navegada durante a espera (o operador dirige essa
aba). A detecção de "logado" é feita por requisição em background (ctx.request),
sem mexer na tela — igual ao esta_logado() dos boletos.

Uso (no container, com DISPLAY=:99):
  python -m src.processors.web.doc2you.login_manual --data 2026-06-19 --limite 5
"""
import argparse
import asyncio
import os
import time
from pathlib import Path

from playwright.async_api import async_playwright

from src.processors.web.doc2you import classificar as C
from src.processors.web.doc2you import download as D

URL_LOGIN = "https://www.smartsecurities.com.br/smartsecurities/"
DOC2YOU_URL = os.getenv("DOC2YOU_URL", "https://www.smartsecurities.com.br/smart/doc2you.php")
PERFIL = os.getenv("DOC2YOU_PERFIL", "/app/data/doc2you/perfil_chrome")
OUT_DIR = Path(os.getenv("DOC2YOU_OUT_DIR", "data/doc2you"))
MIN_PDF_BYTES = 1024

# URLs internas do Smart p/ checar login SEM navegar a aba do operador
SMART_PANEIS = (
    "https://wvw.smartsecurities.com.br/smart/smartsecurities.php",
    "https://www.smartsecurities.com.br/smart/smartsecurities.php",
)


async def smart_logado(ctx) -> bool:
    """Logado no Smart (empresa já escolhida)? Via ctx.request — não navega a tela.
    Espelha o esta_logado() provado dos boletos: trata o redirect JS p/ expira.php
    (sessão expirada) que ANTES dava falso-positivo."""
    NEGATIVOS = (
        'id="femail"', "id='femail'", 'name="email"',
        "selecione a empresa", "acessar empresa",
        "expira.php", "expirasessao", "sessaoexpirada", "sessao expirada",
        "expirou", "faca login", "top.location.href",
    )
    for url in SMART_PANEIS:
        try:
            r = await ctx.request.get(url, timeout=20000)
        except Exception:
            continue
        if r.status >= 400:
            continue
        u = (r.url or "").lower()
        if "loginsec" in u or "expira" in u or ("smartsecurities/" in u and "/smart/" not in u):
            continue  # redirecionou p/ login/expirou
        try:
            txt = (await r.text()).lower()
        except Exception:
            txt = ""
        if any(s in txt for s in NEGATIVOS):
            continue  # tela de login / escolher empresa / sessão expirada
        return True
    return False


async def doc2you_ok(ctx, page_aux) -> bool:
    """SSO Doc2You + valida acesso. page_aux é uma aba auxiliar (não a do login)."""
    try:
        await page_aux.goto(DOC2YOU_URL, wait_until="domcontentloaded", timeout=40000)
    except Exception:
        pass
    await asyncio.sleep(2.5)
    return await D.sessao_valida(ctx)


async def baixar_e_salvar(ctx, docs, data_iso, limite):
    base = OUT_DIR / data_iso
    salvos, erros = 0, 0
    alvo = docs[:limite] if limite else docs
    for i, d in enumerate(alvo, 1):
        tipo = d["tipo"]
        try:
            pdf = await D.baixar_documento(ctx, d["chk"], data_iso, data_iso)
            if not pdf or len(pdf) < MIN_PDF_BYTES:
                print(f"   [{i}/{len(alvo)}] {tipo} op{d.get('operacao')}: PDF vazio", flush=True)
                erros += 1
                continue
            cnpj = D.resolver_cnpj(d, pdf)
            nome = C.nome_final(tipo, d.get("operacao", ""), d.get("nota", ""), cnpj)
            subpasta = C.PASTA_TIPO.get(tipo, "Outros")
            destino = base / subpasta
            destino.mkdir(parents=True, exist_ok=True)
            (destino / f"{nome}.pdf").write_bytes(pdf)
            salvos += 1
            print(f"   [{i}/{len(alvo)}] OK {subpasta}/{nome}.pdf ({len(pdf)} bytes)", flush=True)
        except Exception as e:
            erros += 1
            print(f"   [{i}/{len(alvo)}] {tipo} op{d.get('operacao')}: ERRO {type(e).__name__}: {e}", flush=True)
    return salvos, erros


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="2026-06-19", help="YYYY-MM-DD")
    ap.add_argument("--limite", type=int, default=5, help="máx. de docs (0 = todos)")
    ap.add_argument("--espera", type=int, default=720, help="segundos aguardando login manual")
    args = ap.parse_args()

    Path(PERFIL).mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=PERFIL, headless=False, channel="chrome",
            args=["--no-sandbox", "--disable-dev-shm-usage", "--start-maximized"],
            no_viewport=True)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        page_aux = await ctx.new_page()  # aba auxiliar p/ SSO/checagens (não é a do login)

        # Perfil já logado (reuso)?
        if await smart_logado(ctx) and await doc2you_ok(ctx, page_aux):
            print(">>> Sessão do perfil já válida (Doc2You acessível) — reusando.", flush=True)
        else:
            await page.goto(URL_LOGIN, wait_until="domcontentloaded", timeout=60000)
            print("=" * 70, flush=True)
            print(">>> ABRA O VNC: https://vnc.prospereinvest.com.br/vnc.html "
                  "(senha VNC: ver VNC_PASSWORD no .env do servidor)", flush=True)
            print(">>> LOGUE no Smart na aba de login: reCAPTCHA + escolha a empresa.", flush=True)
            print(">>> (NÃO vou mexer na sua tela — detecto o login em background)", flush=True)
            print(f">>> Aguardando até {args.espera}s...", flush=True)
            print("=" * 70, flush=True)

            fim = time.time() + args.espera
            logado = False
            while time.time() < fim:
                await asyncio.sleep(10)
                if await smart_logado(ctx):
                    print(">>> Login no Smart DETECTADO! Conferindo acesso ao Doc2You...", flush=True)
                    if await doc2you_ok(ctx, page_aux):
                        logado = True
                        break
                    print(">>> Logado no Smart, mas o Doc2You ainda não respondeu — re-tentando...", flush=True)
                else:
                    print(f"   ... aguardando login (faltam {int(fim - time.time())}s)", flush=True)
            if not logado:
                if await smart_logado(ctx):
                    print(">>> Você logou no Smart, mas essa conta NÃO tem acesso ao Doc2You.", flush=True)
                else:
                    print(">>> TIMEOUT: não detectei login no Smart.", flush=True)
                await ctx.close()
                return

        print(">>> LOGADO e Doc2You ACESSÍVEL! Listando documentos...", flush=True)
        docs = await D.listar_documentos(ctx, args.data, args.data, status_doc="C", max_paginas=10)
        print(f">>> {len(docs)} documento(s) concluído(s) em {args.data}", flush=True)
        for d in docs[:10]:
            print(f"    - {d.get('tipo')} | op {d.get('operacao')} | nota {d.get('nota')} | chk {d.get('chk')}", flush=True)
        if docs:
            salvos, erros = await baixar_e_salvar(ctx, docs, args.data, args.limite)
            print(f">>> RESULTADO: {salvos} salvo(s), {erros} erro(s) em {OUT_DIR / args.data}", flush=True)
        await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
