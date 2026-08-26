# -*- coding: utf-8 -*-
"""
robo_retorno_pagamento.py - insere o retorno CNAB 240 de pagamento no Smart (dá baixa).

Robô do ERP AUTOMATION. Roda DESATENDIDO: sobe o próprio Chrome no display :93,
loga via CapSolver, lê os `.RET` publicados em
`FINANCEIRO/Pagamentos-MoneyPlus/_RETORNOS` (Nextcloud — é o `baixar_retorno_pagamento.py`
do process-automation que os deixa lá) e sobe cada um em
"Financeiro > Sistemas de pagamento > Pagamento BMP Money Plus > Processar Retorno".

O robô INSERE — não julga o resultado. Não existe fila de revisão: uma vez que
o POST chegou ao servidor e teve resposta, o arquivo sai da entrada e nunca é
reenviado, seja qual for o conteúdo da resposta (decisão do dono, 26/08/2026).
A resposta crua ainda é salva em `DEBUG_DIR` — não para alguém revisar por
rotina, só para existir evidência se um dia precisar investigar algo pontual.

SEGURANÇA
---------
- DRY_RUN é o padrão (`DRY_RUN_RETPAG`). Sem `--pra-valer` o robô baixa o
  `.RET` do Nextcloud, monta o multipart e MOSTRA o que mandaria — não faz o
  POST, não move nada, não grava controle.
- **Identidade do arquivo é o MD5 do CONTEÚDO**, nunca o nome.
- **Só é seguro re-tentar o que NUNCA chegou ao servidor.** Falha de rede ou
  sessão morta no meio do POST deixam o arquivo NA ENTRADA para a próxima
  rodada tentar de novo — qualquer resposta REAL do servidor tira o arquivo
  da entrada e grava no controle, porque reenviar um arquivo que o Smart já
  viu do lado dele é processar duas vezes, não corrigir um erro.
- Sessão caída ABORTA a rodada — nunca segue reportando "nada a fazer".

Uso:
    # produção (o wrapper do hub chama isto)
    sh /app/src/processors/web/robo_retorno_pagamento/run_agendado.sh

    # manual, dentro do container
    python .../robo_retorno_pagamento.py --listar             # só olha a fila
    python .../robo_retorno_pagamento.py                      # dry-run
    python .../robo_retorno_pagamento.py --pra-valer --limite 1   # UM arquivo, de verdade
"""
import argparse
import csv
import hashlib
import os
import sys
from datetime import datetime

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from playwright.sync_api import sync_playwright  # noqa: E402

import _nextcloud as nuvem                        # noqa: E402
import retorno_pagamento as ret                    # noqa: E402
import retorno_pagamento_config as cfg             # noqa: E402
from src.common.clients import smart_sessao        # noqa: E402

CABECALHO_CONTROLE = ["arquivo", "hash", "status_http", "quando"]

SAIU_OK = 0
SAIU_SEM_NAVEGADOR = 1
SAIU_SEM_SESSAO = 2
SAIU_SMART_MUDO = 3
SAIU_COM_PENDENCIA = 6


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# controle (idempotência)
# --------------------------------------------------------------------------- #
def hashes_ja_tratados() -> set:
    if not os.path.exists(cfg.ARQ_CONTROLE):
        return set()
    try:
        with open(cfg.ARQ_CONTROLE, encoding="utf-8", newline="") as f:
            return {l["hash"] for l in csv.DictReader(f) if l.get("hash")}
    except Exception as e:                                              # noqa: BLE001
        log(f"  (aviso ao ler o controle: {e})")
        return set()


def gravar_controle(registro: dict) -> None:
    """Anexa uma linha. Cabeçalho antigo é arquivado em vez de desalinhar."""
    os.makedirs(os.path.dirname(cfg.ARQ_CONTROLE) or ".", exist_ok=True)
    existe = os.path.exists(cfg.ARQ_CONTROLE)
    if existe:
        try:
            with open(cfg.ARQ_CONTROLE, encoding="utf-8", newline="") as f:
                atual = next(csv.reader(f), [])
            if atual and atual != CABECALHO_CONTROLE:
                velho = f"{cfg.ARQ_CONTROLE}.{datetime.now():%Y%m%d%H%M%S}.bak"
                os.rename(cfg.ARQ_CONTROLE, velho)
                log(f"  (controle com cabeçalho antigo -> arquivado em {velho})")
                existe = False
        except Exception as e:                                          # noqa: BLE001
            log(f"  (aviso ao conferir cabeçalho: {e})")
    with open(cfg.ARQ_CONTROLE, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CABECALHO_CONTROLE, extrasaction="ignore")
        if not existe:
            w.writeheader()
        w.writerow(registro)


