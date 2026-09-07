# -*- coding: utf-8 -*-
"""
Conexao Postgres compartilhada do robo de boletos.

Usa env vars POSTGRES_* ja presentes no container erp-automation:
    POSTGRES_HOST / POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB / POSTGRES_PORT

Persiste em operacional.boleto_envio_log (migration 079 do process-automation).
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Iterable

import psycopg2
import psycopg2.extras


def get_conn():
    """Abre conexao Postgres com autocommit=True.

    autocommit evita que transacoes implicitas fiquem 'idle in transaction' enquanto
    o codigo Python passa muito tempo fora do DB (ex.: POST HTTP de envio de uma
    conta com 155 boletos pode levar 60s+; nesse meio tempo o Postgres mata a
    conexao por idle_in_transaction_session_timeout).

    Tambem habilita TCP keepalives para detectar/manter conexoes ativas mesmo em
    perda silenciosa de rede.
    """
    conn = psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "postgres"),
        user=os.environ.get("POSTGRES_USER", "dev_user"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        dbname=os.environ.get("POSTGRES_DB", "prosperedb"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
    )
    conn.autocommit = True
    return conn


def _parse_data_emissao(data_str: str) -> date:
    """Aceita DD/MM/YYYY (usado no CLI) e devolve date."""
    if isinstance(data_str, date):
        return data_str
    return datetime.strptime(data_str, "%d/%m/%Y").date()


def carregar_ids_enviados(conn, data_emissao_dd_mm_yyyy: str) -> set[str]:
    """IDs ja enviados (status que indica saida bem-sucedida ou provavel).

    Inclui 'ok', 'enviado_timeout' e 'incerto'. Status 'falha' e 'pulada'
    sao re-elegiveis.
    """
    d = _parse_data_emissao(data_emissao_dd_mm_yyyy)
    sql = """
        SELECT DISTINCT id_titulo
        FROM operacional.boleto_envio_log
        WHERE data_emissao = %s
          AND status IN ('ok', 'enviado_timeout', 'incerto')
    """
    with conn.cursor() as cur:
        cur.execute(sql, (d,))
        return {row[0] for row in cur.fetchall()}


def registrar(
    conn,
    *,
    ids: Iterable[str],
    conta_id: str,
    conta_label: str | None,
    modalidade: str,
    status: str,
    data_emissao_dd_mm_yyyy: str,
    valores_por_id: dict[str, float] | None = None,
    sacados_por_id: dict[str, str] | None = None,
    erro: str | None = None,
    run_id: str | None = None,
    extras: dict | None = None,
) -> int:
    """Insere uma linha por id_titulo. Retorna quantidade inserida."""
    d = _parse_data_emissao(data_emissao_dd_mm_yyyy)
    valores_por_id = valores_por_id or {}
    sacados_por_id = sacados_por_id or {}
    extras = extras or {}

    rows = []
    for i in ids:
        rows.append((
            str(i),
            str(conta_id),
            conta_label,
            (modalidade or "")[:2] or None,
            valores_por_id.get(i),
            sacados_por_id.get(i),
            d,
            status,
            erro,
            run_id,
            psycopg2.extras.Json(extras),
        ))
    if not rows:
        return 0

    sql = """
        INSERT INTO erp_automation.boleto_envio_log
            (id_titulo, conta_id, conta_label, modalidade, valor, sacado,
             data_emissao, status, erro, run_id, extras)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, rows, page_size=200)
    conn.commit()
    return len(rows)
