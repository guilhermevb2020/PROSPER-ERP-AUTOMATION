# -*- coding: utf-8 -*-
"""
carregar_historico_csv.py - leva para o banco o que so os CSVs de controle sabiam, para
que nenhum job precise mais ler CSV (Gerencia, 22/09/2026: "colocar tudo no banco ... e
eliminar a escrita no csv").

  retorno de cobranca (controle_processados.csv) -> erp_automation.arquivo_historico
      (erp_008), uma linha por md5: retorno_bb quando alguma linha e da conta 395 (a da
      entrada BB API), senao retorno_cobranca_cnab_400. O detalhe guarda o que a memoria
      do job usa: `processado` (alguma linha processada) e `nomes_smart`.
  retorno de pagamento (controle.csv)            -> arquivo_historico,
      retorno_pagamento_cnab_240, uma linha por md5.
  credito (controle_downloads.csv)               -> operacao_evento: documentos_baixados
      e, quando a etapa foi movida, etapa_movida — com o instante do CSV.

Cada familia entra num comando so (tudo ou nada) e a carga pode ser repetida: o que ja
entrou nao entra de novo. Ensaio por padrao (le, confere e conta); --pra-valer grava numa
execucao `controle/carregar_historico_csv`, com ERP_OPERADOR e ERP_MOTIVO.

Fuso do texto dos CSVs: o container rodou em UTC ate ser recriado com
TZ=America/Sao_Paulo (21/09/2026 21:41 local) e os jobs nao rodam de madrugada, entao
texto anterior a 22/09/2026 00:00 e UTC e o resto e hora local. O texto original fica
no detalhe (`quando_csv`).

Uso (no container, ambiente do job):
  python carregar_historico_csv.py [--familia retorno|retorno_pagamento|credito]... [--pra-valer]
Exit: 0 ok; 1 erro; 2 --pra-valer sem ERP_OPERADOR/ERP_MOTIVO.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from src.common.clients import execucao_job  # noqa: E402

JOB = "carregar_historico_csv"
TZ_CASA = ZoneInfo("America/Sao_Paulo")
#: texto anterior a isto foi escrito com o container em UTC (ver docstring)
VIRADA_DO_FUSO = datetime(2026, 9, 22, 0, 0, 0)
CONTA_BB_API = "395"
#: o resultado que o credito grava no etapa_movida (credito/config.py ROTULO_ANALISE_CREDITO;
#: um teste confere que sao iguais)
ROTULO_ETAPA_CREDITO = "Análise de crédito"
_MD5 = re.compile(r"^[0-9a-f]{32}$")

SAIU_OK, SAIU_ERRO, SAIU_SEM_AUTOR = 0, 1, 2


def _caminho_credito() -> str:
    """O mesmo lugar que credito/config.py resolve: data/ quando existe, senao a pasta do job."""
    novo = "/app/data/robo_credito/controle_downloads.csv"
    return novo if os.path.exists(novo) else "/app/src/processors/web/credito/controle_downloads.csv"


CSV_PADRAO = {
    "retorno": lambda: os.environ.get("ARQ_CONTROLE_RET")
    or "/app/data/robo_retorno/controle_processados.csv",
    "retorno_pagamento": lambda: os.environ.get("ARQ_CONTROLE_RETPAG")
    or "/app/data/robo_retorno_pagamento/controle.csv",
    "credito": lambda: os.environ.get("ARQ_CONTROLE_DOWNLOAD") or _caminho_credito(),
}


def instante_do_csv(texto: str, formato: str = "%Y-%m-%d %H:%M:%S") -> datetime | None:
    """O texto de data do CSV como instante (com fuso), pela regra da virada do container."""
    try:
        ingenuo = datetime.strptime((texto or "").strip(), formato)
    except ValueError:
        return None
    if ingenuo < VIRADA_DO_FUSO:
        return ingenuo.replace(tzinfo=timezone.utc)
    return ingenuo.replace(tzinfo=TZ_CASA)


def _ler(caminho: str, delimitador: str = ",", encoding: str = "utf-8") -> list[dict]:
    with open(caminho, encoding=encoding, newline="") as f:
        return list(csv.DictReader(f, delimiter=delimitador))


def historico_retorno(linhas: list[dict], origem: str) -> tuple[list[dict], int]:
    """controle_processados.csv -> (linhas da erp_008, linhas do CSV sem md5 valido)."""
    por_md5: dict[str, dict] = {}
    sem_md5 = 0
    for l in linhas:
        md5 = (l.get("hash") or "").strip().lower()
        if not _MD5.match(md5):
            sem_md5 += 1
            continue
        r = por_md5.setdefault(md5, {"bb": False, "processado": False, "nomes": set(),
                                     "n": 0, "ultima": None})
        r["n"] += 1
        r["bb"] = r["bb"] or (l.get("conta") or "").strip() == CONTA_BB_API
        r["processado"] = r["processado"] or str(l.get("processado", "")).strip().lower() == "true"
        r["nomes"].add((l.get("nome_smart") or "").strip())
        r["ultima"] = l
    saida = []
    for md5, r in por_md5.items():
        u = r["ultima"]
        saida.append({
            "tipo_arquivo": "retorno_bb" if r["bb"] else "retorno_cobranca_cnab_400",
            "md5": md5,
            "nome_arquivo": (u.get("arquivo") or "").strip(),
            "tratado_em": instante_do_csv(u.get("quando")),
            "origem": origem,
            "detalhe": {"processado": r["processado"], "nomes_smart": sorted(r["nomes"]),
                        "linhas_csv": r["n"], "conta": (u.get("conta") or "").strip(),
                        "ultimo_motivo": (u.get("motivo") or "").strip()[:300],
                        "quando_csv": (u.get("quando") or "").strip()},
        })
    return saida, sem_md5


def historico_retorno_pagamento(linhas: list[dict], origem: str) -> tuple[list[dict], int]:
    """controle.csv do retorno de pagamento -> (linhas da erp_008, linhas sem md5 valido)."""
    por_md5: dict[str, dict] = {}
    sem_md5 = 0
    for l in linhas:
        md5 = (l.get("hash") or "").strip().lower()
        if not _MD5.match(md5):
            sem_md5 += 1
            continue
        por_md5[md5] = l          # a ultima linha do md5 e a que vale
    saida = [{"tipo_arquivo": "retorno_pagamento_cnab_240", "md5": md5,
              "nome_arquivo": (l.get("arquivo") or "").strip(),
              "tratado_em": instante_do_csv(l.get("quando")), "origem": origem,
              "detalhe": {"status_http": (l.get("status_http") or "").strip(),
                          "quando_csv": (l.get("quando") or "").strip()}}
             for md5, l in por_md5.items()]
    return saida, sem_md5


_VERDADEIRO = ("1", "true", "sim", "yes")


def eventos_credito(linhas: list[dict], origem: str, rotulo_etapa: str) -> tuple[list[dict], int]:
    """controle_downloads.csv -> (eventos documentos_baixados/etapa_movida, linhas ignoradas).
    O CSV nao guardava o instante do move: etapa_movida leva o do ultimo download, e diz."""
    eventos, ignoradas = [], 0
    for l in linhas:
        op = (l.get("id_operacao") or "").strip()
        quando = instante_do_csv(l.get("data_download"), "%d/%m/%Y %H:%M:%S")
        if not op.isdigit() or quando is None:
            ignoradas += 1
            continue
        nfe_ok = (l.get("nfe_ok") or "").strip().lower() in _VERDADEIRO
        resumo_ok = (l.get("resumo_ok") or "").strip().lower() in _VERDADEIRO
        base = {"origem": origem, "quando_csv": (l.get("data_download") or "").strip()}
        eventos.append({
            "id_operacao": int(op), "tipo_evento": "documentos_baixados",
            "resultado": "OK" if (nfe_ok and resumo_ok) else "PARCIAL", "ocorrido_em": quando,
            "detalhe": {**base, "arquivo_nfe": (l.get("arquivo_nfe") or "").strip(),
                        "arquivo_resumo": (l.get("arquivo_resumo") or "").strip(),
                        "nfe_ok": nfe_ok, "resumo_ok": resumo_ok}})
        if (l.get("etapa_movida") or "").strip().lower() in _VERDADEIRO:
            eventos.append({
                "id_operacao": int(op), "tipo_evento": "etapa_movida", "resultado": rotulo_etapa,
                "ocorrido_em": quando,
                "detalhe": {**base, "instante": "o do ultimo download (o CSV nao guardava o do move)"}})
    return eventos, ignoradas


def montar_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Carrega no banco o historico dos CSVs de controle.")
    ap.add_argument("--familia", action="append", choices=sorted(CSV_PADRAO),
                    help="so esta familia (repetivel); padrao: as tres")
    ap.add_argument("--csv", action="append", default=[], metavar="FAMILIA=CAMINHO",
                    help="outro caminho para o CSV de uma familia")
    ap.add_argument("--pra-valer", action="store_true", help="grava (sem isto e ensaio)")
    return ap


def main(argv=None) -> int:
    args = montar_parser().parse_args(argv)
    ensaio = not args.pra_valer
    familias = args.familia or ["retorno", "retorno_pagamento", "credito"]
    caminhos = {f: CSV_PADRAO[f]() for f in familias}
    for par in args.csv:
        f, _, c = par.partition("=")
        if f not in CSV_PADRAO or not c:
            print(f"--csv invalido: {par!r} (use FAMILIA=CAMINHO)")
            return SAIU_ERRO
        caminhos[f] = c
    if not ensaio and not (os.environ.get("ERP_OPERADOR") and os.environ.get("ERP_MOTIVO")):
        print("--pra-valer exige ERP_OPERADOR e ERP_MOTIVO no ambiente (quem e por que)")
        return SAIU_SEM_AUTOR

    execucao = execucao_job.abrir_execucao("controle", JOB, flag_ensaio=ensaio,
                                           obrigatoria=not ensaio,
                                           detalhe={"familias": familias, "csv": caminhos})
    codigo = SAIU_ERRO
    try:
        print(f"CARGA DO HISTORICO DOS CSVs — {'ENSAIO' if ensaio else '*** PRA VALER ***'}")
        resumo = {}
        for familia in familias:
            caminho = caminhos[familia]
            if familia == "credito":
                linhas = _ler(caminho, delimitador=";", encoding="utf-8-sig")
                itens, fora = eventos_credito(linhas, os.path.basename(caminho),
                                              ROTULO_ETAPA_CREDITO)
                carregar = execucao_job.carregar_historico_eventos
                unidade = "evento(s)"
            else:
                linhas = _ler(caminho)
                montar = historico_retorno if familia == "retorno" else historico_retorno_pagamento
                itens, fora = montar(linhas, os.path.basename(caminho))
                carregar = execucao_job.carregar_historico_arquivos
                unidade = "md5"
            entraram = None if ensaio else carregar(execucao, itens)
            resumo[familia] = {"csv": caminho, "linhas_csv": len(linhas), "itens": len(itens),
                               "sem_chave": fora, "entraram": entraram}
            por_tipo = {}
            for i in itens:
                chave = i.get("tipo_arquivo") or i.get("tipo_evento")
                por_tipo[chave] = por_tipo.get(chave, 0) + 1
            print(f"  {familia:18} {len(linhas):>6} linha(s) do CSV -> {len(itens)} {unidade} "
                  f"{por_tipo} | sem chave valida: {fora} | "
                  + ("(ensaio: nada gravado)" if ensaio else f"entraram agora: {entraram}"))
        execucao_job.anotar(execucao, "carga", resumo)
        codigo = SAIU_OK
        return codigo
    except Exception as e:  # noqa: BLE001
        print(f"ERRO: {type(e).__name__}: {str(e)[:300]}")
        return SAIU_ERRO
    finally:
        execucao_job.fechar_execucao(execucao, "sucesso" if codigo == SAIU_OK else "falha",
                                     codigo_saida=codigo)


if __name__ == "__main__":
    sys.exit(main())
