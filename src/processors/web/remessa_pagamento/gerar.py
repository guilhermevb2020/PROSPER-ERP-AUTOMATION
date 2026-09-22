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
import time
from datetime import datetime

import analise
import pagamento_config as cfg
from src.common.clients import smart_sessao

# Quantas vezes tenta reler a grade de GERADO antes de desistir, e quanto
# espera entre tentativas -- da tempo pro Smart indexar o arquivo novo.
# So leitura (procurar_gerados + baixar), sem risco de duplicidade.
_TENTATIVAS_RECUPERACAO = 3
_ESPERA_RECUPERACAO_S = 5


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
def _salvar_resposta_malformada(dados, log=print):
    """Guarda o bruto da resposta malformada do POST de geracao, para dar para
    inspecionar depois -- hoje ninguem sabia o QUE vinha nessa resposta, so
    que ela falhava na checagem de layout (linhas de tamanho errado). So
    leitura de diagnostico; nao muda nenhum comportamento do robo."""
    try:
        cfg.ensure_dirs()
        caminho = os.path.join(
            cfg.DEBUG_DIR, f"{datetime.now():%Y%m%d-%H%M%S}_post_malformado.bin")
        with open(caminho, "wb") as f:
            f.write(dados)
        log(f"  resposta malformada salva em {caminho} (diagnostico)")
    except Exception as e:                                          # noqa: BLE001
        log(f"  nao consegui salvar a resposta malformada para diagnostico: {e}")


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
    dados_recebidos = r.body()
    disp = r.headers.get("content-disposition", "")
    log(f"  resposta: status={r.status} bytes={len(dados_recebidos)} "
        f"tipo={r.headers.get('content-type', '?')} disp={disp or '(nenhum)'}")

    dados, reparados = analise.reparar_padding_info12_cnab240(dados_recebidos)
    if reparados:
        log(f"  reparo local CNAB-240: {reparados} segmento(s) B recebeu(ram) "
            "o padding ausente da Informacao 12")
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
    texto = dados_recebidos.decode("iso-8859-1", errors="replace")
    if smart_sessao.parece_deslogado(texto):
        return {"ok": False, "enviado": True, "corpo": corpo, "dados": None,
                "nome": None,
                "motivo": "o POST foi e a resposta diz DESLOGADO — CONFERIR no Smart"}
    # Diagnostico: ninguem tinha olhado o CONTEUDO desta resposta malformada
    # ainda, so o resumo (linhas de tamanho errado). So leitura, nao muda
    # nenhum comportamento do robo -- guarda o bruto para inspecionar depois.
    _salvar_resposta_malformada(dados_recebidos, log=log)
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
    dados, reparados = analise.reparar_padding_info12_cnab240(r.body())
    if reparados:
        log(f"  id={ident}: reparo local CNAB-240 em {reparados} segmento(s) B")
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

    # O Smart pode levar alguns segundos para indexar o arquivo novo nessa
    # grade -- medido em 31/08/2026: a checagem rodava no MESMO segundo do
    # POST malformado, e nas 3 ocorrencias do dia sempre achava so o arquivo
    # mais antigo ja conhecido (CP2708000028.REM, de 27/08, recuperado
    # repetidas vezes ao longo de 4 dias). Tenta de novo com espera curta
    # antes de desistir -- e leitura pura (procurar_gerados + baixar), sem
    # risco de duplicidade.
    nome = dados = None
    for tentativa in range(1, _TENTATIVAS_RECUPERACAO + 1):
        log(f"  recuperando pela grade de GERADO (so leitura, "
            f"tentativa {tentativa}/{_TENTATIVAS_RECUPERACAO})...")
        try:
            arquivos = procurar_gerados(ctx, conta, log=log)
        except SessaoCaiu:
            raise
        except Exception as e:                                      # noqa: BLE001
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
        # recuperacao) ja apareceu ali. `caminho` fica None de proposito
        # quando as tentativas se esgotam: e o que ja liga o alerta existente
        # em gerar_remessa_pagamento.py (`enviado and not caminho` ->
        # SAIU_RODADA_INCOMPLETA) sem precisar duplicar a trava.
        destino = os.path.join(cfg.PASTA_SAIDA, nome)
        ja_conhecido = os.path.exists(destino)
        if ja_conhecido:
            with open(destino, "rb") as f:
                ja_conhecido = f.read() == dados
        if not ja_conhecido:
            saida["gerou"] = True
            saida["arquivo"] = nome
            saida["caminho"], saida["md5"] = guardar(dados, nome, log=log)
            saida["motivo"] = "recuperado pela grade de GERADO"
            return saida

        log(f"  ainda e {nome}, ja conhecido")
        if tentativa < _TENTATIVAS_RECUPERACAO:
            time.sleep(_ESPERA_RECUPERACAO_S)

    saida["motivo"] = (
        f"recuperacao tentou {_TENTATIVAS_RECUPERACAO}x "
        f"({_ESPERA_RECUPERACAO_S}s entre tentativas), achou so {nome}, ja "
        f"conhecido -- a remessa NOVA nao apareceu na grade de GERADO. "
        f"Titulos {saida['ids']} podem ter saido de Pendente sem remessa "
        f"capturada -- CONFERIR NO SMART"
    )
    log(f"  ATENCAO: {saida['motivo']}")
    return saida
