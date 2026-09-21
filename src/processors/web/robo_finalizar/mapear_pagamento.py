# -*- coding: utf-8 -*-
"""
mapear_pagamento.py - INSPETOR READ-ONLY da tela de FORMA DE PAGAMENTO da
operacao (a grade PIX) e do botao que FINALIZA.

Caminho ate a tela (descoberto ao vivo em 28/08/2026, op 64887):
  novatelaoperacao.php?action=edit&op=<op>
    -> clique em #invocarResumirOperacao      (painel "Resumir")
    -> tela operacao/novoresumir.php
       -> clique em #btnPagamento  [onclick=dinheiroCheque(document.Form, <op>, <ced>)]
          -> tela operacao/gridpagamentodinheiro*.php  <- a grade PIX mora aqui
             colunas: Tipo | Tipo PIX | Chave PIX | Cta. origem | Numero |
                      Cta. destino | Bco | Ag | Tp. Conta | CC | Favorecido |
                      CPF/CNPJ | ID Transacao | Vencto | Valor | SP

O botao FINALIZAR e o #pagamento, que vive NESTA tela (nao no resumir). O JS do
Smart faz suas proprias travas antes de finalizar:
  - verificacriticasfinalizar.php  (criticas da operacao)
  - #edicaoPermissaoFO  = 0 -> "usuario nao possui privilegios para finalizar"
  - #fechamentoContabil = 1 -> bloqueia por fechamento contabil do #anofechado
  - saldo != 0 sem #cbCC -> "Informe uma opcao para o saldo!"

SEGURANCA: este script NAO clica no #pagamento e DISPENSA (dismiss) qualquer
dialogo, justamente p/ nao finalizar nada por acidente.

Uso (rodar da RAIZ, com a sessao R7 no ar):
  python robo7_finalizar/mapear_pagamento.py --op 64887
"""
import argparse
import json
import os
import re
import sys
import time

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from playwright.sync_api import sync_playwright  # noqa: E402

import r7_config as cfg  # noqa: E402

_JS = r"""() => {
  const txt = e => ((e.innerText || e.textContent || '') + '').replace(/\s+/g, ' ').trim();
  const campo = el => ({
    tag: el.tagName, type: el.type || '', name: el.name || '', id: el.id || '',
    val: (el.type === 'checkbox' || el.type === 'radio')
           ? ((el.checked ? 'CHECKED' : 'unchecked') + ':' + el.value)
           : (el.value || '').slice(0, 50),
    sel: (el.tagName === 'SELECT' && el.selectedIndex >= 0 && el.options[el.selectedIndex])
           ? el.options[el.selectedIndex].text.slice(0, 40) : null,
    dis: !!el.disabled
  });
  const tabelas = [...document.querySelectorAll('table')].map(t => {
    const ths = [...t.querySelectorAll('th')].map(txt);
    if (!ths.some(x => /Chave PIX|Favorecido|Cta\. destino/i.test(x))) return null;
    const linhas = [...t.querySelectorAll('tr')]
      .filter(tr => tr.querySelector('td'))
      .map(tr => [...tr.children].map((td, j) => ({
        col: ths[j] || ('c' + j),
        texto: txt(td).slice(0, 44),
        campos: [...td.querySelectorAll('input,select,textarea')].map(campo)
      })));
    return { id: t.id || '', ths: ths, linhas: linhas };
  }).filter(Boolean);
  const botoes = [...document.querySelectorAll('button,input[type=button],input[type=submit],a[onclick]')]
    .map(b => ({ id: b.id || '', txt: (txt(b) || b.value || '').slice(0, 40),
                 oc: (b.getAttribute('onclick') || '').slice(0, 100), dis: !!b.disabled }))
    .filter(b => b.id || b.txt);
  const ocultos = {};
  for (const n of ['edicaoPermissaoFO', 'fechamentoContabil', 'anofechado', 'update',
                   'vSaldo', 'vSaldoCC', 'cbCC', 'dinheiroCheque']) {
    const el = document.querySelector('#' + n);
    if (el) ocultos[n] = (el.value || '') + (el.disabled ? ' (disabled)' : '');
  }
  return { url: location.href, tabelas: tabelas, botoes: botoes, ocultos: ocultos };
}"""


def _frame_com(pg, seletor, timeout_s=30, intervalo=1.0):
    """Espera ATIVAMENTE por um frame que contenha o seletor. Devolve o frame
    ou None. Nao usar sleep fixo: a tela da operacao monta os frames por JS e o
    tempo varia muito de operacao p/ operacao (4s basta numa e nao na outra)."""
    fim = time.time() + timeout_s
    while time.time() < fim:
        for f in pg.frames:
            try:
                if f.locator(seletor).count():
                    return f
            except Exception:
                continue          # frame trocou/detached no meio da varredura
        time.sleep(intervalo)
    return None


