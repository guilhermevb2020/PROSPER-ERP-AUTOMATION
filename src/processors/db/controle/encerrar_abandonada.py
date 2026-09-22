# -*- coding: utf-8 -*-
"""
encerrar_abandonada.py - encerra, com autor e motivo, UMA execucao que ficou `ativa` no
ledger (erp_automation.job_execucao) porque o processo morreu ou o fechamento se perdeu.

POR QUE EXISTE: desde 22/09/2026 o fechamento nunca derruba o job — se a conexao cai
nessa hora, a linha fica `ativa` de proposito e a vw_job_execucao_abandonada a denuncia
(#164, remessa de cobranca das 11h30). A paridade diaria (comparar_controle_csv_banco)
trata qualquer abandonada como divergencia (exit 3) — TODO DIA, ate alguem dizer o que
houve. Este e o unico caminho para dizer: grava status `abandonada` (nunca `sucesso`: a
ferramenta nao prova o que o processo fez; o que se sabe vai no motivo), terminado_em, e
em detalhe_json quem encerrou, por que e por qual execucao. Nunca UPDATE a mao.

Uso (ENSAIO por padrao: mostra a linha e o que faria; nao abre execucao, e so consulta):
    docker exec erp-automation python /app/src/processors/db/controle/encerrar_abandonada.py 164
Pra valer (exige ERP_OPERADOR e ERP_MOTIVO; os dois ficam na linha encerrada):
    docker exec -e ERP_OPERADOR=nome -e ERP_MOTIVO="..." erp-automation \\
        python /app/src/processors/db/controle/encerrar_abandonada.py 164 --pra-valer

Exit: 0 encerrada (ou ensaio) · 1 sem banco/erro · 2 falta ERP_OPERADOR/ERP_MOTIVO ·
3 a execucao nao esta abandonada (nao existe, ja fechada, ou ainda dentro do limite da
automacao: nada a fazer). Pra valer registra a propria execucao
(controle/encerrar_execucao_abandonada, gatilho manual, obrigatoria: sem banco, nao age).
"""
from __future__ import annotations

import argparse
import os
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from src.common.clients import execucao_job  # noqa: E402

JOB = "encerrar_execucao_abandonada"
TZ_PADRAO = "America/Sao_Paulo"
SAIU_OK, SAIU_ERRO, SAIU_USO, SAIU_NAO_ABANDONADA = 0, 1, 2, 3

SQL_ALVO = """
    SELECT j.id, j.automacao, j.job, j.gatilho, j.status,
           to_char(j.iniciado_em AT TIME ZONE %(tz)s, 'DD/MM HH24:MI'),
           (j.""" + execucao_job.SQL_ELEGIVEL_ABANDONADA + """)
      FROM erp_automation.job_execucao j
     WHERE j.id = %(id)s
"""


def descrever_alvo(conn, id_alvo: int, tz: str = TZ_PADRAO) -> dict | None:
    """A linha do alvo como esta, e se a view a considera abandonada. None: nao existe."""
    with conn.cursor() as cur:
        cur.execute(SQL_ALVO, {"id": int(id_alvo), "tz": tz})
        linha = cur.fetchone()
    if not linha:
        return None
    ident, automacao, job, gatilho, status, desde, abandonada = linha
    return {"id": int(ident), "automacao": automacao, "job": job, "gatilho": gatilho,
            "status": status, "desde": desde, "abandonada": bool(abandonada)}


def _linha(alvo: dict) -> str:
    return (f"#{alvo['id']} {alvo['automacao']}/{alvo['job']} · {alvo['gatilho']} · desde {alvo['desde']}"
            f" · status {alvo['status']} · " + ("ABANDONADA (a view a lista)" if alvo["abandonada"]
                                                 else "nao esta abandonada"))


def montar_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Encerra como `abandonada`, com autor e motivo, uma "
                                             "execucao que ficou ativa no ledger.")
    ap.add_argument("id", type=int, help="id em erp_automation.job_execucao")
    ap.add_argument("--pra-valer", action="store_true", help="grava (padrao: ensaio, so mostra)")
    ap.add_argument("--tz", default=TZ_PADRAO)
    return ap


def main(argv=None) -> int:
    args = montar_parser().parse_args(argv)
    operador = (os.environ.get("ERP_OPERADOR") or "").strip()
    motivo = (os.environ.get("ERP_MOTIVO") or "").strip()
    if args.pra_valer and not (operador and motivo):
        print("ERRO: --pra-valer exige ERP_OPERADOR e ERP_MOTIVO no ambiente (docker exec -e ...): "
              "quem encerra e por que ficam gravados na linha encerrada", file=sys.stderr)
        return SAIU_USO

    # 1. le o alvo (consulta; sem execucao propria — ensaio e so leitura)
    try:
        conn = execucao_job.conexao_leitura(JOB)
    except Exception as e:  # noqa: BLE001
        print(f"ERRO: sem banco para ler a execucao ({type(e).__name__}: {str(e)[:160]})")
        return SAIU_ERRO
    try:
        alvo = descrever_alvo(conn, args.id, args.tz)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    if alvo is None:
        print(f"execucao #{args.id} nao existe em job_execucao: nada a fazer")
        return SAIU_NAO_ABANDONADA
    print(_linha(alvo))
    if not alvo["abandonada"]:
        print("nada a fazer: so o que a vw_job_execucao_abandonada lista se encerra por aqui "
              "(ja fechada, ou ainda dentro do limite da automacao)")
        return SAIU_NAO_ABANDONADA
    if not args.pra_valer:
        print(f"ENSAIO: encerraria #{args.id} como `abandonada`"
              + (f" por {operador}: {motivo}" if operador and motivo else "")
              + " — rode com --pra-valer e ERP_OPERADOR/ERP_MOTIVO para gravar")
        return SAIU_OK

    # 2. pra valer: a propria execucao registra quem, por que e o que encerrou
    try:
        ex = execucao_job.abrir_execucao("controle", JOB, flag_ensaio=False, gatilho="manual",
                                         obrigatoria=True, operador=operador, motivo=motivo,
                                         detalhe={"alvo": args.id})
    except execucao_job.ExecucaoIndisponivel as e:
        print(f"ERRO: {e}")
        return SAIU_ERRO
    codigo, encerrada = SAIU_ERRO, None
    try:
        try:
            encerrada = execucao_job.encerrar_abandonada(ex, args.id, operador=operador, motivo=motivo)
        except execucao_job.ErroDeRegistro as e:
            print(f"ERRO: {e}")
            return SAIU_ERRO
        if encerrada:
            print(f"#{args.id} encerrada como `abandonada` por {operador}: {motivo}")
            codigo = SAIU_OK
        else:
            print(f"#{args.id} NAO encerrada: deixou de estar abandonada entre a leitura e a gravacao")
            codigo = SAIU_NAO_ABANDONADA
        return codigo
    finally:
        execucao_job.fechar_execucao(
            ex, "sucesso" if codigo in (SAIU_OK, SAIU_NAO_ABANDONADA) else "falha",
            codigo_saida=codigo, qtd_itens=1 if encerrada else 0,
            detalhe={"alvo": args.id, "encerrada": bool(encerrada)})


if __name__ == "__main__":
    sys.exit(main())
