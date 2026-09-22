# -*- coding: utf-8 -*-
"""
comparar_controle_csv_banco.py - paridade entre os CSVs de controle e erp_automation.arquivo.

POR QUE EXISTE (Fase 0 de docs/PLANO_CONTROLE_NO_BANCO.md, 22/09/2026): desde 22/09 os
quatro jobs de arquivo gravam o CSV de controle E as tabelas no mesmo ponto do codigo.
O corte do CSV so acontece depois de semanas com as duas fontes iguais — e "iguais" tem
de ser medido todo dia por um job, nao por alguem lembrando de olhar.

O QUE COMPARA, por familia e por dia (data local do container, America/Sao_Paulo):
  controle_processados.csv   x  arquivo(retorno_cobranca_cnab_400, retorno_bb)
  controle_remessas.csv      x  arquivo(remessa_cobranca_cnab_400, remessa_bb)
  controle_pagamentos.csv    x  arquivo(remessa_pagamento_cnab_240)
  controle.csv (ret. pagto)  x  arquivo(retorno_pagamento_cnab_240)
A chave e o md5 do conteudo, que os dois lados guardam (no banco em detalhe_json.md5;
coluna gerada `md5` a partir da erp_005). Um arquivo re-entregue (o portao BB recusa os
mesmos .RET todo dia) ganha linha nova no CSV mas tem UMA linha em `arquivo`, do
primeiro dia: por isso o lado do banco e "registrado hoje OU com evento hoje".

SAIDA: um resumo por familia e o que so existe de um lado. Exit 0 = paridade;
SAIU_DIVERGENTE (3) = divergencia (o hub alerta); 1 = erro de leitura. So le: nao toca
no Smart nem escreve nada alem da propria execucao em job_execucao (automacao `controle`).

Uso:  python comparar_controle_csv_banco.py [--dia AAAA-MM-DD] [--json]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from src.common.clients import execucao_job  # noqa: E402

SAIU_OK = 0
SAIU_ERRO = 1
SAIU_DIVERGENTE = 3

TZ_PADRAO = "America/Sao_Paulo"
JOB = "comparar_controle_csv_banco"


@dataclass(frozen=True)
class Familia:
    nome: str
    csv_env: str
    csv_padrao: str
    tipos: tuple
    coluna_hash: str
    coluna_quando: str

    @property
    def caminho_csv(self) -> str:
        return os.environ.get(self.csv_env) or self.csv_padrao


#: As quatro familias, com os MESMOS nomes de variavel que cada job usa para achar o
#: seu CSV — quem mudar o caminho num job muda aqui pelo ambiente, nao no codigo.
FAMILIAS = (
    Familia("retorno", "ARQ_CONTROLE_RET", "/app/data/robo_retorno/controle_processados.csv",
            ("retorno_cobranca_cnab_400", "retorno_bb"), "hash", "quando"),
    Familia("remessa", "ARQ_CONTROLE", "/app/data/robo_remessa/controle_remessas.csv",
            ("remessa_cobranca_cnab_400", "remessa_bb"), "md5", "baixado_em"),
    Familia("pagamento", "ARQ_CONTROLE_PAG", "/app/data/robo_pagamento/controle_pagamentos.csv",
            ("remessa_pagamento_cnab_240",), "md5", "quando"),
    Familia("retorno_pagamento", "ARQ_CONTROLE_RETPAG", "/app/data/robo_retorno_pagamento/controle.csv",
            ("retorno_pagamento_cnab_240",), "hash", "quando"),
)


@dataclass
class LadoCsv:
    por_hash: dict = field(default_factory=dict)   # md5 -> nome do arquivo (ultima linha do dia)
    sem_hash: int = 0                              # linhas do dia sem hash: contadas, nao comparadas
    linhas_dia: int = 0
    existe: bool = True


@dataclass
class Resultado:
    familia: str
    csv: LadoCsv
    banco: dict                                    # md5 -> nome
    so_csv: list = field(default_factory=list)     # [(md5, nome)]
    so_banco: list = field(default_factory=list)

    @property
    def paridade(self) -> bool:
        return not self.so_csv and not self.so_banco


# --------------------------------------------------------------------------- #
# os dois lados
# --------------------------------------------------------------------------- #
def ler_csv(caminho: str, coluna_hash: str, coluna_quando: str, dia: str) -> LadoCsv:
    """As linhas do CSV cujo `quando` comeca pelo dia (AAAA-MM-DD). Arquivo ausente
    conta como vazio e fica marcado (existe=False): e diferente de "nada hoje"."""
    lado = LadoCsv()
    if not os.path.exists(caminho):
        lado.existe = False
        return lado
    with open(caminho, encoding="utf-8", errors="replace", newline="") as fh:
        for linha in csv.DictReader(fh):
            if not (linha.get(coluna_quando) or "").startswith(dia):
                continue
            lado.linhas_dia += 1
            h = (linha.get(coluna_hash) or "").strip().lower()
            if not h:
                lado.sem_hash += 1
                continue
            lado.por_hash[h] = linha.get("arquivo") or ""
    return lado


SQL_BANCO = """
    SELECT a.nome_arquivo, lower(a.detalhe_json ->> 'md5') AS md5
      FROM erp_automation.arquivo a
     WHERE a.tipo_arquivo = ANY(%(tipos)s)
       AND ((a.registrado_em AT TIME ZONE %(tz)s)::date = %(dia)s::date
            OR EXISTS (SELECT 1 FROM erp_automation.arquivo_evento e
                        WHERE e.fk_arquivo = a.id
                          AND (e.ocorrido_em AT TIME ZONE %(tz)s)::date = %(dia)s::date))
