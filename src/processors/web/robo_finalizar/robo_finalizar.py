# -*- coding: utf-8 -*-
"""
robo_finalizar.py - ORQUESTRADOR do Robo 7.

Para cada operacao na etapa "Aguardando Ass.":
  1. le os titulos da tela (tipos: LCB/DUR/DSR/...) e o nome do cedente;
  2. CHECAGEM 1 - documentos assinados no doc2you  (checagem_docs);
  3. se os documentos estao ok -> CHECAGEM 2, forma de pagamento (checagem_pagamento);
  4. tudo OK  -> clica em FINALIZAR (so com --executar; DRY e o padrao);
     algo NOK -> NAO finaliza e manda UM e-mail com as pendencias da op.

ORDEM (regra do usuario): a forma de pagamento so e conferida DEPOIS que as
assinaturas estao ok - enquanto ninguem assinou, o cadastro de pagamento ainda
esta sendo montado e cobrar dele so gera ruido. Desligue o portao com
R7_PAGAMENTO_SO_APOS_ASSINATURAS=0 se quiser as duas sempre.

Dentro de um mesmo momento o e-mail continua sendo UM por operacao, com tudo o
que falta naquela etapa - o operador nunca recebe uma pendencia de cada vez.

Uso (rodar da RAIZ; o robo sobe a PROPRIA sessao do Smart - `--cdp` anexa numa ja aberta):
  python robo7_finalizar/robo_finalizar.py                    # DRY, sem e-mail
  python robo7_finalizar/robo_finalizar.py --ops 64886,64890  # ops especificas
  python robo7_finalizar/robo_finalizar.py --email            # DRY + manda o e-mail
  python robo7_finalizar/robo_finalizar.py --executar --email # PRODUCAO
  python robo7_finalizar/robo_finalizar.py --loop             # ciclo continuo
"""
import argparse
import csv
import os
import sys
import time
import traceback
from datetime import datetime

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(_AQUI)
for _p in (_AQUI, os.path.join(_RAIZ, "operacoes"), os.path.join(_RAIZ, "robo1_analise_credito")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import checagem_docs                 # noqa: E402
import checagem_pagamento            # noqa: E402
import finalizar as fin              # noqa: E402
import listar_fila                   # noqa: E402
import notificar                     # noqa: E402
import notificar_whatsapp            # noqa: E402
import r7_config as cfg              # noqa: E402


def _dados_da_operacao(ctx, op):
    """Tipos dos titulos (do dadosTOP da tela) + nome do cedente (do espelho).
    O cedente e a TRAVA da excecao do Aditivo, entao vale a consulta."""
    import classe_risco_tool as crt
    from smart_session import Smart
    tipos, cedente, valor = [], None, None
    try:
        dados = crt.carregar_operacao(Smart.attach(ctx), op)
        tipos = [t.get("tipoTitulo", "") for t in dados["titulos"]]
    except Exception as e:
        print(f"  [op {op}] nao li os titulos da tela: {str(e)[:90]}")
    try:
        extra = listar_fila.enriquecer([op]).get(str(op))
        if extra:
            cedente = extra.get("cedente")
            valor = extra.get("valor")
    except Exception:
        pass
    return tipos, cedente, valor


def _fmt_valor(valor):
    if valor is None:
        return None
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _registrar_finalizada(op, cedente):
    novo = not os.path.exists(cfg.ARQ_FINALIZADAS)
    with open(cfg.ARQ_FINALIZADAS, "a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        if novo:
            w.writerow(["quando", "op", "cedente"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(op), cedente or ""])


def processar(ctx, op, executar=False, mandar_email=False):
    """Roda as duas checagens numa op e decide. Retorna dict com o laudo."""
    op = str(op)
    laudo = {"op": op, "pendencias": [], "observacoes": [], "acao": None,
             "cedente": None, "tipos": [], "erro": None}
    print(f"\n{'=' * 66}\n  OPERACAO {op}\n{'=' * 66}")

    tipos, cedente, valor = _dados_da_operacao(ctx, op)
    laudo["tipos"], laudo["cedente"] = sorted(set(t for t in tipos if t)), cedente
    print(f"  cedente: {cedente or '(nao identificado)'} | titulos: {laudo['tipos'] or '(nao lidos)'}")

    # ---- CHECAGEM 1: documentos assinados -------------------------------- #
    try:
        r_docs = checagem_docs.conferir(ctx, op, tipos, nome_cedente=cedente)
        laudo["pendencias"] += r_docs["pendencias"]
        laudo["observacoes"] += r_docs.get("observacoes", [])
        exig = ", ".join(checagem_docs._ROTULO[e] for e in r_docs["exigidos"])
        print(f"  [docs] exigidos: {exig}")
        for canon, info in r_docs["encontrados"].items():
            print(f"         {checagem_docs._ROTULO[canon]:<18} {info['assinados']}/{info['total']} assinado(s)")
        for obs in r_docs.get("observacoes", []):
            print(f"         * {obs}")
        print(f"  [docs] {'OK' if r_docs['ok'] else 'PENDENCIAS: ' + str(len(r_docs['pendencias']))}")
        # guarda o que foi conferido: e o MOTIVO que vai no aviso de finalizacao
        laudo["detalhes"] = {"exigidos": r_docs["exigidos"],
                             "encontrados": r_docs["encontrados"],
                             "observacoes": r_docs.get("observacoes", []),
                             "tipos_titulos": laudo["tipos"],
                             "linhas_pagamento": []}
    except Exception as e:
        laudo["erro"] = f"checagem de documentos falhou: {str(e)[:140]}"
        print(f"  [docs] ERRO: {laudo['erro']}")
        return laudo   # sem os documentos conferidos NAO se finaliza nada

    # ---- PORTAO: pagamento so depois das assinaturas ---------------------- #
    # Enquanto os documentos nao estao assinados, o cadastro de pagamento ainda
    # esta sendo montado - conferir agora so geraria ruido. A op volta no proximo
    # ciclo e ai o pagamento e conferido.
    if laudo["pendencias"] and cfg.PAGAMENTO_SO_APOS_ASSINATURAS:
        print("\n  >> NAO FINALIZA - documentos pendentes; o pagamento sera conferido "
              "quando as assinaturas estiverem ok:")
        for p in laudo["pendencias"]:
            print(f"     - {p}")
        laudo["acao"] = "avisar"
        laudo["pagamento_conferido"] = False
        if mandar_email:
            ok, motivo = notificar.enviar(
                op, cedente, laudo["pendencias"],
                {"valor": _fmt_valor(valor), "tipos_titulos": laudo["tipos"]})
            print(f"     e-mail: {'enviado' if ok else 'nao enviado'} ({motivo})")
            laudo["acao"] = "avisado" if ok else "avisar"
        else:
            print("     (e-mail NAO enviado - rode com --email para avisar de verdade)")
        return laudo

    # ---- CHECAGEM 2: forma de pagamento ---------------------------------- #
    # A MESMA pagina serve p/ conferir e p/ finalizar: abrir outra e re-navegar
    # e o que pendurava (Page.goto de 45s, 3x) logo depois da grade.
    laudo["pagamento_conferido"] = True
    pg = ctx.new_page()
    modo = {"aceitar": False, "dialogos": []}

    def _dialogo(d):
        # durante a LEITURA nada e confirmado; no clique de Finalizar, sim.
        modo["dialogos"].append(f"{d.type}: {d.message.strip()[:200]}")
        try:
            d.accept() if modo["aceitar"] else d.dismiss()
        except Exception:
            pass

    pg.on("dialog", _dialogo)
    try:
        r_pag = checagem_pagamento.conferir(pg, op, log=lambda m: print("  " + str(m)))
        laudo["pendencias"] += r_pag["pendencias"]
        laudo.setdefault("detalhes", {})["linhas_pagamento"] = r_pag["linhas"]
        for linha in r_pag["linhas"]:
            print(f"  [pag]  linha {linha['_linha']}: Tipo={linha.get('tipo')} | "
                  f"origem={linha.get('cta_origem')} | favorecido={linha.get('favorecido')} | "
                  f"venc={linha.get('vencto')} | SP={linha.get('sp')}")
        print(f"  [pag]  {'OK' if r_pag['ok'] else 'PENDENCIAS: ' + str(len(r_pag['pendencias']))}")

        # ---- DECISAO ------------------------------------------------------ #
        if laudo["pendencias"]:
            print(f"\n  >> NAO FINALIZA - {len(laudo['pendencias'])} pendencia(s):")
            for p in laudo["pendencias"]:
                print(f"     - {p}")
            laudo["acao"] = "avisar"
            if mandar_email:
                ok, motivo = notificar.enviar(
                    op, cedente, laudo["pendencias"],
                    {"valor": _fmt_valor(valor), "tipos_titulos": laudo["tipos"]})
                print(f"     e-mail: {'enviado' if ok else 'nao enviado'} ({motivo})")
                laudo["acao"] = "avisado" if ok else "avisar"
            else:
                print("     (e-mail NAO enviado - rode com --email para avisar de verdade)")
            return laudo

        print("\n  >> TUDO OK - a operacao pode ser finalizada")
        if not executar:
            laudo["acao"] = "finalizaria (DRY)"
            print("     [DRY] NAO clicou em Finalizar. Use --executar para valer.")
            return laudo

        # FINALIZA na MESMA pagina (sem re-navegar) e liga o aceite de dialogos
        def _ligar_aceite(_dialogos):
            modo["aceitar"] = True

        r_fin = fin.finalizar_da_grade(pg, op, aceitar_dialogos=_ligar_aceite,
                                       log=lambda m: print("  " + str(m)))
        r_fin["dialogos"] = modo["dialogos"] or r_fin.get("dialogos", [])
        if r_fin["ok"]:
            laudo["acao"] = "finalizada"
        elif r_fin["situacao"] == "dry":
            # R7_DRY_RUN=1 barrou o clique dentro do finalizar_da_grade: nao e falha,
            # e o mesmo veredito do caminho `not executar` acima.
            laudo["acao"] = "finalizaria (DRY)"
        elif r_fin["situacao"] == "finalizada_por_outro":
            # nao e falha: o operador chegou primeiro. Nao avisamos por WhatsApp
            # porque nao fomos nos que finalizamos.
            laudo["acao"] = "finalizada pelo operador (durante a checagem)"
        else:
            laudo["acao"] = f"falha ao finalizar ({r_fin['situacao']})"
        print(f"     >> {laudo['acao']}: {r_fin['detalhe']}")
        for d in r_fin["dialogos"]:
            print(f"        [dialogo] {d}")
        if r_fin["ok"]:
            _registrar_finalizada(op, cedente)
            _avisar_finalizacao(op, cedente, valor, laudo.get("detalhes"), r_fin["detalhe"])
        return laudo
    except Exception as e:
        laudo["erro"] = f"checagem/finalizacao de pagamento falhou: {str(e)[:140]}"
        print(f"  [pag]  ERRO: {laudo['erro']}")
        return laudo
    finally:
        # sai da tela ANTES de fechar: cancela requests pendentes da grade, que
        # e o que deixava a proxima navegacao pendurada.
        try:
            pg.goto("about:blank", timeout=8_000)
        except Exception:
            pass
        try:
            pg.close()
        except Exception:
            pass


def _avisar_finalizacao(op, cedente, valor, detalhes, confirmacao):
    """Avisa por e-mail E por WhatsApp que a op foi finalizada, com o motivo.
    Best-effort: falha de aviso NAO desfaz nem mascara a finalizacao."""
    ctx = {"valor": _fmt_valor(valor), "confirmacao": confirmacao}
    try:
        ok, motivo = notificar.enviar_finalizada(op, cedente, ctx, detalhes)
        print(f"     e-mail de finalizacao: {'enviado' if ok else 'nao enviado'} ({motivo})")
    except Exception as e:
        print(f"     e-mail de finalizacao FALHOU: {str(e)[:120]}")
    try:
        texto = notificar.texto_whatsapp_finalizada(op, cedente, ctx, detalhes)
        n, res = notificar_whatsapp.enviar(texto)
        for numero, ok, detalhe in res:
            print(f"     whatsapp {numero}: {'OK' if ok else 'FALHOU'} - {detalhe}")
    except Exception as e:
        print(f"     whatsapp FALHOU: {str(e)[:120]}")


def ciclo(ctx, ops=None, executar=False, mandar_email=False):
    if ops is None:
        print(f"=== fila: etapa '{cfg.ROTULO_ETAPA_ENTRADA}' ===")
        ops = listar_fila.listar(ctx)
    if not ops:
        print("  (nenhuma operacao na fila)")
        return []
    print(f"  {len(ops)} operacao(oes): {', '.join(str(o) for o in ops)}")
    # SSO do doc2you UMA vez por ciclo: a sessao vale p/ todas as ops e um SSO
    # que falha no meio derruba a checagem de documentos da op da vez.
    if not checagem_docs.sso_doc2you(ctx):
        print("  [!] SSO do doc2you falhou - as checagens de documento vao tentar de novo por op")
    laudos = []
    for op in ops:
        try:
            laudos.append(processar(ctx, op, executar, mandar_email))
        except Exception as e:
            # uma op problematica nao pode derrubar o ciclo
            print(f"\n  [op {op}] ERRO INESPERADO (ignorado, segue): {e}")
            traceback.print_exc()
            laudos.append({"op": str(op), "erro": str(e)[:140], "pendencias": [],
                           "acao": "erro", "cedente": None, "tipos": []})
    return laudos


def _resumo(laudos, executar):
    print(f"\n\n{'#' * 66}\n  RESUMO ({len(laudos)} operacao(oes))\n{'#' * 66}")
    for l in laudos:
        if l.get("erro"):
            estado = f"ERRO - {l['erro']}"
        elif l["pendencias"]:
            estado = f"BARRADA ({len(l['pendencias'])} pendencia(s))"
            if l.get("pagamento_conferido") is False:
                estado += " [pagamento ainda nao conferido]"
        elif executar and l.get("acao"):
            # em modo EXECUTAR o resumo tem de mostrar o que ACONTECEU, nao
            # "PASSARIA" - senao uma falha de clique passa despercebida.
            estado = "FINALIZADA" if l["acao"] == "finalizada" else l["acao"].upper()
        else:
            estado = "PASSARIA"
        print(f"  op {l['op']}  {str(l.get('cedente') or '')[:34]:<34} {estado}")
        for p in l["pendencias"]:
            print(f"       - {p}")
    print("#" * 66)


def main():
    ap = argparse.ArgumentParser(description="Robo 7 - confere e finaliza operacoes.")
    ap.add_argument("--cdp", action="store_true",
                    help=f"anexa num Chrome ja aberto em {cfg.CDP_URL} (desenvolvimento "
                         "pelo VNC) em vez de subir o proprio e logar")
    ap.add_argument("--ops", default="", help="ops especificas (virgula). Vazio = fila da etapa")
    ap.add_argument("--executar", action="store_true",
                    help="clica em Finalizar de verdade (sem isso = DRY)")
    ap.add_argument("--email", action="store_true",
                    help="manda o e-mail de pendencia (sem isso, so mostra)")
    ap.add_argument("--loop", action="store_true", help="repete a cada R7_INTERVALO_CICLO_S")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    executar = args.executar and not cfg.DRY_RUN
    if args.executar and cfg.DRY_RUN:
        print("[!] R7_DRY_RUN=1 no ambiente -> --executar IGNORADO (nada sera finalizado).\n"
              "    Para valer: $env:R7_DRY_RUN='0' antes de rodar.")
    modo = "EXECUTAR (finaliza de verdade)" if executar else "DRY (nao finaliza nada)"
    print(f"=== ROBO 7 | {modo} | e-mail: {'SIM' if args.email else 'nao'} | "
          f"conta: {cfg.CONTA} ===")

    ops = [o.strip() for o in args.ops.split(",") if o.strip()] or None

    # Sessao pelo modulo comum (o mesmo do robo_pagamento): sobe o Chrome no
    # display/perfil/porta PROPRIOS e loga via CapSolver com a credencial DESTE
    # robo (cfg.EMAIL/SENHA). Ate 21/09/2026 o main so anexava num Chrome ja
    # aberto (connect_over_cdp); no container ninguem o abria, e a 1a rodada em
    # producao morreu com "CDP 9228 nao responde" antes de logar.
    from playwright.sync_api import sync_playwright
    from src.common.clients import smart_sessao
    with sync_playwright() as p:
        try:
            with smart_sessao.sessao(p, cfg, usar_cdp=args.cdp, log=print) as ctx:
                while True:
                    laudos = ciclo(ctx, ops, executar, args.email)
                    _resumo(laudos, executar)
                    if not args.loop:
                        break
                    print(f"\n  ... proximo ciclo em {cfg.INTERVALO_CICLO_S}s\n")
                    time.sleep(cfg.INTERVALO_CICLO_S)
        except (smart_sessao.SemNavegador, smart_sessao.SemSessao,
                smart_sessao.SmartIndisponivel) as e:
            print(f"[ERRO] sessao do Smart: {e}")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
