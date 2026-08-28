# -*- coding: utf-8 -*-
"""
gerar.py - gera a remessa de PAGAMENTO no Smart e devolve o arquivo, por HTTP.

Replica o que o navegador faz na tela "Financeiro > Sistemas de pagamento >
Pagamento BMP Money Plus > Gerar Remessa", sem abrir tela nenhuma. Todo o
contrato abaixo foi MEDIDO em 21/08/2026 contra o Smart real, pelo sandbox do
host — o HTML cru esta em `data/sandbox/robo_pagamento/debug/`.

O CICLO, e ele e curto
----------------------
    1) PESQUISA   POST pagtobmppesquisa.php -> pagtobmpgrid.php
                  (IdContaBancaria + pagtobmp=P + pesquisar=1)
                  Resposta = a grade dos pendentes.

    2) GERACAO    POST pagtobmpgrid.php com processar=1 e acao=1
                  Resposta = O PROPRIO ARQUIVO. Medido:
                      application/octet-stream
                      content-disposition: attachment; filename="CP2108000003.REM"
                  Nao ha segunda tela, nao ha download separado.

E so. Duas requisicoes.

⛔ O PERIGO DESTA TELA, E POR QUE O `acao` E CHUMBADO
----------------------------------------------------
`pagtobmpgrid.php` e O MESMO ENDPOINT para consultar e para agir, e a acao que a
tela oferece depende do STATUS que foi filtrado:

    filtro P (Pendente) -> um botao: GerarMultipag(this, 1)  "Gerar ..."
    filtro G (Gerado)   -> um botao: GerarMultipag(this, 3)  "Cancelar ..."

Mesmo form (`multipagForm`), mesmos campos, MESMOS titulos na grade. So muda um
digito. Um robo que fosse a "Gerado" atras do arquivo e submetesse o form da tela
CANCELARIA os pagamentos.

Por isso o robo NUNCA le a acao do HTML: ela e `cfg.ACAO_GERAR`, e
`analise.montar_geracao` RECUSA a montagem se a grade nao oferecer aquele botao.
A trava vive no modulo puro, e por isso tem teste.

⛔ A SEPARACAO PIX NAO E COSMETICA
---------------------------------
`checkeds` (nao-PIX) e `checkedsPIX` sao listas separadas porque decidem os LOTES
do CNAB-240. Medido no arquivo gerado: lote 0001 forma 41 (TED), lote 0002 forma
45 (PIX). Mandar tudo em `checkeds` sairia como TED — errado, e em silencio.

SEGURANCA
---------
`ciclo(dry_run=True)` vai ate montar o POST e PARA, mostrando o corpo exato. E o
padrao. Gerar remessa de pagamento MOVE DINHEIRO e nao tem desfazer.
"""
import hashlib
import os
from datetime import datetime

import analise
import pagamento_config as cfg
from src.common.clients import smart_sessao


class SessaoCaiu(Exception):
    """A sessao do Smart morreu no meio. Abortar — nunca seguir.

    Sem isto, a grade vazia viraria "nao ha pagamento pendente" e a rodada
    terminaria com cara de sucesso sem ter olhado nada. E a armadilha nº 1 deste
    ERP: deslogado, ele responde HTTP 200 com um redirect para `expira.php`.
    """


class GradeRecusada(Exception):
    """A grade nao e a de PENDENTE (ou nao tem o botao Gerar)."""


def _corpo(r):
    return r.body().decode("iso-8859-1", errors="replace")


