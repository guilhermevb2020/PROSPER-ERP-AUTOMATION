# -*- coding: utf-8 -*-
"""
robo_pagamento.py - gera a remessa de PAGAMENTO (BMP Money Plus) e baixa o .REM.

Robo do ERP AUTOMATION. Roda DESATENDIDO: sobe o proprio Chrome no display :94,
loga via CapSolver, pesquisa os pagamentos PENDENTES da conta, gera a remessa,
salva o arquivo e FECHA. Um login por run.

Tudo por HTTP, sobre os cookies da sessao — nenhuma etapa depende de clicar em
tela. O contrato das duas requisicoes esta em `gerar.py`, e foi medido contra o
Smart real em 21/08/2026 (o HTML cru esta em `data/sandbox/robo_pagamento/debug/`).

    pesquisa  POST pagtobmppesquisa.php   (conta + status=P + pesquisar=1)
    geracao   POST pagtobmpgrid.php       (processar=1 + acao=1)
              -> a resposta E o arquivo (application/octet-stream)

O ENVIO AO BANCO NAO E DESTE ROBO. Ele so gera e guarda o .REM.

SEGURANCA
---------
- DRY_RUN e o padrao (`DRY_RUN_PAG`). Sem `--pra-valer` o robo monta o POST,
  mostra o corpo exato e NAO gera nada. Gerar remessa de pagamento MOVE DINHEIRO
  e nao tem desfazer.
- `acao` e CHUMBADO em 1. `pagtobmpgrid.php` e o mesmo endpoint para consultar e
  para agir, e na grade de "Gerado" o unico botao e CANCELAR — um digito de
  diferenca. `analise.montar_geracao` recusa a montagem se a grade nao oferecer
  o botao "Gerar".
- Sessao caida ABORTA a rodada. Grade vazia pode ser "sem pendente" ou "sessao
  morreu"; o Smart responde HTTP 200 com redirect p/ `expira.php` no segundo
  caso, e tratar isso como "nada a fazer" e terminar com cara de sucesso sem ter
  olhado nada.
- POST que FOI e nao devolveu arquivo NAO vira falha silenciosa: os titulos ja
  sairam da fila, entao o robo recupera pela grade de GERADO (so leitura).
- Valida CNAB-240 antes de gravar. Sessao caindo no meio faz o Smart devolver
  HTML; gravar isso com nome de `.REM` poe lixo na pasta do Financeiro.
- Idempotencia: `controle_pagamentos.csv` guarda arquivo/md5/titulos.

Uso:
    # producao (o wrapper do hub chama isto)
    sh /app/src/processors/web/robo_pagamento/run_agendado.sh

    # manual, dentro do container
    python /app/src/processors/web/robo_pagamento/robo_pagamento.py            # dry-run
    python .../robo_pagamento.py --pra-valer                                   # gera
    python .../robo_pagamento.py --listar                                      # so olha
"""
import argparse
import csv
import os
import sys
from datetime import datetime

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

from playwright.sync_api import sync_playwright  # noqa: E402

import gerar as ger                              # noqa: E402
import _nextcloud as nuvem                       # noqa: E402
import pagamento_config as cfg                   # noqa: E402
from src.common.clients import smart_sessao      # noqa: E402

CABECALHO_CONTROLE = ["arquivo", "bytes", "md5", "titulos", "ids", "pix", "quando"]

# Codigos de saida (o hub-orchestration marca a execucao pelo exit code).
SAIU_OK = 0
SAIU_SEM_NAVEGADOR = 1
SAIU_SEM_SESSAO = 2
SAIU_SMART_MUDO = 3
SAIU_GRADE_RECUSADA = 5
SAIU_RODADA_INCOMPLETA = 6


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# controle (idempotencia e trilha)
# --------------------------------------------------------------------------- #
def ler_controle():
    """{md5: linha} do que ja foi gravado."""
    if not os.path.exists(cfg.ARQ_CONTROLE):
        return {}
    try:
        with open(cfg.ARQ_CONTROLE, encoding="utf-8", newline="") as f:
            return {l["md5"]: l for l in csv.DictReader(f) if l.get("md5")}
    except Exception as e:                                          # noqa: BLE001
        log(f"  (aviso ao ler o controle: {e})")
        return {}


def gravar_controle(registro):
    """Anexa uma linha. Cabecalho antigo e arquivado em vez de desalinhar.

    (O retorno_cobranca pegou esse bug uma vez: CSV criado por versao com menos
    colunas + linhas novas com mais campos = arquivo inteiro fora de posicao.)
    """
    os.makedirs(os.path.dirname(cfg.ARQ_CONTROLE) or ".", exist_ok=True)
    existe = os.path.exists(cfg.ARQ_CONTROLE)
    if existe:
        try:
            with open(cfg.ARQ_CONTROLE, encoding="utf-8", newline="") as f:
                atual = next(csv.reader(f), [])
            if atual and atual != CABECALHO_CONTROLE:
                velho = f"{cfg.ARQ_CONTROLE}.{datetime.now():%Y%m%d%H%M%S}.bak"
                os.rename(cfg.ARQ_CONTROLE, velho)
                log(f"  (controle com cabecalho antigo -> arquivado em {velho})")
                existe = False
        except Exception as e:                                      # noqa: BLE001
            log(f"  (aviso ao conferir o cabecalho: {e})")
    with open(cfg.ARQ_CONTROLE, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CABECALHO_CONTROLE, extrasaction="ignore")
        if not existe:
            w.writeheader()
        w.writerow(registro)


