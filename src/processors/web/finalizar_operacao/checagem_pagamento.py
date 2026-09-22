# -*- coding: utf-8 -*-
"""
checagem_pagamento.py - CHECAGEM 2 do job finalizar_operacao: a FORMA DE PAGAMENTO da operacao
esta corretamente preenchida?

A grade fica em operacao/gridpagamentodinheirocheque.php?op=<op>&ced=<ced>,
alcancada por: tela da operacao -> #invocarResumirOperacao -> #btnPagamento.
Mapeada ao vivo em 28/08/2026 (ops 64887 e 64882).

ATENCAO - por que le o DOM e nao o HTML: o HTML cru traz so o ESQUELETO dos
campos (sem value=, sem checked=; o <select> chega ate com dois <option
selected>). Quem preenche e o JS da propria pagina. Parsear o HTML daria
"tudo vazio" e reprovaria toda operacao.

Campos da linha N (o sufixo e o numero da linha):
    ftipN  Tipo             ftchN  Tipo PIX (select)   fchaN  Chave PIX (select)
    fccrN  Cta. origem      fnumN  Numero              fcdtN  Cta. destino (select)
    fnbcN  Bco              fageN  Ag                  ftpcN  Tp. Conta (select)
    fctdN  CC               fbenN  Favorecido          fcpfN  CPF/CNPJ
    fidtN  ID Transacao     fdatN  Vencto (date)       fvalN  Valor
    ckspN  SP (checkbox)

Uso isolado (read-only, NAO clica em Finalizar):
  python finalizar_operacao/checagem_pagamento.py --op 64887
"""
import argparse
import os
import sys
from datetime import date

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import r7_config as cfg          # noqa: E402
from mapear_pagamento import abrir_pagamento  # noqa: E402

# de-para: nome canonico -> prefixo do campo na grade
CAMPOS = {
    "tipo": "ftip", "tipo_pix": "ftch", "chave_pix": "fcha",
    "cta_origem": "fccr", "numero": "fnum", "cta_destino": "fcdt",
    "bco": "fnbc", "agencia": "fage", "tipo_conta": "ftpc", "cc": "fctd",
    "favorecido": "fben", "cpf_cnpj": "fcpf", "id_transacao": "fidt",
    "vencto": "fdat", "valor": "fval", "sp": "cksp",
}
_ROTULO = {
    "tipo": "Tipo", "tipo_pix": "Tipo PIX", "chave_pix": "Chave PIX",
    "cta_origem": "Cta. origem", "numero": "Numero", "cta_destino": "Cta. destino",
    "bco": "Bco", "agencia": "Ag", "tipo_conta": "Tp. Conta", "cc": "CC",
    "favorecido": "Favorecido", "cpf_cnpj": "CPF/CNPJ", "id_transacao": "ID Transacao",
    "vencto": "Vencto", "valor": "Valor", "sp": "SP",
}

_JS_LINHAS = r"""(campos) => {
  const texto = el => {
    if (!el) return null;
    if (el.tagName === 'SELECT') {
      const o = el.options[el.selectedIndex];
      // valor "0" e o placeholder "Selecione ..." -> conta como vazio
      if (!o || el.value === '0' || el.value === '') return '';
      return (o.text || '').trim();
    }
    if (el.type === 'checkbox' || el.type === 'radio') return el.checked ? 'SIM' : 'NAO';
    return (el.value || '').trim();
  };
  const linhas = [];
  for (let i = 1; i <= 200; i++) {
    if (!document.querySelector(`[name="${campos.tipo}${i}"]`)) break;
    const linha = { _linha: i };
    for (const [canon, pref] of Object.entries(campos)) {
      linha[canon] = texto(document.querySelector(`[name="${pref}${i}"]`));
    }
    linhas.push(linha);
  }
  return linhas;
}"""


def _norm(s):
    return " ".join(str(s or "").split()).strip().lower()


def ler_grade(pg, op, log=print):
    """Navega ate a grade e devolve a lista de linhas (dicts). [] = sem forma
    de pagamento registrada."""
    fr = abrir_pagamento(pg, op, log=log)
    if fr is None:
        raise RuntimeError("nao cheguei na grade de pagamento da op " + str(op))
    return fr.evaluate(_JS_LINHAS, CAMPOS)


