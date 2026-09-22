# -*- coding: utf-8 -*-
"""
finalizar_operacao.py - ORQUESTRADOR do Robo 7.

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
  python finalizar_operacao/finalizar_operacao.py                    # DRY, sem e-mail
  python finalizar_operacao/finalizar_operacao.py --ops 64886,64890  # ops especificas
  python finalizar_operacao/finalizar_operacao.py --email            # DRY + manda o e-mail
  python finalizar_operacao/finalizar_operacao.py --executar --email # PRODUCAO
  python finalizar_operacao/finalizar_operacao.py --loop             # ciclo continuo
"""
import argparse
import csv
import os
import re
import sys
import time
import traceback
from datetime import datetime
from html import unescape

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(_AQUI)
for _p in (_AQUI, os.path.join(_RAIZ, "operacoes"), os.path.join(_RAIZ, "credito")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import checagem_docs                 # noqa: E402
import checagem_pagamento            # noqa: E402
import finalizar as fin              # noqa: E402
import listar_fila                   # noqa: E402
import notificar                     # noqa: E402
import notificar_whatsapp            # noqa: E402
import r7_config as cfg              # noqa: E402
from src.common.clients import execucao_job  # noqa: E402  (PYTHONPATH=/app, como o smart_sessao)


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


# Etapa ATUAL da operacao: a opcao marcada no <select id=etapaOperacao> da tela de
# edicao (novatelaoperacao.php), a mesma que o _dados_da_operacao ja baixa por HTTP.
# Medido em 22/09/2026 (op 65879): o select vem no HTML com 9 opcoes e a marcada e a
# etapa ("Aguardando Ass.", value 15). Pelo DOM NAO serve depois da grade: o form mora
# no frame 'stage', e o Resumir e a grade de pagamento abrem nesse MESMO frame.
_RE_SELECT_ETAPA = re.compile(
    r"<select\b[^>]*\bid\s*=\s*[\"']etapaOperacao[\"'][^>]*>(.*?)</select>", re.S | re.I)
_RE_OPCAO_MARCADA = re.compile(r"<option\b[^>]*\bselected\b[^>]*>([^<]*)", re.I)


def _etapa_do_html(html):
    """Rotulo da opcao marcada no select de etapa. None se o select nao estiver no
    HTML ou se nao houver exatamente UMA opcao marcada (ai nao da para afirmar)."""
    m = _RE_SELECT_ETAPA.search(html or "")
    if not m:
        return None
    marcadas = _RE_OPCAO_MARCADA.findall(m.group(1))
    if len(marcadas) != 1:
        return None
    return unescape(marcadas[0]).strip() or None


def _etapa_da_operacao(ctx, op):
    """Etapa da operacao lida no Smart, por HTTP, na hora. None = nao deu para ler
    (e quem chama trata None como "nao esta na etapa": a porta fecha)."""
    try:
        import classe_risco_tool as crt
        from smart_session import Smart
        st, html = Smart.attach(ctx).get(crt.URL_EDIT.format(op=op), timeout=60_000)
    except Exception:
        return None
    if st != 200:
        return None
    return _etapa_do_html(html)


def _norm_etapa(texto):
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in t if c.isalnum()).lower()


def _mesma_etapa(lida, esperada):
    """'Aguardando Ass.' == 'AGUARDANDO ASS' == ' aguardando  ass. '; None nunca casa."""
    return lida is not None and _norm_etapa(lida) != "" and _norm_etapa(lida) == _norm_etapa(esperada)


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


