# -*- coding: utf-8 -*-
"""
mapear_assinaturas.py - INSPETOR READ-ONLY do doc2you, p/ descobrir COMO ler os
ASSINANTES de um documento (nome + assinou/nao assinou).

Por que existe: o Aditivo NUNCA fica "Concluido" no doc2you, porque a assinatura
da Prosper e feita depois. A regra do negocio e "se falta SO a Prosper, pode
finalizar" - e p/ isso nao basta o status do documento, tem de olhar assinante a
assinante. A lista (documento/documentos) so traz o status agregado; o detalhe
com os assinantes esta atras do link de cada linha, que este script descobre.

O que faz (tudo GET/POST de leitura, nada de escrita):
  1. SSO no doc2you (via smart/doc2you.php);
  2. POST documento/documentos com numOperacao=<op> -> linhas dos documentos;
  3. lista TODOS os href/onclick de cada linha (o caminho p/ o detalhe);
  4. tenta abrir cada link e dizer se ali tem tabela de assinantes;
  5. mostra o que o parser heuristico (checagem_docs.parse_assinantes) extraiu.

Uso (rodar da RAIZ, com a sessao R7 no ar):
  python robo7_finalizar/mapear_assinaturas.py --op 64743
  python robo7_finalizar/mapear_assinaturas.py --op 64743 --cdp 9222 --so-aditivo

Saidas: debug_r7/doc2you_op<OP>_lista.html + doc2you_doc<idDoc>.html
"""
import argparse
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(_AQUI)
for _p in (_AQUI, os.path.join(_RAIZ, "robo3")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import checagem_docs as cd   # noqa: E402
import r7_config as cfg      # noqa: E402
import verificar_docs as vd  # noqa: E402


def _salvar(nome, conteudo):
    os.makedirs(cfg.DEBUG_DIR, exist_ok=True)
    caminho = os.path.join(cfg.DEBUG_DIR, nome)
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write(conteudo)
    return caminho


def main():
    ap = argparse.ArgumentParser(description="Descobre como ler os assinantes no doc2you.")
    ap.add_argument("--op", required=True)
    ap.add_argument("--cdp", default=str(cfg.CDP_PORT))
    ap.add_argument("--so-aditivo", action="store_true",
                    help="olha so o Aditivo (tipo 'Contrato') - e o caso que importa")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    from playwright.sync_api import sync_playwright
    print(f"=== MAPEAR ASSINANTES (doc2you) | op {args.op} | READ-ONLY ===\n")

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.cdp}")
        except Exception as e:
            print(f"[ERRO] CDP {args.cdp} nao responde: {e}\n"
                  "       Suba a sessao: python robo7_finalizar/sessao_r7.py")
            return 2
        ctx = browser.contexts[0]

        print("  fazendo SSO no doc2you...")
        cd.sso_doc2you(ctx)   # versao robusta do R7 (o vd.sso_doc2you estoura timeout)

        docs, html = cd._consultar(ctx, args.op)
        print(f"  lista salva em {_salvar(f'doc2you_op{args.op}_lista.html', html)}")
        if not docs:
            print("\n[!] 0 documentos. Ou a op nao tem digitais, ou o SSO nao pegou "
                  "(sessao nova precisa abrir smart/doc2you.php antes).")
            return 1

        print(f"\n--- {len(docs)} documento(s) na op {args.op} ---")
        for d in docs:
            canonico = cd._classificar(d)
            if args.so_aditivo and canonico != "aditivo":
                continue
            print(f"\n  idDoc={d['idDoc']} | tipo='{d['tipo']}' ({canonico}) | "
                  f"status='{d['status']}' | {d['descricao']}")
            if not d["links"]:
                print("     (nenhum href/onclick nesta linha - o detalhe deve abrir por JS)")
            for link in d["links"]:
                print(f"     link: {link[:140]}")

            assinantes = None
            for link in d["links"]:
                url = link if link.startswith("http") else \
                    "https://www.doc2you.com.br/" + link.lstrip("/")
                if not re.search(r"doc2you\.com\.br", url):
                    continue
                try:
                    r = ctx.request.get(url, timeout=45_000)
                    corpo = r.body().decode("utf-8", errors="replace")
                except Exception as e:
                    print(f"     -> {url[:90]} FALHOU: {e}")
                    continue
                achou = cd.parse_assinantes(corpo)
                print(f"     -> {url[:90]} | HTTP {r.status} | {len(corpo)} bytes | "
                      f"{len(achou)} assinante(s) reconhecido(s)")
                _salvar(f"doc2you_doc{d['idDoc']}.html", corpo)
                if achou and not assinantes:
                    assinantes = achou

            if assinantes:
                print("     ASSINANTES lidos:")
                for a in assinantes:
                    marca = "PROSPER" if cd._e_prosper(a) else "terceiro"
                    print(f"        [{marca:<8}] {a['nome'][:44]:<44} {a['documento']:<20} "
                          f"[{a['papel']}] -> {a['situacao']}")
                terceiros_pendentes = [a["nome"] for a in assinantes
                                       if cd._NAO_ASSINOU.search(a["situacao"])
                                       and not cd._e_prosper(a)]
                veredito = ("REPROVA (falta terceiro): " + ", ".join(terceiros_pendentes)
                            if terceiros_pendentes else "LIBERA (so a Prosper pendente)")
                print(f"     VEREDITO pela regra atual: {veredito}")
            else:
                print("     [!] nenhum assinante reconhecido - abra o HTML salvo em "
                      f"{cfg.DEBUG_DIR}/ e me mande a estrutura da tabela.")

    print(f"\nHTML salvo em {cfg.DEBUG_DIR}/ - use p/ apertar o parse_assinantes().")
    return 0


if __name__ == "__main__":
    sys.exit(main())
