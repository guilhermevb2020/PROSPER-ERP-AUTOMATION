# -*- coding: utf-8 -*-
"""
finalizar.py - A ACAO do Robo 7: clicar em FINALIZAR na tela de Resumir.

Caminho (mapeado ao vivo em 28/08/2026):
  novatelaoperacao.php?action=edit&op=<op>
    -> #invocarResumirOperacao              (painel "Resumir")
       -> #pagamento  <button>Finalizar</button>  onclick="validaCalculoOperacao(this, <op>)"

O botao SO EXISTE enquanto a operacao nao foi finalizada - numa operacao ja
concluida ele simplesmente nao e renderizado (foi assim que se descobriu que as
ops 64887/64882 ja tinham sido finalizadas pelo operador). Por isso "botao
ausente" e tratado como JA_FINALIZADA, nao como erro.

Travas que o proprio Smart aplica ao clicar (do JS da tela):
  - verificacriticasfinalizar.php -> alert se houver criticas
  - #edicaoPermissaoFO = 0        -> "usuario nao possui privilegios para finalizar"
  - #fechamentoContabil = 1       -> bloqueia pelo fechamento contabil
  - saldo != 0 sem #cbCC          -> "Informe uma opcao para o saldo!"
Qualquer alert desses e CAPTURADO e devolvido como motivo da falha.

DRY-RUN por padrao (cfg.DRY_RUN): diz o que faria e NAO clica.
"""
import os
import sys
import time

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import r7_config as cfg                                    # noqa: E402
from mapear_pagamento import _frame_com, _ir_para_operacao  # noqa: E402

SEL_FINALIZAR = "#pagamento"


def _abrir_resumir(pg, op, log=print):
    """Abre a tela de Resumir da operacao. Retorna o frame ou None."""
    if not _ir_para_operacao(pg, op, log=log):
        return None
    fr = _frame_com(pg, "#invocarResumirOperacao", timeout_s=10)
    if fr is None:
        return None
    fr.locator("#invocarResumirOperacao").click(timeout=15_000)
    # o resumir esta carregado quando os botoes dele aparecem
    return _frame_com(pg, "#btnPagamento", timeout_s=30)


def estado(pg, op, log=print):
    """Diz se a operacao pode ser finalizada AGORA, sem clicar em nada.
    Retorna (situacao, detalhe): 'pronta' | 'ja_finalizada' | 'botao_desabilitado'
    | 'sem_privilegio' | 'fechamento_contabil' | 'inacessivel'."""
    fr = _abrir_resumir(pg, op, log=log)
    if fr is None:
        return "inacessivel", ("nao consegui abrir o Resumir (op aberta por outro "
                               "usuario? sessao caiu?)")
    info = fr.evaluate("""() => {
        const b = document.querySelector('#pagamento');
        const v = n => { const e = document.querySelector('#' + n); return e ? e.value : null; };
        return { tem: !!b, dis: b ? !!b.disabled : null,
                 txt: b ? (b.innerText || '').trim() : null,
                 permissao: v('edicaoPermissaoFO'), fechamento: v('fechamentoContabil'),
                 anofechado: v('anofechado') };
    }""")
    if not info["tem"]:
        return "ja_finalizada", "o botao Finalizar nao existe nesta tela"
    if info["permissao"] == "0":
        return "sem_privilegio", "o usuario da sessao nao pode finalizar operacoes"
    if info["fechamento"] == "1":
        return "fechamento_contabil", f"fechamento contabil do ano {info['anofechado']}"
    if info["dis"]:
        return "botao_desabilitado", "o botao Finalizar esta desabilitado"
    return "pronta", f"botao '{info['txt']}' habilitado"