def processar(ctx, op, executar=False, mandar_email=False, execucao=None):
    """Roda as duas checagens numa op e decide. Retorna dict com o laudo."""
    op = str(op)
    laudo = {"op": op, "pendencias": [], "observacoes": [], "acao": None,
             "cedente": None, "tipos": [], "erro": None}
    print(f"\n{'=' * 66}\n  OPERACAO {op}\n{'=' * 66}")

    tipos, cedente, valor = _dados_da_operacao(ctx, op)
    laudo["tipos"], laudo["cedente"] = sorted(set(t for t in tipos if t)), cedente
    laudo["valor"] = valor
    print(f"  cedente: {cedente or '(nao identificado)'} | titulos: {laudo['tipos'] or '(nao lidos)'}")

    # ---- TITULOS: sem os tipos, nao ha como saber o que exigir ------------- #
    # documentos_exigidos([]) pede so Aditivo + Nota promissoria: Duplicata e Letra
    # de cambio dependem do tipo dos titulos. Titulo nao lido deixaria passar uma
    # operacao com duplicatas SEM assinatura - com o clique ligado (22/09/2026),
    # conferir menos vira finalizar indevidamente. Nao lido = nao confere nem clica.
    if not laudo["tipos"]:
        laudo["erro"] = ("nao li os tipos dos titulos na tela da operacao; sem eles nao "
                         "sei se Duplicata/Letra de cambio sao exigidas")
        print(f"  [docs] ERRO: {laudo['erro']}")
        return laudo

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

    # ---- ETAPA: so finaliza quem esta MESMO na etapa de entrada ----------- #
    # A fila vem da consulta do Smart, que le a tabela 1,5 s depois de Pesquisar.
    # Quando o Smart demora, ela le a tabela que ja estava na tela: as ~10
    # operacoes mais recentes, das duas securitizadoras e de qualquer etapa
    # (medido 3x em 22/09/2026: 11:00, 14:30 e 15:00). Com o clique ligado, isso
    # punha ao alcance do Finalizar uma operacao que o operador tirou da etapa de
    # proposito. A etapa e lida no Smart ANTES de abrir a grade; se nao for a de
    # entrada, ou nao der para ler, nao finaliza.
    etapa = _etapa_da_operacao(ctx, op)
    laudo["etapa"] = etapa
    print(f"  [etapa] {etapa if etapa is not None else 'NAO consegui ler a etapa da operacao no Smart'}")
    if not _mesma_etapa(etapa, cfg.ROTULO_ETAPA_ENTRADA):
        motivo = (f"Etapa: a operacao esta em '{etapa}', nao em '{cfg.ROTULO_ETAPA_ENTRADA}'"
                  if etapa is not None else
                  "Etapa: nao consegui ler a etapa da operacao no Smart")
        laudo["pendencias"].append(f"{motivo} - o robo so finaliza na etapa de entrada")
        laudo["acao"] = "fora da etapa (nao finaliza)"
        laudo["pagamento_conferido"] = False
        print(f"\n  >> NAO FINALIZA - {motivo}")
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

        # LIMITE DE HORA, antes de registrar a intencao de clique: depois de
        # R7_HORA_LIMITE_FINALIZAR (18:30) a operacao passa, mas fica para o primeiro
        # ciclo de amanha - a remessa de pagamento exige vencimento = hoje. A mesma
        # trava vive dentro do finalizar_da_grade(), para os outros caminhos.
        dentro, motivo_janela = cfg.dentro_da_janela_de_finalizacao()
        if not dentro:
            laudo["acao"] = "finalizaria (fora da janela de horario)"
            print(f"     [janela] NAO clicou em Finalizar: {motivo_janela}")
            return laudo

        # FINALIZA na MESMA pagina (sem re-navegar) e liga o aceite de dialogos
        def _ligar_aceite(_dialogos):
            modo["aceitar"] = True

        if execucao is not None:
            execucao_job.registrar_evento_operacao(
                execucao, op, "finalizar_clicado", cedente=cedente, valor_liquido=valor,
                detalhe={"tipos_titulos": laudo["tipos"]})
        r_fin = fin.finalizar_da_grade(pg, op, aceitar_dialogos=_ligar_aceite,
                                       log=lambda m: print("  " + str(m)))
        r_fin["dialogos"] = modo["dialogos"] or r_fin.get("dialogos", [])
        if r_fin["ok"]:
            laudo["acao"] = "finalizada"
        elif r_fin["situacao"] == "dry":
            # R7_DRY_RUN=1 barrou o clique dentro do finalizar_da_grade: nao e falha,
            # e o mesmo veredito do caminho `not executar` acima.
            laudo["acao"] = "finalizaria (DRY)"
        elif r_fin["situacao"] == "fora_da_janela":
            # o relogio cruzou o limite entre a checagem acima e o clique: nao e falha
            laudo["acao"] = "finalizaria (fora da janela de horario)"
        elif r_fin["situacao"] == "finalizada_por_outro":
            # nao e falha: o operador chegou primeiro. Nao avisamos por WhatsApp
            # porque nao fomos nos que finalizamos.
            laudo["acao"] = "finalizada pelo operador (durante a checagem)"
        else:
            laudo["acao"] = f"falha ao finalizar ({r_fin['situacao']})"
        print(f"     >> {laudo['acao']}: {r_fin['detalhe']}")
        if execucao is not None and r_fin["situacao"] != "dry":
            _tipo = {"finalizada": "finalizada",
                     "finalizada_por_outro": "finalizada_por_outro"}.get(
                r_fin["situacao"], "finalizacao_falhou")
            execucao_job.registrar_evento_operacao(
                execucao, op, _tipo, resultado=r_fin["situacao"], cedente=cedente,
                valor_liquido=valor,
                detalhe={"detalhe": r_fin["detalhe"], "dialogos": r_fin["dialogos"]})
        for d in r_fin["dialogos"]:
            print(f"        [dialogo] {d}")
        if r_fin["ok"]:
            _registrar_finalizada(op, cedente)
            _avisar_finalizacao(op, cedente, valor, laudo.get("detalhes"), r_fin["detalhe"],
                                execucao=execucao)
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