def conferir_linhas(linhas, hoje=None):
    """Aplica as regras. Retorna {'ok', 'pendencias', 'linhas'}."""
    hoje = hoje or date.today()
    pendencias = []

    if not linhas:
        return {"ok": False, "linhas": [],
                "pendencias": ["Forma de pagamento: NAO ha nenhuma linha registrada "
                               "na tela de pagamento da operacao"]}

    for linha in linhas:
        n = linha["_linha"]
        pref = f"Pagamento (linha {n}): " if len(linhas) > 1 else "Pagamento: "

        # 1) Tipo tem de ser PIX
        if _norm(linha.get("tipo")) != _norm(cfg.TIPO_PAGAMENTO_ESPERADO):
            pendencias.append(f"{pref}Tipo e '{linha.get('tipo') or '(vazio)'}', "
                              f"deveria ser '{cfg.TIPO_PAGAMENTO_ESPERADO}'")

        # 2) Cta. origem tem de ser a conta da Prosper
        origem = _norm(linha.get("cta_origem"))
        if _norm(cfg.CONTA_ORIGEM_ESPERADA) not in origem:
            pendencias.append(f"{pref}Cta. origem e '{linha.get('cta_origem') or '(vazio)'}', "
                              f"deveria ser '{cfg.CONTA_ORIGEM_ESPERADA}'")

        # 3) campos obrigatorios preenchidos
        for canon in cfg.CAMPOS_OBRIGATORIOS:
            if canon not in CAMPOS:
                continue
            if not _norm(linha.get(canon)):
                pendencias.append(f"{pref}campo '{_ROTULO.get(canon, canon)}' esta VAZIO")

        # 4) chave PIX
        if cfg.EXIGIR_CHAVE_PIX and not _norm(linha.get("chave_pix")):
            pendencias.append(f"{pref}campo 'Chave PIX' esta VAZIO")

        # 5) vencimento = hoje (o input date entrega AAAA-MM-DD)
        if cfg.EXIGIR_VENCTO_HOJE:
            venc = (linha.get("vencto") or "").strip()
            if venc != hoje.isoformat():
                legivel = "-".join(reversed(venc.split("-"))) if venc else "(vazio)"
                pendencias.append(f"{pref}Vencto e {legivel}, deveria ser hoje "
                                  f"({hoje.strftime('%d/%m/%Y')})")

        # 6) SP marcado
        if cfg.EXIGIR_SP_MARCADO and linha.get("sp") != "SIM":
            pendencias.append(f"{pref}o campo 'SP' NAO esta marcado")

    return {"ok": not pendencias, "pendencias": pendencias, "linhas": linhas}


def conferir(pg, op, hoje=None, log=print):
    """Le a grade e aplica as regras. Retorna o dict de conferir_linhas."""
    return conferir_linhas(ler_grade(pg, op, log=log), hoje=hoje)


def main():
    ap = argparse.ArgumentParser(description="Confere a forma de pagamento (PIX) da operacao.")
    ap.add_argument("--op", required=True)
    ap.add_argument("--cdp", default=str(cfg.CDP_PORT))
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.cdp}")
        except Exception as e:
            print(f"[ERRO] CDP {args.cdp} nao responde: {e}")
            return 2
        ctx = browser.contexts[0]
        pg = ctx.new_page()
        # DISMISS, nao accept: nada aqui deve confirmar nenhuma acao.
        pg.on("dialog", lambda d: d.dismiss())
        try:
            r = conferir(pg, args.op)
        finally:
            try:
                pg.close()
            except Exception:
                pass

    print(f"\n=== FORMA DE PAGAMENTO op {args.op} | {len(r['linhas'])} linha(s) ===")
    for linha in r["linhas"]:
        print(f"\n  --- linha {linha['_linha']} ---")
        for canon in ("tipo", "tipo_pix", "chave_pix", "cta_origem", "cta_destino",
                      "bco", "agencia", "tipo_conta", "cc", "favorecido", "cpf_cnpj",
                      "vencto", "valor", "sp"):
            print(f"     {_ROTULO[canon]:<14} {linha.get(canon) or '(vazio)'}")
    if r["ok"]:
        print("\n  >> OK: forma de pagamento completa e correta.")
    else:
        print("\n  >> PENDENCIAS:")
        for pnd in r["pendencias"]:
            print(f"     - {pnd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