def finalizar(pg, op, dry=None, log=print):
    """Clica em Finalizar. Retorna dict com 'ok', 'situacao', 'detalhe', 'dialogos'.

    dry=None usa cfg.DRY_RUN (padrao: True = nao clica).
    """
    dry = cfg.DRY_RUN if dry is None else dry
    op = str(op)
    dialogos = []

    fr = _abrir_resumir(pg, op, log=log)
    if fr is None:
        return {"ok": False, "situacao": "inacessivel", "dialogos": [],
                "detalhe": "nao consegui abrir o Resumir da op " + op}

    botao = fr.locator(SEL_FINALIZAR)
    if not botao.count():
        return {"ok": False, "situacao": "ja_finalizada", "dialogos": [],
                "detalhe": "o botao Finalizar nao existe (operacao ja finalizada?)"}
    if botao.is_disabled():
        return {"ok": False, "situacao": "botao_desabilitado", "dialogos": [],
                "detalhe": "o botao Finalizar esta desabilitado"}

    if dry:
        return {"ok": False, "situacao": "dry", "dialogos": [],
                "detalhe": f"DRY-RUN: clicaria em Finalizar da op {op} (botao habilitado)"}

    # A PARTIR DAQUI A ACAO E REAL. Os alerts do Smart (criticas, privilegio,
    # fechamento contabil, saldo) precisam ser ACEITOS p/ o fluxo seguir, e o
    # texto deles e o motivo da eventual recusa - por isso sao capturados.
    def _dialogo(d):
        dialogos.append(f"{d.type}: {d.message.strip()[:200]}")
        try:
            d.accept()
        except Exception:
            pass

    pg.on("dialog", _dialogo)
    log(f"  [finalizar] op {op}: clicando em Finalizar...")
    try:
        botao.click(timeout=20_000)
    except Exception as e:
        return {"ok": False, "situacao": "erro_clique", "dialogos": dialogos,
                "detalhe": f"falha ao clicar: {str(e)[:120]}"}

    time.sleep(12)   # "Finalizando operacao..." + gravacao no servidor

    # VERIFICA de verdade: reabre o Resumir; se a op finalizou, o botao some.
    situacao, detalhe = estado(pg, op, log=log)
    if situacao == "ja_finalizada":
        return {"ok": True, "situacao": "finalizada", "dialogos": dialogos,
                "detalhe": "confirmado: o botao Finalizar sumiu da tela"}
    return {"ok": False, "situacao": "nao_confirmou", "dialogos": dialogos,
            "detalhe": f"apos o clique a op continua '{situacao}' ({detalhe})"}


def confirmar_no_banco(op, tentativas=6, espera=10):
    """Confirma no espelho do Postgres que a op ficou CONCLUIDA.

    E a confirmacao mais confiavel que existe aqui: nao depende de reabrir tela
    nenhuma (foi justamente a re-navegacao que penduraava). O espelho atualiza
    em segundos, entao algumas tentativas bastam.
    """
    import time as _t
    try:
        import psycopg2
        import config as r1_config
    except Exception as e:
        return None, f"sem acesso ao banco: {str(e)[:60]}"
    for i in range(tentativas):
        try:
            conn = psycopg2.connect(connect_timeout=8, **r1_config.DB_CONFIG)
            try:
                cur = conn.cursor()
                cur.execute("SELECT etapa, flag_operacao_concluida FROM trs.operacao_desagio "
                            "WHERE id_operacao = %s", (int(op),))
                r = cur.fetchone()
            finally:
                conn.close()
            if r and (r[1] or str(r[0]).upper() == "CONCLUIDA"):
                return True, f"banco confirma: etapa={r[0]}"
            ultimo = f"etapa={r[0] if r else '?'}"
        except Exception as e:
            ultimo = f"erro: {str(e)[:60]}"
        if i < tentativas - 1:
            _t.sleep(espera)
    return False, f"banco ainda nao confirmou ({ultimo})"