# --------------------------------------------------------------------------- #
# 1) pesquisa
# --------------------------------------------------------------------------- #
def pesquisar_pendentes(ctx, conta=None, log=print):
    """Submete o filtro (conta + status PENDENTE) e devolve a grade lida.

    Retorna o dict de `analise.ler_grade`. Levanta SessaoCaiu se a resposta do
    Smart disser que nao ha sessao — nunca devolve "grade vazia" nesse caso.
    """
    conta = conta or cfg.CONTA
    pagina = _corpo(ctx.request.get(cfg.URL_PESQUISA, timeout=60_000))
    if smart_sessao.parece_deslogado(pagina):
        raise SessaoCaiu("a tela de pesquisa respondeu deslogado")

    formularios = [f for f in analise.analisar(pagina, cfg.URL_PESQUISA)["forms"]
                   if any(c["nome"] for c in f["campos"])]
    if not formularios:
        raise GradeRecusada("a tela de pesquisa nao trouxe formulario")

    corpo, campos = analise.montar_filtro(
        formularios[0],
        {"IdContaBancaria": conta, "pagtobmp": cfg.STATUS_PENDENTE})
    log(f"  pesquisa: conta={campos.get('IdContaBancaria')} "
        f"status={campos.get('pagtobmp')}")

    r = ctx.request.post(
        formularios[0]["action"], data=corpo,
        headers={"content-type": "application/x-www-form-urlencoded"},
        timeout=120_000)
    html = _corpo(r)
    if smart_sessao.parece_deslogado(html):
        raise SessaoCaiu("a grade respondeu deslogado")
    return analise.ler_grade(html, cfg.URL_GERAR)


# --------------------------------------------------------------------------- #
# 2) geracao
# --------------------------------------------------------------------------- #
def gerar_remessa(ctx, grade, dry_run=True, log=print):
    """Monta (e, se dry_run=False, envia) o POST de geracao.

    Retorna dict:
        ok       True gerou | None dry-run | False falhou
        enviado  o POST FOI? (decide se ha risco de remessa orfa)
        dados    bytes do .REM, quando a resposta e o arquivo
        nome     nome do arquivo (traz o SEQUENCIAL da remessa)
        corpo    o corpo que foi/seria enviado
    """
    corpo, campos = analise.montar_geracao(grade, acao=cfg.ACAO_GERAR)

    log(f"  POST de geracao -> {cfg.URL_GERAR}")
    for k, v in sorted(campos.items()):
        log(f"      {k:18} = {v!r}")

    if dry_run:
        return {"ok": None, "enviado": False, "motivo": "DRY_RUN (nada enviado)",
                "corpo": corpo, "dados": None, "nome": None}

    log("  *** ENVIANDO — gerar remessa de pagamento e IRREVERSIVEL ***")
    r = ctx.request.post(
        cfg.URL_GERAR, data=corpo,
        headers={"content-type": "application/x-www-form-urlencoded"},
        timeout=180_000)
    dados = r.body()
    disp = r.headers.get("content-disposition", "")
    log(f"  resposta: status={r.status} bytes={len(dados)} "
        f"tipo={r.headers.get('content-type', '?')} disp={disp or '(nenhum)'}")

    arq = analise.inspecionar_arquivo(dados)
    if arq["ok"]:
        nome = analise.nome_do_arquivo(disp)
        log(f"  a resposta E o arquivo: {nome} ({arq['layout']}, "
            f"{arq['linhas']} linhas)")
        return {"ok": True, "enviado": True, "motivo": "gerado", "corpo": corpo,
                "dados": dados, "nome": nome, "layout": arq["layout"],
                "linhas": arq["linhas"]}

    # ⚠️ O POST FOI. A remessa provavelmente EXISTE no Smart — os titulos ja
    # sairam da fila de pendentes. Isto NAO pode virar "falhou" em silencio:
    # vira remessa orfa, e a proxima rodada dira "nada pendente".
    texto = dados.decode("iso-8859-1", errors="replace")
    if smart_sessao.parece_deslogado(texto):
        return {"ok": False, "enviado": True, "corpo": corpo, "dados": None,
                "nome": None,
                "motivo": "o POST foi e a resposta diz DESLOGADO — CONFERIR no Smart"}
    return {"ok": False, "enviado": True, "corpo": corpo, "dados": None,
            "nome": None, "html": texto[:1500],
            "motivo": f"o POST foi (status={r.status}) mas a resposta nao e "
                      f"arquivo ({arq['motivo']}) — CONFERIR no Smart"}