# --------------------------------------------------------------------------- #
# rodada
# --------------------------------------------------------------------------- #
def rodada(ctx, args, dry):
    log("=" * 66)
    log(f"PAGAMENTO BMP {'(DRY_RUN - nao gera nada)' if dry else '*** PRA VALER ***'}"
        f"  |  conta {args.conta}")
    log(f"saida   : {cfg.PASTA_SAIDA}")
    log(f"controle: {cfg.ARQ_CONTROLE}")
    log("=" * 66)

    if args.listar:
        grade = ger.pesquisar_pendentes(ctx, args.conta, log=log)
        log(f"{len(grade['titulos'])} pendente(s): "
            f"{[(t['id'], 'PIX' if t['pix'] else 'TED') for t in grade['titulos']]}")
        log(f"botoes da tela: {grade['botoes']}")
        log(f"arquivos ja na grade: {[(a['id'], a['nome']) for a in grade['arquivos']]}")
        return SAIU_OK

    r = ger.ciclo(ctx, args.conta, dry_run=dry, log=log)

    log("=" * 66)
    log(f"RESUMO: {r['pendentes']} pendente(s) ({r['pix']} PIX) | "
        f"gerou={r['gerou']} | arquivo={r['arquivo'] or '-'} | {r['motivo']}")

    if r["gerou"] and r["md5"]:
        controle = ler_controle()
        if r["md5"] in controle:
            log(f"  (md5 ja no controle — mesmo conteudo de "
                f"{controle[r['md5']]['arquivo']} em {controle[r['md5']]['quando']})")
        else:
            gravar_controle({
                "arquivo": os.path.basename(r["caminho"] or r["arquivo"] or ""),
                "bytes": os.path.getsize(r["caminho"]) if r["caminho"] else 0,
                "md5": r["md5"], "titulos": r["pendentes"],
                "ids": ",".join(r["ids"]), "pix": r["pix"],
                "quando": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        # Sobe pro Nextcloud na hora — mesmo padrao do robo_remessa (CNAB 400):
        # quem chama ja tem o arquivo local, entao falha de rede aqui NUNCA
        # perde o arquivo (ele fica no controle e pode subir depois, a mao).
        if r["caminho"]:
            with open(r["caminho"], "rb") as _f:
                _dados = _f.read()
            ok_nc, alvo_nc, detalhe_nc = nuvem.enviar(_dados, os.path.basename(r["caminho"]))
            if ok_nc:
                log(f"  subiu pro Nextcloud: {alvo_nc} ({detalhe_nc})")
            else:
                log(f"  AVISO: nao subiu pro Nextcloud ({detalhe_nc}) — "
                    f"arquivo local em {r['caminho']}, suba a mao")

    if dry:
        log("(DRY_RUN: nada foi gerado. Use --pra-valer quando quiser valer.)")
        return SAIU_OK

    # O caso que precisa de gente: o POST FOI e o arquivo nao esta na pasta. Os
    # titulos ja sairam da fila, entao a proxima rodada dira "nada pendente" e
    # ninguem vai perceber sozinho.
    if r["enviado"] and not r["caminho"]:
        log("PENDENTE: o POST foi e o arquivo NAO esta na pasta. "
            "Confira a tela 'Gerado' no Smart.")
        return SAIU_RODADA_INCOMPLETA
    return SAIU_OK


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def montar_parser():
    ap = argparse.ArgumentParser(
        description="Gera a remessa de pagamento BMP Money Plus e baixa o .REM.")
    ap.add_argument("--conta", default=cfg.CONTA,
                    help=f"IdContaBancaria (padrao: {cfg.CONTA})")
    ap.add_argument("--pra-valer", action="store_true",
                    help="desliga o DRY_RUN: GERA DE VERDADE (move dinheiro)")
    ap.add_argument("--listar", action="store_true",
                    help="so mostra os pendentes e sai, sem gerar nada")
    ap.add_argument("--cdp", action="store_true",
                    help="usa um Chrome JA ABERTO (dev/VNC) em vez de subir o proprio")
    return ap


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                               # noqa: BLE001
        pass

    args = montar_parser().parse_args()
    dry = cfg.DRY_RUN and not args.pra_valer
    cfg.exigir_tela()

    with sync_playwright() as p:
        try:
            with smart_sessao.sessao(p, cfg, usar_cdp=args.cdp, log=log) as ctx:
                # Timeout NAO e deslogado — o Smart fica lento depois de
                # processar. So aborta quando A RESPOSTA diz que caiu.
                estado = smart_sessao.sessao_viva(ctx, cfg, log=log)
                if estado == "deslogado":
                    log("ERRO: a sessao do Smart nao esta logada.")
                    return SAIU_SEM_SESSAO
                if estado is None:
                    log("ERRO: nao consegui falar com o Smart. Rede? Smart fora? "
                        "(isto NAO quer dizer deslogado)")
                    return SAIU_SMART_MUDO
                log("sessao do Smart OK (logada).")
                try:
                    return rodada(ctx, args, dry)
                except ger.SessaoCaiu as e:
                    log(f"ABORTANDO: {e}")
                    log("A rodada NAO terminou. Isto nao e 'nada pendente'.")
                    return SAIU_SEM_SESSAO
                except ger.GradeRecusada as e:
                    log(f"RECUSADO: {e}")
                    return SAIU_GRADE_RECUSADA
                except ValueError as e:
                    # montar_geracao recusa grade sem o botao Gerar
                    log(f"RECUSADO: {e}")
                    return SAIU_GRADE_RECUSADA
        except smart_sessao.SmartIndisponivel as e:
            log(f"ERRO: {e}")
            return SAIU_SMART_MUDO
        except smart_sessao.SemSessao as e:
            log(f"ERRO: {e}")
            return SAIU_SEM_SESSAO
        except smart_sessao.SemNavegador as e:
            log(f"ERRO: {e}")
            return SAIU_SEM_NAVEGADOR


if __name__ == "__main__":
    sys.exit(main())