def _avisar_finalizacao(op, cedente, valor, detalhes, confirmacao, execucao=None):
    """Avisa por e-mail E por WhatsApp que a op foi finalizada, com o motivo.
    Best-effort: falha de aviso NAO desfaz nem mascara a finalizacao."""
    ctx = {"valor": _fmt_valor(valor), "confirmacao": confirmacao}
    try:
        ok, motivo = notificar.enviar_finalizada(op, cedente, ctx, detalhes)
        print(f"     e-mail de finalizacao: {'enviado' if ok else 'nao enviado'} ({motivo})")
    except Exception as e:
        print(f"     e-mail de finalizacao FALHOU: {str(e)[:120]}")
    res = []
    try:
        texto = notificar.texto_whatsapp_finalizada(op, cedente, ctx, detalhes)
        n, res = notificar_whatsapp.enviar(texto)
        for numero, ok, detalhe in res:
            print(f"     whatsapp {numero}: {'OK' if ok else 'FALHOU'} - {detalhe}")
    except Exception as e:
        print(f"     whatsapp FALHOU: {str(e)[:120]}")
    if execucao is not None:
        # best-effort como o aviso: registrar o aviso nunca desfaz a finalizacao
        try:
            execucao_job.registrar_evento_operacao(
                execucao, op, "aviso_enviado",
                resultado="ok" if res and all(ok for _, ok, _ in res) else "falhou",
                cedente=cedente, valor_liquido=valor,
                detalhe={"whatsapp": [{"numero": str(n_), "ok": bool(ok), "detalhe": str(d)[:200]}
                                      for n_, ok, d in res]})
        except Exception as e:  # noqa: BLE001
            print(f"     registro do aviso FALHOU: {str(e)[:120]}")


def _veredito(laudo):
    if laudo.get("erro"):
        return "ERRO"
    return "BARRADA" if laudo.get("pendencias") else "FINALIZARIA"


def _registrar_avaliacao(execucao, laudo):
    """O laudo de processar() vira o evento 'avaliada' - o placar mora no banco."""
    if execucao is None:
        return
    detalhes = laudo.get("detalhes") or {}
    execucao_job.registrar_evento_operacao(
        execucao, laudo["op"], "avaliada", resultado=_veredito(laudo),
        cedente=laudo.get("cedente"), valor_liquido=laudo.get("valor"),
        pendencias=laudo.get("pendencias") or [],
        detalhe={"acao": laudo.get("acao"), "erro": laudo.get("erro"),
                 "tipos_titulos": laudo.get("tipos"),
                 "pagamento_conferido": laudo.get("pagamento_conferido"),
                 "etapa": laudo.get("etapa"),
                 "observacoes": laudo.get("observacoes"),
                 "exigidos": detalhes.get("exigidos")},
        linhas_pagamento=detalhes.get("linhas_pagamento") or [])


def ciclo(ctx, ops=None, executar=False, mandar_email=False, execucao=None):
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
            laudo = processar(ctx, op, executar, mandar_email, execucao=execucao)
            laudos.append(laudo)
            _registrar_avaliacao(execucao, laudo)
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

    # A execucao no banco: em ensaio, sem banco segue degradada (avisa e nao registra);
    # em modo real e OBRIGATORIA - sem registro nao ha clique.
    try:
        execucao = execucao_job.abrir_execucao(
            "finalizar_operacao", "finalizar_operacao_aguardando_assinatura",
            flag_ensaio=not executar, obrigatoria=executar,
            apelido_credencial=os.environ.get("SMART_SENHA"),
            detalhe={"ops": ops, "loop": bool(args.loop), "email": bool(args.email)})
    except execucao_job.ExecucaoIndisponivel as e:
        print(f"[ERRO] {e}")
        return 2
    codigo, total = 2, 0

    # Sessao pelo modulo comum (o mesmo do remessa_pagamento): sobe o Chrome no
    # display/perfil/porta PROPRIOS e loga via CapSolver com a credencial DESTE
    # robo (cfg.EMAIL/SENHA). Ate 21/09/2026 o main so anexava num Chrome ja
    # aberto (connect_over_cdp); no container ninguem o abria, e a 1a rodada em
    # producao morreu com "CDP 9228 nao responde" antes de logar.
    from playwright.sync_api import sync_playwright
    from src.common.clients import smart_sessao
    try:
        with sync_playwright() as p:
            try:
                with smart_sessao.sessao(p, cfg, usar_cdp=args.cdp, log=print) as ctx:
                    while True:
                        laudos = ciclo(ctx, ops, executar, args.email, execucao=execucao)
                        total += len(laudos)
                        _resumo(laudos, executar)
                        if not args.loop:
                            break
                        print(f"\n  ... proximo ciclo em {cfg.INTERVALO_CICLO_S}s\n")
                        time.sleep(cfg.INTERVALO_CICLO_S)
                codigo = 0
            except (smart_sessao.SemNavegador, smart_sessao.SemSessao,
                    smart_sessao.SmartIndisponivel) as e:
                print(f"[ERRO] sessao do Smart: {e}")
                codigo = 2
    finally:
        execucao_job.fechar_execucao(execucao, "sucesso" if codigo == 0 else "falha",
                                     codigo_saida=codigo, qtd_itens=total)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
