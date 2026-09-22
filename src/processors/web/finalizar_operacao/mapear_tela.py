# -*- coding: utf-8 -*-
"""
mapear_tela.py - INSPETOR READ-ONLY da tela da operacao, p/ descobrir as duas
coisas que o job finalizar_operacao precisa e que ainda NAO estao mapeadas no projeto:

  (A) a GRADE DE FORMA DE PAGAMENTO (colunas Tipo | Tipo PIX | Chave PIX |
      Cta. origem | Cta. destino | Bco | Ag | Tp. Conta | CC | Favorecido |
      CPF/CNPJ | Vencto | Valor | SP) -> onde ela mora no DOM, quais os NAMES
      dos inputs e de qual endpoint os dados vem;
  (B) o botao FINALIZAR dentro do "Resumir" (#invocarResumirOperacao) -> id,
      onclick e qual POST ele dispara.

NAO CLICA em nada que grave: so abre a tela, abre o Resumir e LE o DOM. As
requisicoes de rede sao apenas OBSERVADAS (nao ha route/abort).

Uso (rodar da RAIZ, com uma sessao logada no CDP informado):
  python finalizar_operacao/mapear_tela.py --op 64743
  python finalizar_operacao/mapear_tela.py --op 64743 --cdp 9222 --sem-resumir

Saidas: debug_r7/op<OP>_*.html + debug_r7/mapa_op<OP>.json + relatorio no stdout.
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

# palavras que denunciam o botao de finalizar
_FINALIZAR = re.compile(r"(finaliz|efetiv|concluir\s*opera)", re.I)

# JS que varre UM documento (frame) e devolve o que interessa
_JS_DUMP = r"""() => {
  const txt = e => ((e.innerText || e.textContent || '') + '').replace(/\s+/g, ' ').trim();
  const q = s => [...document.querySelectorAll(s)];

  // 1) tabelas cujo cabecalho cheira a "forma de pagamento"
  const alvo = /chave\s*pix|favorecido|cta\.?\s*destino|tp\.?\s*conta|vencto/i;
  const tabelas = q('table').map((t, i) => {
    const ths = [...t.querySelectorAll('th')].map(txt).filter(Boolean);
    const cab = ths.join(' | ');
    if (!alvo.test(cab)) return null;
    // primeira linha de dados: o que cada celula tem + os inputs dentro dela
    const tr = t.querySelector('tbody tr') || t.querySelectorAll('tr')[1];
    const celulas = tr ? [...tr.children].map((td, j) => ({
      col: ths[j] || ('col' + j),
      texto: txt(td).slice(0, 60),
      campos: [...td.querySelectorAll('input,select,textarea')].map(el => ({
        tag: el.tagName.toLowerCase(),
        type: el.type || '',
        name: el.name || '',
        id: el.id || '',
        value: (el.type === 'checkbox' || el.type === 'radio')
                 ? ((el.checked ? 'CHECKED:' : 'unchecked:') + el.value)
                 : (el.value || '').slice(0, 60),
        opcao: (el.tagName === 'SELECT' && el.selectedIndex >= 0 && el.options[el.selectedIndex])
                 ? el.options[el.selectedIndex].text : undefined
      }))
    })) : [];
    return { indice: i, id: t.id || '', classe: t.className || '', cabecalho: cab,
             linhas: t.querySelectorAll('tbody tr').length, celulas: celulas };
  }).filter(Boolean);

  // 2) botoes/acoes (p/ achar o Finalizar)
  const botoes = q('button,input[type=button],input[type=submit],a,span[onclick],div[onclick],li[onclick]')
    .map(b => ({ txt: (txt(b) || b.value || '').slice(0, 60),
                 id: b.id || '',
                 onclick: (b.getAttribute('onclick') || '').slice(0, 200),
                 href: (b.getAttribute('href') || '').slice(0, 120) }))
    .filter(b => b.txt || b.onclick || b.id);

  // 3) variaveis/JSON globais uteis (o padrao dadosTOP do classe_risco_tool)
  const globais = Object.keys(window).filter(k => /^dados|pagamento|pix/i.test(k)).slice(0, 40);

  return { url: location.href, tabelas: tabelas, botoes: botoes, globais: globais,
           titulo: document.title, bytes: document.documentElement.outerHTML.length };
}"""


def _dump_frames(page, rotulo, op, salvar=True):
    """Varre TODOS os frames da pagina e imprime o que casar com os alvos."""
    achados = {"pagamento": [], "finalizar": []}
    for fr in page.frames:
        try:
            info = fr.evaluate(_JS_DUMP)
        except Exception as e:
            print(f"   [frame {fr.name or fr.url[:60]}] nao avaliou: {e}")
            continue
        nome = fr.name or (fr.url.rsplit("/", 1)[-1][:40] or "root")
        print(f"\n--- [{rotulo}] frame '{nome}' | {info['bytes']} bytes | {info['url'][:100]}")

        for t in info["tabelas"]:
            print(f"   >>> TABELA DE PAGAMENTO (id='{t['id']}' classe='{t['classe']}' "
                  f"{t['linhas']} linha(s))")
            print(f"       cabecalho: {t['cabecalho']}")
            for c in t["celulas"]:
                campos = "; ".join(
                    f"{f['tag']}[{f['type']}] name='{f['name']}' id='{f['id']}' -> '{f['value']}'"
                    + (f" (opcao='{f['opcao']}')" if f.get("opcao") else "")
                    for f in c["campos"]) or "(sem input - so texto)"
                print(f"       - {c['col']:<14} texto='{c['texto']}' | {campos}")
            achados["pagamento"].append(dict(t, frame=nome))

        for b in info["botoes"]:
            if _FINALIZAR.search(b["txt"]) or _FINALIZAR.search(b["onclick"]) \
                    or _FINALIZAR.search(b["id"]):
                print(f"   >>> BOTAO FINALIZAR? txt='{b['txt']}' id='{b['id']}' "
                      f"onclick='{b['onclick']}' href='{b['href']}'")
                achados["finalizar"].append(dict(b, frame=nome))

        if info["globais"]:
            print(f"   globais interessantes: {info['globais']}")

        if salvar:
            os.makedirs(cfg.DEBUG_DIR, exist_ok=True)
            safe = re.sub(r"\W+", "_", nome)[:40]
            caminho = os.path.join(cfg.DEBUG_DIR, f"op{op}_{rotulo}_{safe}.html")
            try:
                with open(caminho, "w", encoding="utf-8") as fh:
                    fh.write(fr.content())
            except Exception:
                pass
    return achados


def main():
    ap = argparse.ArgumentParser(description="Inspetor read-only da tela da operacao (finalizar_operacao).")
    ap.add_argument("--op", required=True, help="numero da operacao (use uma em 'Aguardando Ass.')")
    ap.add_argument("--cdp", default=str(cfg.CDP_PORT),
                    help=f"porta CDP da sessao logada (default {cfg.CDP_PORT}; a do job de credito e outra)")
    ap.add_argument("--sem-resumir", action="store_true",
                    help="nao abre o painel Resumir (so mapeia a tela da operacao)")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    url = cfg.URL_EDITAR.format(op=args.op)
    print(f"=== MAPEAR TELA | op {args.op} | CDP {args.cdp} | READ-ONLY ===\n{url}\n")

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.cdp}")
        except Exception as e:
            print(f"[ERRO] CDP {args.cdp} nao responde: {e}\n"
                  f"       Sem Chrome deste job no ar: a sessao so existe durante uma rodada (smart_sessao.sessao)")
            return 2
        ctx = browser.contexts[0]
        page = ctx.new_page()
        page.on("dialog", lambda d: d.accept())

        # OBSERVA a rede (sem interceptar) p/ descobrir de onde vem o pagamento
        rede = []
        page.on("request", lambda r: rede.append((r.method, r.url, (r.post_data or "")[:200])))
        ctx.on("page", lambda pg: pg.on("request",
               lambda r: rede.append(("POPUP " + r.method, r.url, (r.post_data or "")[:200]))))

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            time.sleep(3)
            if "expira.php" in page.content() or "expira.php" in page.url:
                print("[ERRO] sessao EXPIRADA (o Smart devolveu expira.php). "
                      "Logue na janela do Chrome desse CDP e rode de novo.")
                return 3

            print("\n########## PASSO 1: tela da operacao (sem abrir nada) ##########")
            a1 = _dump_frames(page, "tela", args.op)

            a2 = {"pagamento": [], "finalizar": []}
            if not args.sem_resumir:
                print("\n########## PASSO 2: abrindo o painel 'Resumir' ##########")
                try:
                    alvo = None
                    for fr in page.frames:
                        if fr.locator("#invocarResumirOperacao").count():
                            alvo = fr
                            break
                    if alvo is None:
                        print("   [!] #invocarResumirOperacao nao encontrado em nenhum frame.")
                    else:
                        alvo.locator("#invocarResumirOperacao").click(timeout=15_000)
                        time.sleep(4)
                        a2 = _dump_frames(page, "resumir", args.op)
                except Exception as e:
                    print(f"   [!] erro ao abrir o Resumir: {e}")

            print("\n########## PASSO 3: requisicoes observadas ##########")
            vistas = set()
            for metodo, u, body in rede:
                chave = (metodo, u.split("?")[0])
                if chave in vistas:
                    continue
                vistas.add(chave)
                if re.search(r"\.php|ajax", u, re.I):
                    print(f"   {metodo:<10} {u[:130]}")
                    if body:
                        print(f"              body: {body}")

            print("\n" + "=" * 70)
            pg = a1["pagamento"] + a2["pagamento"]
            fz = a1["finalizar"] + a2["finalizar"]
            print(f"RESUMO: {len(pg)} tabela(s) de pagamento | {len(fz)} candidato(s) a Finalizar")
            if not pg:
                print("  [!] grade de pagamento NAO encontrada -> pode estar em popup/aba"
                      " propria. Rode de novo com a aba de pagamento ja aberta na tela.")
            if not fz:
                print("  [!] botao Finalizar NAO encontrado -> confira se a op esta mesmo"
                      " em 'Aguardando Ass.'.")
            os.makedirs(cfg.DEBUG_DIR, exist_ok=True)
            saida = os.path.join(cfg.DEBUG_DIR, f"mapa_op{args.op}.json")
            with open(saida, "w", encoding="utf-8") as fh:
                json.dump({"pagamento": pg, "finalizar": fz}, fh, ensure_ascii=False, indent=2)
            print(f"  mapa salvo em {saida}")
            print(f"  HTML dos frames em {cfg.DEBUG_DIR}/")
            print("=" * 70)
        finally:
            try:
                page.close()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
