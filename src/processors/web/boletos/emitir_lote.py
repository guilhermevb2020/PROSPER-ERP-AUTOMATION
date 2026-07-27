# -*- coding: utf-8 -*-
"""
Robo de EMISSAO de boletos no Smart (entrypoint).

Modos:
  - SCAN_EMISSAO=true (default): lista pendentes em todas as contas, NAO emite.
  - DRY_RUN_EMISSAO=true SCAN_EMISSAO=false: prepara mas NAO emite.
  - DRY_RUN_EMISSAO=false SCAN_EMISSAO=false CONFIRMAR=1: emite DE VERDADE.

Fluxo do robo:
  1) Conecta na sessao viva (CDP 9222) — mesmo Chrome usado pelo enviar_lote.
  2) Le dropdown contaCorrente via HTTP (mais rapido que Playwright UI).
  3) Para cada conta:
       - 1a passada: lista + (se CONFIRMAR=1) emite
       - 2a passada (PASSADAS>=2): verifica se sumiu. Se nao, marca alerta.
  4) Grava resultado em operacional.boleto_emissao_log.

Tabelas/dependencias compartilhadas com o enviar_lote:
  - sessao Smart (mesmo CDP)
  - _config.py (URLs base, paths)
  - _db.py (conexao Postgres)
"""

from __future__ import annotations

import os
import sys
import time
import uuid

from playwright.sync_api import sync_playwright

from src.processors.web.boletos import _config as cfg
from src.processors.web.boletos import _db
from src.processors.web.boletos import _emissao_config as ec
from src.processors.web.boletos._emissao_core import emitir_conta_http, listar_contas_dropdown
from src.processors.web.boletos._sessao import esta_logado, login_automatico_capsolver


# --------------------------------------------------------------------------- #
# Flags
# --------------------------------------------------------------------------- #
CONFIRMAR = os.environ.get("CONFIRMAR", "").strip().lower() in ("1", "true", "sim", "yes")

RUN_ID = os.environ.get("HUB_RUN_ID") or os.environ.get("RUN_ID") or f"local-{uuid.uuid4().hex[:12]}"


def _modo() -> str:
    if ec.SCAN:
        return "SCAN (read-only, nao emite)"
    if ec.DRY_RUN or not CONFIRMAR:
        return "DRY (preview, nao emite)"
    return "EMISSAO REAL"


