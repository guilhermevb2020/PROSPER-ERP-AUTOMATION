# -*- coding: utf-8 -*-
"""
listar_md5.py - imprime, um por linha, os md5 dos arquivos de um ou mais tipos ja
registrados em erp_automation.arquivo. E a memoria "ja processei" que o wrapper do
retorno de cobranca le quando CONTROLE_FONTE_RET=banco (Fase 2 de
docs/PLANO_CONTROLE_NO_BANCO.md) — no lugar do grep no CSV.

Uso:  python listar_md5.py retorno_cobranca_cnab_400 retorno_bb
Exit: 0 com a lista (pode ser vazia); 1 sem banco ou tipo desconhecido, sem nada no
stdout — o wrapper entende 1 como "volte ao CSV". Nao abre execucao: e uma consulta,
nao um job.
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


def listar(conn, tipos: list[str]) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(SQL, (tipos,))
        return sorted({str(l[0]).lower() for l in cur.fetchall() if l and l[0]})


def main(argv=None) -> int:
    tipos = list(argv if argv is not None else sys.argv[1:])
    desconhecidos = [t for t in tipos if t not in execucao_job.TIPOS_ARQUIVO]
    if not tipos or desconhecidos:
        print(f"uso: listar_md5.py <tipo_arquivo>...; desconhecidos: {desconhecidos}", file=sys.stderr)
        return 1
    try:
        conn = execucao_job.conexao_leitura("listar_md5")
    except Exception as e:  # noqa: BLE001
        print(f"sem banco: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
        return 1
    try:
        for md5 in listar(conn, tipos):
            print(md5)
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