def finalizar_da_grade(pg, op, aceitar_dialogos=None, log=print):
    """FINALIZA a partir da pagina que JA esta na grade de pagamento.

    Por que existe: o finalizar() abre uma pagina nova e re-navega ate a
    operacao. Logo depois da checagem de pagamento essa segunda navegacao
    PENDURA (Page.goto estoura 45s, 3x) - foi o que travou a 1a finalizacao real
    (op 64997, 01/09/2026). Aqui nao ha goto nenhum: usamos o botao "Sair" da
    propria grade (#btConfirmar2, que faz document.location p/ novoresumir.php)
    e clicamos o #pagamento que aparece la.

    aceitar_dialogos: callable p/ ligar o modo "aceitar" no handler de dialog da
    pagina (o clique de finalizar precisa CONFIRMAR os alerts do Smart).
    """
    op = str(op)
    dialogos = []

    grade = _frame_com(pg, "#btConfirmar2", timeout_s=15)
    if grade is None:
        return {"ok": False, "situacao": "sem_grade", "dialogos": [],
                "detalhe": "a pagina nao esta na grade de pagamento"}
    try:
        grade.locator("#btConfirmar2").click(timeout=15_000)   # Sair -> novoresumir
    except Exception as e:
        return {"ok": False, "situacao": "erro_sair", "dialogos": [],
                "detalhe": f"falha ao sair da grade: {str(e)[:110]}"}

    fr = _frame_com(pg, SEL_FINALIZAR, timeout_s=40)
    if fr is None:
        # Botao ausente tem DOIS significados muito diferentes: ou alguem
        # finalizou a op enquanto conferiamos (comum - a checagem leva ~1min e o
        # operador trabalha na mesma fila), ou a tela nao carregou. Chutar
        # "ja_finalizada" mascararia o segundo caso, entao perguntamos ao Smart.
        ja, detalhe = _confirmar_no_smart(pg, op)
        if ja:
            return {"ok": False, "situacao": "finalizada_por_outro", "dialogos": [],
                    "detalhe": "a operacao ja estava finalizada quando fomos clicar "
                               "(provavelmente o operador finalizou durante a checagem)"}
        return {"ok": False, "situacao": "botao_nao_apareceu", "dialogos": [],
                "detalhe": f"o botao Finalizar nao apareceu no Resumir e o Smart "
                           f"diz que a op NAO esta finalizada ({detalhe})"}
    botao = fr.locator(SEL_FINALIZAR)
    if botao.is_disabled():
        return {"ok": False, "situacao": "botao_desabilitado", "dialogos": [],
                "detalhe": "o botao Finalizar esta desabilitado"}

    # Trava do AMBIENTE, no ponto do clique: R7_DRY_RUN=1 impede a finalizacao por
    # qualquer caminho - inclusive quem chama esta funcao direto com executar=True
    # (finalizar_op_executar.py --confirmar). Ate 21/09/2026 a trava vivia so no
    # main() do finalizar_operacao, e esse caminho passava por cima dela. Fica DEPOIS
    # das checagens do botao de proposito: o DRY continua dizendo se clicaria.
    if cfg.DRY_RUN:
        return {"ok": False, "situacao": "dry", "dialogos": [],
                "detalhe": f"DRY-RUN (R7_DRY_RUN=1): clicaria em Finalizar da op {op} "
                           "(botao habilitado); nada foi clicado"}

    if aceitar_dialogos:
        aceitar_dialogos(dialogos)      # a partir daqui os alerts sao ACEITOS
    log(f"  [finalizar] op {op}: clicando em Finalizar (sem re-navegar)...")
    try:
        botao.click(timeout=20_000)
    except Exception as e:
        return {"ok": False, "situacao": "erro_clique", "dialogos": dialogos,
                "detalhe": f"falha ao clicar: {str(e)[:120]}"}

    time.sleep(12)                       # "Finalizando operacao..." + gravacao

    # CONFIRMACAO. A fonte da verdade e o SMART, nao o banco: o espelho do
    # Postgres NAO e instantaneo e deu falso negativo na 1a finalizacao real
    # (op 64997, 01/09/2026 - finalizou, o robo disse que falhou e por isso nem
    # avisou). O banco fica so como ultimo recurso.
    ok_smart, detalhe_smart = _confirmar_no_smart(pg, op)
    if ok_smart:
        return {"ok": True, "situacao": "finalizada", "dialogos": dialogos,
                "detalhe": f"Smart confirma: {detalhe_smart}"}

    sumiu = False
    try:
        sumiu = not any(f.locator(SEL_FINALIZAR).count() for f in pg.frames)
    except Exception:
        pass
    if ok_smart is None and sumiu:
        return {"ok": True, "situacao": "finalizada", "dialogos": dialogos,
                "detalhe": f"o botao Finalizar sumiu da tela ({detalhe_smart})"}

    ok_banco, detalhe_banco = confirmar_no_banco(op, tentativas=3, espera=8)
    if ok_banco:
        return {"ok": True, "situacao": "finalizada", "dialogos": dialogos,
                "detalhe": detalhe_banco}
    return {"ok": False, "situacao": "nao_confirmou", "dialogos": dialogos,
            "detalhe": f"{detalhe_smart} | {detalhe_banco}"}


def _confirmar_no_smart(pg, op):
    """Pergunta ao Smart se a op finalizou. -> (True/False/None, detalhe)."""
    try:
        import estado_no_smart
        from smart_session import Smart
        return estado_no_smart.finalizada(Smart.attach(pg.context), op)
    except Exception as e:
        return None, f"nao consegui conferir no Smart: {str(e)[:100]}"


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Finaliza uma operacao (DRY por padrao).")
    ap.add_argument("--op", required=True)
    ap.add_argument("--cdp", default=str(cfg.CDP_PORT))
    ap.add_argument("--executar", action="store_true",
                    help="clica de verdade (sem isso = DRY, so diz o que faria)")
    ap.add_argument("--estado", action="store_true", help="so consulta o estado, nao clica")
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
        if not args.executar:
            pg.on("dialog", lambda d: d.dismiss())   # em DRY nada e confirmado
        try:
            if args.estado:
                situacao, detalhe = estado(pg, args.op)
                print(f"\n>> op {args.op}: {situacao} - {detalhe}")
                return 0
            r = finalizar(pg, args.op, dry=not args.executar)
        finally:
            try:
                pg.close()
            except Exception:
                pass

    print(f"\n>> op {args.op}: {r['situacao']} | ok={r['ok']}")
    print(f"   {r['detalhe']}")
    for d in r["dialogos"]:
        print(f"   [dialogo] {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