# --------------------------------------------------------------------------- #
# recuperacao: o arquivo pela grade de GERADO (SO LEITURA)
# --------------------------------------------------------------------------- #
def procurar_gerados(ctx, conta=None, log=print):
    """Lista os arquivos que a grade de GERADO mostra. Nunca aciona botao.

    Usada so para recuperar de um POST que foi e nao devolveu o arquivo. Le com
    `pesquisar=1` — a mesma trava do `montar_filtro` vale aqui: nada de submeter
    o form daquela tela, cujo unico botao e CANCELAR.
    """
    conta = conta or cfg.CONTA
    pagina = _corpo(ctx.request.get(cfg.URL_PESQUISA, timeout=60_000))
    if smart_sessao.parece_deslogado(pagina):
        raise SessaoCaiu("a tela de pesquisa respondeu deslogado")
    formularios = [f for f in analise.analisar(pagina, cfg.URL_PESQUISA)["forms"]
                   if any(c["nome"] for c in f["campos"])]
    if not formularios:
        return []
    corpo, _ = analise.montar_filtro(
        formularios[0],
        {"IdContaBancaria": conta, "pagtobmp": cfg.STATUS_GERADO})
    r = ctx.request.post(
        formularios[0]["action"], data=corpo,
        headers={"content-type": "application/x-www-form-urlencoded"},
        timeout=120_000)
    html = _corpo(r)
    if smart_sessao.parece_deslogado(html):
        raise SessaoCaiu("a grade de gerados respondeu deslogado")
    return analise.ler_grade(html, cfg.URL_GERAR)["arquivos"]


def baixar(ctx, ident, log=print):
    """GET no arquivo pelo id da grade. Retorna (nome, bytes) ou (None, None)."""
    url = f"{cfg.URL_DOWNLOAD}?file={ident}"
    try:
        r = ctx.request.get(url, timeout=90_000)
    except Exception as e:                                          # noqa: BLE001
        log(f"  id={ident}: ERRO na requisicao: {e}")
        return None, None
    if r.status != 200:
        log(f"  id={ident}: status {r.status}")
        return None, None
    dados = r.body()
    arq = analise.inspecionar_arquivo(dados)
    if not arq["ok"]:
        log(f"  id={ident}: DESCARTADO — {arq['motivo']}")
        return None, None
    nome = analise.nome_do_arquivo(r.headers.get("content-disposition", ""),
                                   padrao=f"remessa_{ident}.REM")
    return nome, dados


# --------------------------------------------------------------------------- #
# gravacao
# --------------------------------------------------------------------------- #
def guardar(dados, nome, log=print):
    """Grava o .REM na pasta de saida. NUNCA sobrescreve em silencio.

    Duas remessas nunca deveriam ter o mesmo nome — o sequencial muda a cada
    geracao. Nome repetido com conteudo diferente e sinal de problema, e
    sobrescrever apagaria uma remessa real: ganha sufixo e grita.

    Retorna (caminho, md5) ou (None, None) se nao gravou.
    """
    cfg.ensure_dirs()
    destino = os.path.join(cfg.PASTA_SAIDA, nome)
    if os.path.exists(destino):
        with open(destino, "rb") as f:
            atual = f.read()
        if atual == dados:
            log(f"  ja no disco, identico: {destino}")
            return destino, hashlib.md5(dados).hexdigest()
        destino = os.path.join(
            cfg.PASTA_SAIDA,
            f"{os.path.splitext(nome)[0]}_dup{datetime.now():%H%M%S}.REM")
        log(f"  ATENCAO: ja existe {nome} com conteudo DIFERENTE -> "
            f"salvando como {os.path.basename(destino)}")
    with open(destino, "wb") as f:
        f.write(dados)
    md5 = hashlib.md5(dados).hexdigest()
    log(f"  salvo: {destino} ({len(dados)} bytes, md5 {md5[:12]})")
    return destino, md5