"""


def ler_banco(conn, tipos: tuple, dia: str, tz: str = TZ_PADRAO) -> dict:
    """md5 -> nome dos arquivos destes tipos registrados no dia OU com evento no dia."""
    with conn.cursor() as cur:
        cur.execute(SQL_BANCO, {"tipos": list(tipos), "tz": tz, "dia": dia})
        linhas = cur.fetchall()
    return {md5: nome for nome, md5 in linhas if md5}


def comparar(familia: str, lado_csv: LadoCsv, banco: dict) -> Resultado:
    r = Resultado(familia=familia, csv=lado_csv, banco=banco)
    r.so_csv = sorted((h, n) for h, n in lado_csv.por_hash.items() if h not in banco)
    r.so_banco = sorted((h, n) for h, n in banco.items() if h not in lado_csv.por_hash)
    return r


# --------------------------------------------------------------------------- #
# relatorio
# --------------------------------------------------------------------------- #
def relatorio(dia: str, resultados: list) -> str:
    out = [f"PARIDADE CSV x BANCO — {dia}"]
    for r in resultados:
        situacao = "OK" if r.paridade else "DIVERGE"
        ausente = "" if r.csv.existe else " (CSV ausente)"
        out.append(f"  {r.familia:18} csv={len(r.csv.por_hash):4}  banco={len(r.banco):4}  {situacao}{ausente}"
                   + (f"  [{r.csv.sem_hash} linha(s) do dia sem hash]" if r.csv.sem_hash else ""))
        for h, n in r.so_csv[:20]:
            out.append(f"      so no CSV   : {n}  ({h[:12]})")
        for h, n in r.so_banco[:20]:
            out.append(f"      so no BANCO : {n}  ({h[:12]})")
        if len(r.so_csv) > 20 or len(r.so_banco) > 20:
            out.append("      ... (lista cortada em 20 por lado)")
    total = sum(len(r.csv.por_hash) for r in resultados)
    divergentes = [r.familia for r in resultados if not r.paridade]
    out.append(f"TOTAL: {total} arquivo(s) no CSV; "
               + ("todas as familias em paridade" if not divergentes else f"DIVERGENCIA em {', '.join(divergentes)}"))
    return "\n".join(out)


def resumo_json(dia: str, resultados: list) -> dict:
    return {"dia": dia, "familias": {
        r.familia: {"csv": len(r.csv.por_hash), "banco": len(r.banco), "sem_hash": r.csv.sem_hash,
                    "csv_existe": r.csv.existe, "so_csv": [n for _, n in r.so_csv],
                    "so_banco": [n for _, n in r.so_banco], "paridade": r.paridade}
        for r in resultados}}


def codigo_de_saida(resultados: list) -> int:
    return SAIU_OK if all(r.paridade for r in resultados) else SAIU_DIVERGENTE


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def hoje(tz: str = TZ_PADRAO) -> str:
    return datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d")


def montar_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Paridade CSV de controle x erp_automation.arquivo, por dia.")
    ap.add_argument("--dia", default=None, help="AAAA-MM-DD (padrao: hoje, no fuso do container)")
    ap.add_argument("--tz", default=TZ_PADRAO)
    ap.add_argument("--json", action="store_true", help="imprime tambem o resumo em JSON")
    return ap


def executar(dia: str, tz: str, conn, log=print) -> tuple[int, list]:
    resultados = []
    for fam in FAMILIAS:
        lado = ler_csv(fam.caminho_csv, fam.coluna_hash, fam.coluna_quando, dia)
        banco = ler_banco(conn, fam.tipos, dia, tz)
        resultados.append(comparar(fam.nome, lado, banco))
    log(relatorio(dia, resultados))
    return codigo_de_saida(resultados), resultados


def main(argv=None) -> int:
    args = montar_parser().parse_args(argv)
    dia = args.dia or hoje(args.tz)
    execucao = execucao_job.abrir_execucao("controle", JOB, flag_ensaio=False, obrigatoria=False,
                                           detalhe={"dia": dia})
    codigo = SAIU_ERRO
    resultados = []
    try:
        try:
            conn = execucao_job.conexao_leitura(JOB)
        except Exception as e:  # noqa: BLE001
            print(f"ERRO: sem banco para comparar ({type(e).__name__}: {str(e)[:160]})")
            return SAIU_ERRO
        try:
            codigo, resultados = executar(dia, args.tz, conn)
        finally:
            conn.close()
        if args.json:
            print(json.dumps(resumo_json(dia, resultados), ensure_ascii=False, indent=1))
        return codigo
    finally:
        execucao_job.fechar_execucao(
            execucao, "sucesso" if codigo == SAIU_OK else "falha", codigo_saida=codigo,
            qtd_itens=sum(len(r.csv.por_hash) for r in resultados) if resultados else None,
            detalhe=resumo_json(dia, resultados) if resultados else {"dia": dia})


if __name__ == "__main__":
    sys.exit(main())