def _registrar_log(
    conn,
    *,
    conta_id: str,
    conta_label: str,
    grupo: str,
    classes_risco: list[str] | None,
    radio_em_nome: str | None,
    qtd_titulos: int,
    qtd_apos_2pass: int | None,
    passada: int,
    status: str,
    erro: str | None = None,
    content_type: str | None = None,
    extras: dict | None = None,
) -> None:
    """Insere linha em operacional.boleto_emissao_log."""
    sql = """
        INSERT INTO operacional.boleto_emissao_log
            (conta_id, conta_label, grupo, classes_risco, radio_em_nome,
             qtd_titulos, qtd_apos_2pass, passada, status, erro,
             content_type, run_id, extras)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    import psycopg2.extras
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                str(conta_id),
                conta_label,
                grupo,
                classes_risco,
                radio_em_nome,
                int(qtd_titulos or 0),
                int(qtd_apos_2pass) if qtd_apos_2pass is not None else None,
                int(passada),
                status,
                erro,
                content_type,
                RUN_ID,
                psycopg2.extras.Json(extras or {}),
            ),
        )


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"\n===== ROBO EMISSAO BOLETOS | MODO={_modo()} | run_id={RUN_ID} =====")

    with sync_playwright() as p:
        # Conecta no Chrome persistente (mesmo que o enviar_lote usa)
        try:
            browser = p.chromium.connect_over_cdp(cfg.CDP_URL)
            ctx = browser.contexts[0]
            print(f"  conectado na sessao viva via CDP ({cfg.CDP_URL})")
        except Exception as exc:
            print(f"\n[ERRO] nao consegui conectar no CDP {cfg.CDP_URL}: {exc}")
            print("       Verifique se manter_sessao esta rodando.")
            sys.exit(2)

        # Fallback defesa-em-profundidade: se sessao caiu, tenta CapSolver antes
        # de abortar (mesmo padrao do healthcheck). Healthcheck cuida do caso
        # normal, mas se a task rodar entre 2 ticks do healthcheck a sessao
        # pode estar down — relogar aqui evita falhar a task.
        if not esta_logado(ctx):
            print("\n[sessao] caiu — tentando login automatico via CapSolver")
            try:
                autologin_ok = login_automatico_capsolver(ctx)
            except Exception as exc:
                print(f"[sessao] excecao no login automatico: {exc}")
                autologin_ok = False
            if not autologin_ok:
                print("\n[ERRO] login automatico falhou; nao foi possivel reativar a sessao.")
                print("       Logue via VNC ou rode boletos_healthcheck manualmente.")
                sys.exit(3)
            print("[sessao] login automatico OK — sessao reativada")

        # 1) Lista contas
        try:
            contas = listar_contas_dropdown(ctx)
        except Exception as exc:
            print(f"\n[ERRO] ao listar contas: {exc}")
            sys.exit(4)

        print(f"  {len(contas)} conta(s) no dropdown")

        # Filtros opcionais
        if ec.SO_CONTA_ID:
            contas = [(v, l) for v, l in contas if v == ec.SO_CONTA_ID]
            print(f"  (SO_CONTA_ID={ec.SO_CONTA_ID}) -> {len(contas)} conta(s)")
        if ec.SO_GRUPO in (ec.GRUPO_CONVENCIONAL, ec.GRUPO_OCULTO):
            contas = [(v, l) for v, l in contas if ec.classificar_conta(l) == ec.SO_GRUPO]
            print(f"  (SO_GRUPO={ec.SO_GRUPO}) -> {len(contas)} conta(s)")
        if ec.CONTAS_IGNORAR:
            antes = len(contas)
            contas = [(v, l) for v, l in contas if l.strip().lower() not in ec.CONTAS_IGNORAR]
            if antes != len(contas):
                print(f"  (CONTAS_IGNORAR) {antes - len(contas)} conta(s) puladas")

        # Trava de seguranca por quantidade de contas
        if len(contas) > ec.TETO_CONTAS and not ec.SCAN and not ec.DRY_RUN:
            print(f"\n[TRAVA] {len(contas)} contas > TETO_CONTAS={ec.TETO_CONTAS}. ABORTADO.")
            sys.exit(5)

        if not contas:
            print("  nenhuma conta para processar.")
            return

        # Ordena: convencionais primeiro
        contas.sort(key=lambda x: (ec.classificar_conta(x[1]) != ec.GRUPO_CONVENCIONAL, x[1].lower()))

        # 2) Loop principal
        db_conn = _db.get_conn() if not ec.SCAN else None
        resumo = {
            "ok": 0, "vazio": 0, "alerta_sem_efeito": 0,
            "falha": 0, "preview": 0,
        }
        tot_titulos_emitidos = 0

        try:
            for i, (conta_value, conta_label) in enumerate(contas, 1):
                grupo = ec.classificar_conta(conta_label)
                cfg_grupo = ec.CONFIG_GRUPO[grupo]
                ident = f"[{i}/{len(contas)}] {grupo}: {conta_label[:35]}"
                print(f"\n--- {ident} ---")

                # 1a passada
                r1 = emitir_conta_http(
                    ctx,
                    conta_value=conta_value,
                    conta_label=conta_label,
                    grupo=grupo,
                    dry_run=(ec.SCAN or ec.DRY_RUN or not CONFIRMAR),
                )

                n1 = r1.get("titulos") or 0
                if not r1.get("ok"):
                    print(f"  P1 FALHA: {r1.get('erro')}")
                    if db_conn:
                        _registrar_log(
                            db_conn,
                            conta_id=conta_value,
                            conta_label=conta_label,
                            grupo=grupo,
                            classes_risco=cfg_grupo["classes"],
                            radio_em_nome=cfg_grupo["radio"],
                            qtd_titulos=n1,
                            qtd_apos_2pass=None,
                            passada=1,
                            status="falha",
                            erro=str(r1.get("erro"))[:500],
                        )
                        db_conn.commit() if hasattr(db_conn, "commit") else None
                    resumo["falha"] += 1
                    time.sleep(ec.DELAY_ENTRE_CONTAS)
                    continue

                # SCAN: lista e segue
                if ec.SCAN or ec.DRY_RUN or not CONFIRMAR:
                    status = "preview"
                    print(f"  P1 [{status.upper()}] {n1} titulo(s) pendente(s) "
                          f"(classes={cfg_grupo['classes']} radio={cfg_grupo['radio']})")
                    if db_conn:
                        _registrar_log(
                            db_conn, conta_id=conta_value, conta_label=conta_label,
                            grupo=grupo, classes_risco=cfg_grupo["classes"],
                            radio_em_nome=cfg_grupo["radio"], qtd_titulos=n1,
                            qtd_apos_2pass=None, passada=1, status=status,
                        )
                    resumo["preview"] += 1
                    time.sleep(ec.DELAY_ENTRE_CONTAS)
                    continue

                # REAL: 1a passada emitiu
                if r1.get("vazio"):
                    print(f"  P1 VAZIO (nada a emitir)")
                    if db_conn:
                        _registrar_log(
                            db_conn, conta_id=conta_value, conta_label=conta_label,
                            grupo=grupo, classes_risco=cfg_grupo["classes"],
                            radio_em_nome=cfg_grupo["radio"], qtd_titulos=0,
                            qtd_apos_2pass=None, passada=1, status="vazio",
                        )
                    resumo["vazio"] += 1
                    time.sleep(ec.DELAY_ENTRE_CONTAS)
                    continue

                print(f"  P1 OK: {n1} titulo(s) emitido(s) | ct={r1.get('content_type','?')[:40]}")
                tot_titulos_emitidos += n1

                # 2a passada (se PASSADAS>=2): verifica se sumiu
                qtd_apos = None
                if ec.PASSADAS >= 2:
                    time.sleep(ec.DELAY_ENTRE_PASSADAS)
                    r2 = emitir_conta_http(
                        ctx,
                        conta_value=conta_value,
                        conta_label=conta_label,
                        grupo=grupo,
                        dry_run=True,  # 2a passada eh sempre read-only (so confere)
                    )
                    qtd_apos = r2.get("titulos") or 0
                    if not r2.get("ok"):
                        print(f"  P2 ERRO ao verificar: {r2.get('erro')}")
                    elif qtd_apos > 0:
                        print(f"  P2 ALERTA: ainda mostra {qtd_apos} pendentes — emissao pode NAO ter surtido efeito!")
                        if db_conn:
                            _registrar_log(
                                db_conn, conta_id=conta_value, conta_label=conta_label,
                                grupo=grupo, classes_risco=cfg_grupo["classes"],
                                radio_em_nome=cfg_grupo["radio"], qtd_titulos=n1,
                                qtd_apos_2pass=qtd_apos, passada=2,
                                status="alerta_sem_efeito",
                                content_type=r1.get("content_type"),
                            )
                        resumo["alerta_sem_efeito"] += 1
                        time.sleep(ec.DELAY_ENTRE_CONTAS)
                        continue
                    else:
                        print(f"  P2 OK: 0 pendentes — emissao confirmada")

                # P1 OK + P2 OK
                if db_conn:
                    _registrar_log(
                        db_conn, conta_id=conta_value, conta_label=conta_label,
                        grupo=grupo, classes_risco=cfg_grupo["classes"],
                        radio_em_nome=cfg_grupo["radio"], qtd_titulos=n1,
                        qtd_apos_2pass=qtd_apos, passada=1, status="ok",
                        content_type=r1.get("content_type"),
                    )
                resumo["ok"] += 1
                time.sleep(ec.DELAY_ENTRE_CONTAS)
        finally:
            if db_conn:
                try:
                    db_conn.close()
                except Exception:
                    pass

        # Resumo final
        print(f"\n===== RESUMO =====")
        for k, v in resumo.items():
            print(f"  {k:<22} {v}")
        if not ec.SCAN and CONFIRMAR:
            print(f"  total_titulos_emitidos {tot_titulos_emitidos}")
        print(f"  run_id={RUN_ID}")


if __name__ == "__main__":
    main()