def _ir_para_operacao(pg, op, tentativas=3, log=print):
    """Abre a tela da operacao e espera o painel ficar utilizavel.

    NAO usar wait_until='domcontentloaded': essa tela monta frames por JS e o
    evento as vezes nao dispara -> Timeout de 60s sem motivo real. 'commit'
    retorna assim que a navegacao e aceita e a espera fica por nossa conta
    (mesma licao do SSO do doc2you)."""
    for i in range(1, tentativas + 1):
        try:
            pg.goto(cfg.URL_EDITAR.format(op=op), wait_until="commit", timeout=45_000)
            if _frame_com(pg, "#invocarResumirOperacao", timeout_s=30):
                return True
            log(f"  [nav] tentativa {i}: #invocarResumirOperacao nao apareceu em 30s")
        except Exception as e:
            log(f"  [nav] tentativa {i} falhou: {str(e)[:90]}")
        time.sleep(3)
    return False


def abrir_pagamento(pg, op, log=print):
    """Navega ate a grade de pagamento. Retorna o frame (ou None)."""
    if not _ir_para_operacao(pg, op, log=log):
        log(f"  [!] nao consegui abrir a tela da op {op}")
        return None
    fr = _frame_com(pg, "#invocarResumirOperacao", timeout_s=10)
    if fr is None:
        log("  [!] #invocarResumirOperacao nao encontrado (op nao esta editavel?)")
        return None
    fr.locator("#invocarResumirOperacao").click(timeout=15_000)

    fr2 = _frame_com(pg, "#btnPagamento", timeout_s=30)
    if fr2 is None:
        log("  [!] #btnPagamento nao apareceu no Resumir")
        return None
    fr2.locator("#btnPagamento").click(timeout=15_000)

    # a grade pode vir no mesmo frame 'stage' ou num frame novo
    grade = _frame_com(pg, "th:has-text('Chave PIX')", timeout_s=30)
    if grade is not None:
        time.sleep(2)      # deixa o JS terminar de preencher os campos
        return grade
    for f in pg.frames:
        if "gridpagamento" in (f.url or ""):
            return f
    return None


def main():
    ap = argparse.ArgumentParser(description="Mapeia a grade de pagamento (PIX) da operacao. READ-ONLY.")
    ap.add_argument("--op", required=True)
    ap.add_argument("--cdp", default=str(cfg.CDP_PORT))
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print(f"=== MAPEAR PAGAMENTO | op {args.op} | READ-ONLY (nao clica em Finalizar) ===\n")
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.cdp}")
        except Exception as e:
            print(f"[ERRO] CDP {args.cdp} nao responde: {e}")
            return 2
        ctx = browser.contexts[0]
        pg = ctx.new_page()
        dialogos = []
        # DISMISS, nao accept: um confirm() de finalizacao aceito por engano
        # finalizaria a operacao de verdade.
        pg.on("dialog", lambda d: (dialogos.append(f"{d.type}: {d.message[:140]}"), d.dismiss()))
        try:
            fr = abrir_pagamento(pg, args.op)
            if fr is None:
                print("  [!] nao cheguei na grade de pagamento.")
                return 1
            print(f"  frame da grade: {fr.url[:100]}")
            dados = fr.evaluate(_JS)
            os.makedirs(cfg.DEBUG_DIR, exist_ok=True)
            saida = os.path.join(cfg.DEBUG_DIR, f"pagamento_op{args.op}.json")
            with open(saida, "w", encoding="utf-8") as fh:
                json.dump(dados, fh, ensure_ascii=False, indent=1)
            try:
                with open(os.path.join(cfg.DEBUG_DIR, f"pagamento_op{args.op}.html"),
                          "w", encoding="utf-8") as fh:
                    fh.write(fr.content())
            except Exception:
                pass

            for t in dados["tabelas"]:
                print(f"\n  TABELA id='{t['id']}' | colunas: {[x for x in t['ths'] if x.strip()]}")
                for i, linha in enumerate(t["linhas"], 1):
                    print(f"\n  --- linha {i} ---")
                    for c in linha:
                        if not c["col"].strip() or c["col"].startswith("&"):
                            continue
                        campos = "; ".join(
                            f"{f['tag']}[{f['type']}] name='{f['name']}' -> '{f['val']}'"
                            + (f" (opcao='{f['sel']}')" if f["sel"] else "")
                            + (" DISABLED" if f["dis"] else "")
                            for f in c["campos"]) or f"(texto) '{c['texto']}'"
                        print(f"     {c['col'][:14]:<14} {campos}")

            print(f"\n  CAMPOS DE CONTROLE: {dados['ocultos']}")
            print("\n  BOTOES:")
            for b in dados["botoes"]:
                marca = "  <== FINALIZAR" if b["id"] == "pagamento" else ""
                print(f"     id='{b['id'][:22]:<22}' txt='{b['txt'][:24]:<24}' "
                      f"{'DISABLED ' if b['dis'] else ''}oc={b['oc'][:60]}{marca}")
            if dialogos:
                print(f"\n  DIALOGOS (dispensados): {dialogos}")
            print(f"\n  salvo em {saida}")
        finally:
            try:
                pg.close()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
