# -*- coding: utf-8 -*-
"""
_analisar_credito_v3.py - Robo 1 (analise de credito): hook de CLASSE DE RISCO.

Instala o hook PRE-SALVAR que ajusta a classe de risco dos titulos ANTES do
SALVAR (regra por MAIORIA: 'E' -> 'B'; 'P' -> 'T'; se houver QUALQUER titulo em
'C'/'CE' -> NAO mexe). A aplicacao REAL liga com CLASSE_RISCO_APLICAR=1 (a V4
liga). Reusa TODO o fluxo do V1 (robo.main()).

CONFERENCIA POR IA (Claude) REMOVIDA daqui (2026-06-29): a analise dos documentos
virou uma automacao SEPARADA que le os PDFs salvos na pasta do Nextcloud. Este
robo nao chama mais o Claude nem varre etapas atras de documentos -> mais rapido.

Uso:
  python _analisar_credito_v3.py             # robo completo (instala hook + loop)
  python _analisar_credito_v3.py --classe 61086   # testa SO a classe (read-only)
"""
import argparse
import collections
import os
import sys
import time

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import config                       # noqa: E402
import conta_operacao               # noqa: E402
import _analisar_credito_base as robo  # noqa: E402


# ------------------------------------------------------------------ #
# CLASSE DE RISCO dos titulos — ajuste ANTES de clicar SALVAR (hook pre-salvar).
# Regra (por MAIORIA): maioria 'E' -> todos 'B'; maioria 'P' -> todos 'T';
# se houver QUALQUER titulo em 'C' ou 'CE' -> NAO mexe. So esses 2 padroes.
# Liga a aplicacao REAL com CLASSE_RISCO_APLICAR=1; padrao = so LOG (read-only).
# ------------------------------------------------------------------ #
_CR_APLICAR = os.getenv("CLASSE_RISCO_APLICAR", "0").strip().lower() in ("1", "true", "sim", "yes", "on")
_CR_MAP = {"E": "B", "P": "T"}     # classe MAIORITARIA -> classe alvo
_CR_PULAR = {"C", "CE"}            # se aparecer alguma destas -> pula a operacao


def _frame_classe_risco(page):
    """Acha o frame que tem os botoes #classeRisco_ e a funcao SelecionarClasseRiscoMaster."""
    for fr in page.frames:
        try:
            ok = fr.evaluate("() => (typeof SelecionarClasseRiscoMaster === 'function') "
                             "&& !!document.querySelector('[id^=classeRisco_]')")
            if ok:
                return fr
        except Exception:
            continue
    return None


def ajustar_classe_risco(page_edit, op):
    """Le a classe de risco de TODOS os titulos (botoes #classeRisco_<n>) e, pela MAIORIA,
    aplica E->B ou P->T em todos via SelecionarClasseRiscoMaster, ANTES do SALVAR. Pula se
    houver titulo em C/CE. Por padrao SO LOGA; aplica de fato com CLASSE_RISCO_APLICAR=1.
    Best-effort: nunca derruba o robo."""
    fr = None
    for _ in range(12):                 # o grid carrega via ajax; espera ate ~12s
        fr = _frame_classe_risco(page_edit)
        if fr:
            break
        time.sleep(1)
    if not fr:
        print(f"  [classe risco op {op}] grid de classe nao encontrado -> pula")
        return
    classes = fr.evaluate("() => [...document.querySelectorAll('[id^=classeRisco_]')]"
                          ".map(b => (b.innerText||'').trim()).filter(Boolean)")
    if not classes:
        print(f"  [classe risco op {op}] nenhum titulo com classe -> pula")
        return
    cont = collections.Counter(classes)
    maioria, qtd = cont.most_common(1)[0]
    print(f"  [classe risco op {op}] atuais={dict(cont)} -> maioria '{maioria}' ({qtd}/{len(classes)})")
    if _CR_PULAR & set(classes):
        print(f"  [classe risco op {op}] tem titulo em C/CE -> NAO mexe")
        return
    alvo = _CR_MAP.get(maioria)
    if not alvo:
        print(f"  [classe risco op {op}] maioria '{maioria}' sem regra (so E->B, P->T) -> NAO mexe")
        return
    if not _CR_APLICAR:
        print(f"  [classe risco op {op}] [DRY classe] MUDARIA todos {maioria} -> {alvo} "
              f"(CLASSE_RISCO_APLICAR=0; nao aplicado)")
        return
    try:
        fr.evaluate("(c) => SelecionarClasseRiscoMaster(c)", alvo)
        print(f"  [classe risco op {op}] APLICADO: todos -> {alvo} (era maioria {maioria})")
    except Exception as e:
        print(f"  [classe risco op {op}] erro ao aplicar: {e}")


def _testar_na_op(op, ajuste, rotulo):
    """Roda UM ajuste pre-salvar numa op, sem clicar em SALVAR (read-only).

    Serve para conferir a leitura/decisao contra uma operacao real antes de ligar
    a aplicacao de verdade. Nao salva nada: o SALVAR nao e clicado aqui.
    """
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=config.USER_DATA_DIR, headless=config.HEADLESS,
            channel="chrome",
            args=["--start-maximized", "--no-sandbox", "--disable-dev-shm-usage"],
            no_viewport=True)
        try:
            try:
                robo.login(ctx)
            except Exception as e:
                print(f"[{rotulo}] aviso ao logar: {e}")
            page = ctx.new_page()
            page.goto(config.URL_EDITAR.format(op=op),
                      wait_until="domcontentloaded", timeout=60_000)
            ajuste(page, op)   # so loga, a menos que a flag do ajuste esteja ligada
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def _hooks_pre_salvar(page_edit, op):
    """Roda os ajustes pre-SALVAR em ordem; um que falhe nao impede o seguinte.

    A CONTA vem por ULTIMO de proposito: e o ajuste que reabilita o
    `#SalvarOperacaoButton` (via `onchange`), entao e o ultimo evento antes do
    clique — nada depois dele pode re-desabilitar o botao sem aparecer no log.
    """
    for nome, fn in (("classe risco", ajustar_classe_risco),
                     ("conta", conta_operacao.ajustar_conta)):
        try:
            fn(page_edit, op)
        except Exception as e:                                   # noqa: BLE001
            print(f"  [{nome} op {op}] erro ignorado: {e}")


def _instalar_hook_classe():
    robo.pre_salvar_hook = _hooks_pre_salvar
    print(f"[classe risco] ajuste no SALVAR: "
          f"{'APLICA de verdade (E->B, P->T)' if _CR_APLICAR else 'modo LOG/read-only (nao altera)'}.")
    print(f"[conta] destravar op com Conta vazia -> '{conta_operacao.ALVO}': "
          f"{'APLICA de verdade' if conta_operacao.APLICAR else 'modo LOG/read-only (nao altera)'}.")


def main():
    ap = argparse.ArgumentParser(description="Robo 1 (analise de credito) + hook de classe de risco.")
    ap.add_argument("--classe", help="testa SO a leitura/decisao de classe de risco numa op (read-only)")
    ap.add_argument("--conta", help="testa SO a leitura/decisao do campo Conta numa op (read-only)")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if args.classe:
        _testar_na_op(args.classe, ajustar_classe_risco, "classe")
    elif args.conta:
        _testar_na_op(args.conta, conta_operacao.ajustar_conta, "conta")
    else:
        _instalar_hook_classe()
        robo.main()   # reusa TODO o fluxo do V1 + o hook pre-salvar (classe de risco)


if __name__ == "__main__":
    main()
