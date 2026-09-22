# -*- coding: utf-8 -*-
"""
listar_md5.py - imprime, um por linha, os md5 dos arquivos de um ou mais tipos ja
registrados em erp_automation.arquivo — e, desde a erp_008, tambem os do historico que so
os CSVs de controle sabiam (erp_automation.arquivo_historico). E a memoria "ja processei"
que o wrapper do retorno de cobranca le quando CONTROLE_FONTE_RET=banco (Fase 2 de
docs/PLANO_CONTROLE_NO_BANCO.md) — no lugar do grep no CSV.

Uso:  python listar_md5.py [--com-historico] retorno_cobranca_cnab_400 retorno_bb
Exit: 0 com a lista (pode ser vazia); 1 sem banco ou tipo desconhecido, sem nada no
stdout — o wrapper entende 1 como "volte ao CSV". Com --com-historico, 3 quando a lista
saiu mas o historico dos CSVs ainda nao foi carregado no banco para estes tipos: o wrapper
junta o CSV congelado. Sem a opcao o exit e o de sempre (0), para o wrapper antigo. Nao
abre execucao: e uma consulta, nao um job.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from src.common.clients import execucao_job  # noqa: E402

SQL = ("SELECT md5 FROM erp_automation.arquivo "
       "WHERE tipo_arquivo = ANY(%s) AND md5 IS NOT NULL")
SQL_COM_HISTORICO = (SQL + " UNION SELECT md5 FROM erp_automation.arquivo_historico "
                     "WHERE tipo_arquivo = ANY(%s)")
SQL_TEM_TABELA = "SELECT to_regclass('erp_automation.arquivo_historico') IS NOT NULL"
SQL_TEM_HISTORICO = ("SELECT EXISTS (SELECT 1 FROM erp_automation.arquivo_historico "
                     "WHERE tipo_arquivo = ANY(%s))")
SAIU_SEM_HISTORICO = 3


def _um(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        linha = cur.fetchone()
        return bool(linha and linha[0])


def listar(conn, tipos: list[str]) -> tuple[list[str], bool]:
    """(md5 ordenados, o historico destes tipos esta no banco?)"""
    tem_tabela = _um(conn, SQL_TEM_TABELA)
    historico = tem_tabela and _um(conn, SQL_TEM_HISTORICO, (tipos,))
    with conn.cursor() as cur:
        if tem_tabela:
            cur.execute(SQL_COM_HISTORICO, (tipos, tipos))
        else:
            cur.execute(SQL, (tipos,))
        return sorted({str(l[0]).lower() for l in cur.fetchall() if l and l[0]}), historico


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    com_historico = "--com-historico" in args
    tipos = [a for a in args if a != "--com-historico"]
    desconhecidos = [t for t in tipos if t not in execucao_job.TIPOS_ARQUIVO]
    if not tipos or desconhecidos:
        print(f"uso: listar_md5.py [--com-historico] <tipo_arquivo>...; desconhecidos: "
              f"{desconhecidos}", file=sys.stderr)
        return 1
    try:
        conn = execucao_job.conexao_leitura("listar_md5")
    except Exception as e:  # noqa: BLE001
        print(f"sem banco: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
        return 1
    try:
        md5s, historico = listar(conn, tipos)
        for md5 in md5s:
            print(md5)
        if com_historico and not historico:
            print("historico dos CSVs ainda nao esta no banco para estes tipos", file=sys.stderr)
            return SAIU_SEM_HISTORICO
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"consulta falhou: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
        return 1
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