def salvar_resposta(nome_arquivo: str, html: str | None) -> str | None:
    """Grava a resposta crua no DEBUG_DIR — evidência, não fila de revisão."""
    if html is None:
        return None
    cfg.ensure_dirs()
    seguro = "".join(c if c.isalnum() or c in "._-" else "_" for c in nome_arquivo)
    caminho = os.path.join(cfg.DEBUG_DIR, f"{datetime.now():%Y%m%d-%H%M%S}_{seguro}.html")
    with open(caminho, "w", encoding="utf-8", errors="replace") as f:
        f.write(html)
    return caminho


# --------------------------------------------------------------------------- #
# um arquivo
# --------------------------------------------------------------------------- #
def tratar(ctx, nome_arquivo: str, dry: bool, feitos: set) -> str:
    """Devolve: 'pendente' (nada feito, tenta de novo depois) | 'ok' | 'repete'."""
    dados = nuvem.baixar(nome_arquivo)
    if dados is None:
        log(f"  {nome_arquivo}: não consegui baixar do Nextcloud — tenta de novo depois")
        return "pendente"

    digest = hashlib.md5(dados).hexdigest()
    if digest in feitos:
        log(f"  {nome_arquivo}: conteúdo já inserido antes (md5 {digest[:8]}) — só arquivando")
        nuvem.mover_para(nome_arquivo, cfg.SUB_PROCESSADOS)
        return "repete"

    if dry:
        log(f"  [DRY][enviaria] {nome_arquivo} ({len(dados)} bytes) -> {cfg.URL_RETORNO} "
            "(etapa 1: upload — etapa 2: confirmar)")
        return "pendente"

    # Etapa 1 — upload. Só STAGEIA o arquivo e devolve uma prévia; não efetiva
    # nada. Reenviar esta etapa de novo (se a etapa 2 falhar de rede) é
    # inofensivo — o Smart só re-stagea, não dá baixa duas vezes.
    resposta1 = ret.enviar(ctx, cfg.URL_RETORNO, nome_arquivo, dados)
    if not resposta1["ok_rede"]:
        log(f"  {nome_arquivo}: FALHA DE REDE na etapa 1 ({resposta1['erro_rede']}) — "
            "fica na entrada, tenta de novo na próxima rodada")
        return "pendente"
    if smart_sessao.parece_deslogado(resposta1["html"] or ""):
        log(f"  {nome_arquivo}: sessão caiu na etapa 1 — fica na entrada, tenta de novo")
        return "pendente"

    caminho1 = salvar_resposta(f"{nome_arquivo}.etapa1_previa", resposta1["html"])
    target = ret.extrair_target(resposta1["html"] or "")
    if not target:
        log(f"  {nome_arquivo}: etapa 1 respondeu (HTTP {resposta1['status']}) mas sem "
            f"'target' reconhecível — a tela pode ter mudado. Resposta em {caminho1}. "
            "Fica na entrada.")
        return "pendente"

    # Etapa 2 — confirmar. É esta que de fato dá baixa.
    resposta2 = ret.confirmar(ctx, cfg.URL_RETORNO, target)
    if not resposta2["ok_rede"]:
        log(f"  {nome_arquivo}: etapa 1 OK mas FALHA DE REDE na etapa 2 "
            f"({resposta2['erro_rede']}) — NÃO efetivou (a etapa 2 é quem confirma). "
            "Fica na entrada, tenta de novo (reenviar a etapa 1 é seguro).")
        return "pendente"
    if smart_sessao.parece_deslogado(resposta2["html"] or ""):
        log(f"  {nome_arquivo}: sessão caiu na etapa 2 — provavelmente NÃO efetivou. "
            "Fica na entrada, tenta de novo.")
        return "pendente"

    caminho2 = salvar_resposta(f"{nome_arquivo}.etapa2_confirmado", resposta2["html"])
    log(f"  {nome_arquivo}: inserido (etapa1 HTTP {resposta1['status']}, "
        f"etapa2 HTTP {resposta2['status']}) | respostas em {caminho1} e {caminho2}")

    gravar_controle({
        "arquivo": nome_arquivo, "hash": digest, "status_http": resposta2["status"],
        "quando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    nuvem.mover_para(nome_arquivo, cfg.SUB_PROCESSADOS)
    return "ok"


# --------------------------------------------------------------------------- #
# rodada
# --------------------------------------------------------------------------- #
def rodada(ctx, args, dry: bool) -> int:
    log("=" * 66)
    log(f"RETORNO PAGAMENTO BMP {'(DRY_RUN — não envia nada)' if dry else '*** PRA VALER ***'}")
    log(f"entrada : {cfg.NC_DEST_BASE}")
    log(f"controle: {cfg.ARQ_CONTROLE}")
    log("=" * 66)

    pendentes = [args.arquivo] if args.arquivo else nuvem.listar_pendentes()
    if args.limite:
        pendentes = pendentes[:args.limite]

    if args.listar:
        log(f"{len(pendentes)} arquivo(s) na entrada: {pendentes}")
        return SAIU_OK

    if not pendentes:
        log("nada em _RETORNOS — nenhum retorno de pagamento a inserir")
        return SAIU_OK

    feitos = hashes_ja_tratados()
    contagem = {"pendente": 0, "ok": 0, "repete": 0}
    for nome in pendentes:
        efeito = tratar(ctx, nome, dry, feitos)
        contagem[efeito] = contagem.get(efeito, 0) + 1

    log("=" * 66)
    log(f"RESUMO: {contagem}")
    if dry:
        log("(DRY_RUN: nada foi enviado. Use --pra-valer quando quiser valer.)")
        return SAIU_OK
    if contagem["pendente"]:
        log("PENDENTE: falha de rede/sessão deixou arquivo na entrada para a próxima rodada.")
        return SAIU_COM_PENDENCIA
    return SAIU_OK


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def montar_parser():
    ap = argparse.ArgumentParser(
        description="Insere o retorno CNAB 240 de pagamento no Smart (Processar Retorno).")
    ap.add_argument("--arquivo", help="processa só este arquivo (nome exato na entrada)")
    ap.add_argument("--limite", type=int, help="processa no máximo N arquivos")
    ap.add_argument("--listar", action="store_true", help="só mostra a fila e sai")
    ap.add_argument("--pra-valer", action="store_true",
                    help="desliga o DRY_RUN: ENVIA de verdade (dá baixa no Smart)")
    ap.add_argument("--cdp", action="store_true",
                    help="usa um Chrome JÁ ABERTO (dev/VNC) em vez de subir o próprio")
    return ap


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                                   # noqa: BLE001
        pass

    args = montar_parser().parse_args()
    dry = cfg.DRY_RUN and not args.pra_valer
    cfg.ensure_dirs()

    if args.listar:
        if not nuvem.disponivel():
            log("ERRO: sem credencial do Nextcloud (config/nextcloud.env).")
            return SAIU_SEM_SESSAO
        pendentes = nuvem.listar_pendentes()
        log(f"{len(pendentes)} arquivo(s) na entrada: {pendentes}")
        return SAIU_OK

    with sync_playwright() as p:
        try:
            with smart_sessao.sessao(p, cfg, usar_cdp=args.cdp, log=log) as ctx:
                estado = smart_sessao.sessao_viva(ctx, cfg, log=log)
                if estado == "deslogado":
                    log("ERRO: a sessão do Smart não está logada.")
                    return SAIU_SEM_SESSAO
                if estado is None:
                    log("ERRO: não consegui falar com o Smart. Rede? Smart fora? "
                        "(isto NÃO quer dizer deslogado)")
                    return SAIU_SMART_MUDO
                log("sessão do Smart OK (logada).")
                return rodada(ctx, args, dry)
        except smart_sessao.SemSessao as e:
            log(f"ERRO: {e}")
            return SAIU_SEM_SESSAO
        except smart_sessao.SemNavegador as e:
            log(f"ERRO: {e}")
            return SAIU_SEM_NAVEGADOR


if __name__ == "__main__":
    sys.exit(main())