# --------------------------------------------------------------------------- #
# o ciclo inteiro
# --------------------------------------------------------------------------- #
def ciclo(ctx, conta=None, dry_run=True, log=print):
    """Pesquisa pendentes, gera e guarda. Retorna o dict do resultado.

    Levanta SessaoCaiu (o chamador aborta a rodada) e GradeRecusada.
    """
    saida = {"pendentes": 0, "ids": [], "pix": 0, "gerou": False, "enviado": False,
             "arquivo": None, "md5": None, "caminho": None, "motivo": ""}

    grade = pesquisar_pendentes(ctx, conta, log=log)
    saida["pendentes"] = len(grade["titulos"])
    saida["ids"] = [t["id"] for t in grade["titulos"]]
    saida["pix"] = sum(1 for t in grade["titulos"] if t["pix"])
    log(f"  grade PENDENTE: {saida['pendentes']} titulo(s) {saida['ids']} "
        f"({saida['pix']} PIX) | botoes={grade['botoes']}")

    if not grade["titulos"]:
        saida["motivo"] = "nada pendente"
        return saida

    res = gerar_remessa(ctx, grade, dry_run=dry_run, log=log)
    saida["enviado"] = res["enviado"]
    if res["ok"] is None:
        saida["motivo"] = "DRY_RUN"
        return saida

    if res["ok"]:
        saida["gerou"] = True
        saida["arquivo"] = res["nome"]
        saida["caminho"], saida["md5"] = guardar(res["dados"], res["nome"], log=log)
        saida["motivo"] = "gerado" if saida["caminho"] else "gerou mas NAO gravou"
        return saida

    # POST foi e nao veio arquivo -> tentar recuperar pela grade de GERADO
    saida["motivo"] = res["motivo"]
    log(f"  ATENCAO: {res['motivo']}")
    log("  recuperando pela grade de GERADO (so leitura)...")
    try:
        arquivos = procurar_gerados(ctx, conta, log=log)
    except SessaoCaiu:
        raise
    except Exception as e:                                          # noqa: BLE001
        log(f"  a recuperacao falhou: {e}")
        return saida
    if not arquivos:
        log("  a grade de GERADO nao mostrou arquivo — CONFERIR NO SMART")
        return saida
    ident = max(arquivos, key=lambda a: int(a["id"]))["id"]
    log(f"  arquivo mais recente na grade: file={ident}")
    nome, dados = baixar(ctx, ident, log=log)
    if not dados:
        return saida

    # A grade de GERADO pode devolver so o arquivo MAIS ANTIGO que ja
    # conheciamos -- nada garante que a remessa NOVA (a que motivou esta
    # recuperacao) ja apareceu ali. Medido em 28/08/2026: o POST veio
    # malformado para 5 titulos, e "o mais recente" continuava sendo um
    # leftover de 27/08 (mesmo nome, mesmo conteudo, recuperado repetidas
    # vezes). Sem esta checagem isso virava `gerou=True` -- os titulos ja
    # tinham saido da fila de Pendente no Smart, e ninguem saberia que a
    # remessa real nunca foi capturada. `caminho` fica None de proposito: e
    # o que ja liga o alerta existente em robo_pagamento.py (`enviado and
    # not caminho` -> SAIU_RODADA_INCOMPLETA) sem precisar duplicar a trava.
    destino = os.path.join(cfg.PASTA_SAIDA, nome)
    ja_conhecido = os.path.exists(destino)
    if ja_conhecido:
        with open(destino, "rb") as f:
            ja_conhecido = f.read() == dados
    if ja_conhecido:
        saida["motivo"] = (
            f"recuperacao achou so {nome}, ja conhecido -- a remessa NOVA nao "
            f"apareceu na grade de GERADO. Titulos {saida['ids']} podem ter "
            f"saido de Pendente sem remessa capturada -- CONFERIR NO SMART"
        )
        log(f"  ATENCAO: {saida['motivo']}")
        return saida

    saida["gerou"] = True
    saida["arquivo"] = nome
    saida["caminho"], saida["md5"] = guardar(dados, nome, log=log)
    saida["motivo"] = "recuperado pela grade de GERADO"
    return saida
