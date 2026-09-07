# -*- coding: utf-8 -*-
"""
Envio em LOTE de boletos (TESTES no servidor).

Modos:
  - SCAN=true (default): so descobre + imprime preview. NAO envia. Read-only.
  - DRY_RUN=true SCAN=false: prepara mas para antes do POST de envio.
  - DRY_RUN=false SCAN=false CONFIRMAR=1: envia DE VERDADE.

Conexao:
  - Tenta reusar a sessao viva (CDP em cfg.CDP_URL) — ideal.
  - Se nao houver, sobe o proprio Chrome com perfil persistente e exige sessao
    ja logada (nao tenta login automatico — quem loga e o manter_sessao.py).

Saidas:
  - preview no stdout (FASE 1)
  - log canonico em Postgres: operacional.boleto_envio_log (FASE 2)
"""

from __future__ import annotations

import os
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from src.processors.web.boletos import _config as cfg
from src.processors.web.boletos import _db
from src.processors.web.boletos import _emissao_core
from src.processors.web.boletos._sessao import esta_logado


HDR = {"content-type": "application/x-www-form-urlencoded"}
_MONEY = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")

# run_id correlaciona TODAS as linhas inseridas por esta execucao.
# Hub-orchestration tambem passa o seu proprio run_id; aceitamos via env.
RUN_ID = os.environ.get("HUB_RUN_ID") or os.environ.get("RUN_ID") or f"local-{uuid.uuid4().hex[:12]}"


# --------------------------------------------------------------------------- #
# Flags de execucao (sobrescreve cfg quando necessario)
# --------------------------------------------------------------------------- #
CONFIRMAR = os.environ.get("CONFIRMAR", "").strip().lower() in ("1", "true", "sim", "yes")
DATA = os.environ.get("DATA", "").strip() or cfg.data_alvo().strftime("%d/%m/%Y")
DATA_FINAL = os.environ.get("DATA_FINAL", "").strip() or DATA
SO_TIPO = os.environ.get("SO_TIPO", "").strip().lower()
SO_CONTA_ID = os.environ.get("SO_CONTA_ID", "").strip()
MODALIDADE = os.environ.get("MODALIDADE", "C").strip().upper()
# Filtros opcionais do POST de listagem (vazios = sem filtro)
NOP = os.environ.get("NOP", "").strip()                # numero de operacao (nop1 e nop2)
NUM_DOC = os.environ.get("NUM_DOC", "").strip()        # NumDocumento
# Whitelist de IDs do checkEnvio: envia SO os ids listados (CSV).
# Vazio = comportamento normal (envia todos os listados na conta).
SO_TITULO_IDS = set(
    x.strip() for x in os.environ.get("SO_TITULO_IDS", "").split(",") if x.strip()
)
# Envio AVULSO/cirurgico (1 titulo por NUM_DOC): so envia se o filtro casar EXATAMENTE
# 1 boleto no total. 0 = nao localizado; >1 = ambiguo (NumDocumento pode COLIDIR entre
# cedentes) => ABORTA sem enviar (fail-closed), protegendo contra boleto ao sacado errado.
# O lote diario NAO seta este flag (mantem o comportamento de enviar todos os listados).
EXIGIR_UNICO = os.environ.get("EXIGIR_UNICO", "").strip().lower() in ("1", "true", "sim", "yes")
# Emitir-se-ausente (envio avulso): se o envio nao achar boleto (tot_n=0), tenta EMITIR a
# 1a via cirurgicamente (NumDocumento+NOP, mesma guarda de unicidade) e re-lista antes de
# enviar. Recupera titulos NUNCA emitidos. So no avulso; o lote diario NAO seta este flag.
EMITIR_SE_AUSENTE = os.environ.get("EMITIR_SE_AUSENTE", "").strip().lower() in ("1", "true", "sim", "yes")


def _classes_da_conta(lab: str):
    eh_mp = lab.strip().lower().startswith(cfg.PREFIXO_MP)
    return (cfg.CLASSES_MP if eh_mp else cfg.CLASSES_PADRAO), ("MP" if eh_mp else "PADRAO")


def _connect_or_launch(p):
    """Reusa sessao viva via CDP; senao abre perfil persistente (precisa estar logado)."""
    try:
        b = p.chromium.connect_over_cdp(cfg.CDP_URL)
        print(f"  conectado na sessao viva via CDP ({cfg.CDP_URL})")
        return b.contexts[0], None
    except Exception:
        print("  sessao viva nao encontrada; abrindo perfil persistente proprio")
        cfg.ensure_dirs()
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=cfg.USER_DATA_DIR,
            headless=cfg.HEADLESS,
            channel="chrome",
            args=["--start-maximized", "--no-sandbox", "--disable-dev-shm-usage"],
            no_viewport=True,
        )
        if not esta_logado(ctx):
            raise RuntimeError(
                "Perfil persistente NAO esta logado e este script NAO faz login "
                "automatico. Suba o manter_sessao.py via VNC e logue uma vez."
            )
        return ctx, ctx


def _html_smart_validado(resposta):
    """Uma resposta de erro ou login nao pode virar lista vazia com sucesso."""
    from src.common.clients.smart_sessao import parece_deslogado

    if resposta.status != 200:
        raise RuntimeError(f"consulta ao Smart falhou: HTTP {resposta.status}")
    html = resposta.body().decode("iso-8859-1", errors="replace")
    if parece_deslogado(html):
        raise RuntimeError("sessao do Smart expirada ou resposta vazia; consulta abortada")
    return html


def _ler_contas(ctx):
    r = ctx.request.get(cfg.URL_FORM_HTTP, timeout=60_000)
    html = _html_smart_validado(r)
    pg = ctx.new_page()
    try:
        pg.set_content(html, timeout=20_000)
        opts = pg.evaluate("""()=>{const s=document.querySelector("select[name='contaCorrente']");
            return s?[...s.options].map(o=>[o.value,(o.text||'').trim()]):[];}""")
    finally:
        pg.close()
    return [
        (v, l) for v, l in opts
        if v and v != "0"
        and "selecione" not in l.lower()
        and "sem conta" not in l.lower()
    ]


def _ler_template(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def _body_lista(conta_id: str, conta_lab: str) -> str:
    b = _ler_template(cfg.T_LISTA_PATH)
    d1 = quote(DATA, safe="")
    d2 = quote(DATA_FINAL, safe="")
    b = re.sub(r"(?<=[?&])contaCorrente=[^&]*", f"contaCorrente={conta_id}", b)
    b = re.sub(r"(?<=[?&])DtInicial=[^&]*", f"DtInicial={d1}", b)
    b = re.sub(r"(?<=[?&])DtFinal=[^&]*", f"DtFinal={d2}", b)
    b = re.sub(r"(?<=[?&])nop1=[^&]*", f"nop1={quote(NOP, safe='')}", b)
    b = re.sub(r"(?<=[?&])nop2=[^&]*", f"nop2={quote(NOP, safe='')}", b)
    b = re.sub(r"(?<=[?&])NumDocumento=[^&]*", f"NumDocumento={quote(NUM_DOC, safe='')}", b)
    b = re.sub(r"(?<=[?&])modalidadeS=[^&]*", f"modalidadeS={MODALIDADE}", b)
    b = re.sub(r"&?sClasseRisco%5B%5D=[^&]*", "", b)
    classes, _tipo = _classes_da_conta(conta_lab)
    b += "".join(f"&sClasseRisco%5B%5D={c}" for c in classes)
    return b


def _titulos_conta(ctx, conta_id: str, conta_lab: str):
    r = ctx.request.post(
        cfg.URL_LISTA_HTTP,
        data=_body_lista(conta_id, conta_lab),
        headers=HDR,
        timeout=120_000,
    )
    html = _html_smart_validado(r)
    pg = ctx.new_page()
    try:
        pg.set_content(html, timeout=20_000)
        rows = pg.evaluate("""()=>{const cb=document.querySelector("input[name='checkEnvio']");
            if(!cb) return [];
            const tb=cb.closest('table');
            return [...tb.querySelectorAll('tr')].map(tr=>{
                const e=tr.querySelector("input[name='checkEnvio']");
                if(!e) return null;
                const cells=[...tr.children].map(td=>(td.innerText||'').replace(/\\s+/g,' ').trim());
                return {id:e.value, cells};}).filter(Boolean);}""")
    finally:
        pg.close()
    out = []
    for row in rows:
        cells = row["cells"]
        val = 0.0
        for c in cells:
            if _MONEY.fullmatch(c):
                val = float(c.replace(".", "").replace(",", "."))
                break
        sac = ""
        idx = [i for i, c in enumerate(cells) if re.fullmatch(r"\d{2}/\d{2}/\d{4}", c)]
        if len(idx) >= 2 and idx[1] + 1 < len(cells):
            sac = cells[idx[1] + 1][:60]
        # campos uteis pra debug/conferencia (sem custo extra; ja temos as cells)
        datas = [cells[i] for i in idx]                 # [emissao, vencimento] em geral
        emissao = datas[0] if len(datas) >= 1 else ""
        vencimento = datas[1] if len(datas) >= 2 else ""
        out.append({
            "id": row["id"],
            "valor": val,
            "sacado": sac,
            "emissao": emissao,
            "vencimento": vencimento,
            "cells": cells,
        })
    return out


def _body_envio(ids):
    b = _ler_template(cfg.T_ENVIO_PATH)
    checks = "".join(f"{i}%2B" for i in ids)
    b = re.sub(r"(?<=[?&])Checks=[^&]*", f"Checks={checks}", b)
    b = re.sub(r"(?<=[?&])checkEnvio=[^&]*", f"checkEnvio={ids[0]}", b)
    for x in ids[1:]:
        b += f"&checkEnvio={x}"
    b = re.sub(r"(?<=[?&])op1=[^&]*", "op1=", b)
    b = re.sub(r"(?<=[?&])op2=[^&]*", "op2=", b)
    b = re.sub(r"(?<=[?&])modalidadeS=[^&]*", f"modalidadeS={MODALIDADE}", b)
    return b


def _carregar_enviados(db_conn) -> set[str]:
    """ids ja enviados nesta data (nao re-enviar) — fonte: Postgres."""
    return _db.carregar_ids_enviados(db_conn, DATA)


def _registrar(
    db_conn,
    *,
    conta_id: str,
    conta_label: str | None,
    ids: list,
    status: str,
    titulos_lookup: dict[str, dict],
    erro: str | None = None,
) -> None:
    """Persiste o resultado do envio em operacional.boleto_envio_log."""
    valores = {i: titulos_lookup.get(i, {}).get("valor") for i in ids}
    sacados = {i: titulos_lookup.get(i, {}).get("sacado") for i in ids}
    _db.registrar(
        db_conn,
        ids=ids,
        conta_id=conta_id,
        conta_label=conta_label,
        modalidade=MODALIDADE,
        status=status,
        data_emissao_dd_mm_yyyy=DATA,
        valores_por_id=valores,
        sacados_por_id=sacados,
        erro=erro,
        run_id=RUN_ID,
        extras={"data_final": DATA_FINAL, "nop": NOP, "num_doc": NUM_DOC},
    )


def _descobrir_e_preview(ctx, contas, periodo):
    """FASE 1: lista os boletos a enviar por conta e imprime o preview.

    Retorna (dados, tot_n, tot_v). Extraido em funcao para poder RE-LISTAR apos uma
    emissao avulsa (EMITIR_SE_AUSENTE) sem duplicar codigo.
    """
    dados = {}
    for v, lab in contas:
        cls, tipo = _classes_da_conta(lab)
        try:
            tit = _titulos_conta(ctx, v, lab)
        except Exception as e:
            print(f"   - {lab} ({v}): ERRO ao listar ({e})")
            continue
        if tit:
            dados[v] = {"lab": lab, "titulos": tit, "tipo": tipo, "classes": cls}

    print(f"\n  PREVIEW {periodo}")
    print(f"  {'conta':<28} {'id':<6} {'tipo':<7} {'boletos':>7} {'valor (R$)':>15} {'sacados':>7}")
    print("  " + "-" * 80)
    tot_n = 0
    tot_v = 0.0
    for v, d in sorted(dados.items(), key=lambda x: -len(x[1]["titulos"])):
        n = len(d["titulos"])
        val = sum(t["valor"] for t in d["titulos"])
        sacs = {t["sacado"] for t in d["titulos"]}
        tot_n += n
        tot_v += val
        print(f"  {d['lab'][:28]:<28} {v:<6} {d['tipo']:<7} {n:>7} {val:>15,.2f} {len(sacs):>7}")
    print(f"\n  TOTAL: {tot_n} boleto(s) | R$ {tot_v:,.2f} | {len(dados)} conta(s) com boleto")
    return dados, tot_n, tot_v


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    periodo = DATA if DATA == DATA_FINAL else f"{DATA} a {DATA_FINAL}"
    if cfg.SCAN:
        modo = "SCAN (read-only, nao envia)"
    elif cfg.DRY_RUN or not CONFIRMAR:
        modo = "DRY (preview, nao envia)"
    else:
        modo = "ENVIO REAL"
    print(f"\n===== ROBO BOLETOS (TESTE) | EMISSAO {periodo} | tipo={SO_TIPO or 'todas'} "
          f"| modalidade={MODALIDADE} | MODO={modo} =====")

    with sync_playwright() as p:
        try:
            ctx, prop = _connect_or_launch(p)
        except RuntimeError as e:
            print(f"\n[ERRO] {e}")
            sys.exit(2)
        try:
            contas = _ler_contas(ctx)
            print(f"  {len(contas)} conta(s) no dropdown")
            if SO_CONTA_ID:
                contas = [(v, l) for v, l in contas if v == SO_CONTA_ID]
                print(f"  (SO_CONTA_ID={SO_CONTA_ID}) -> {len(contas)} conta(s): "
                      f"{[l for _, l in contas]}")
            elif cfg.SO_CONTA:
                contas = [(v, l) for v, l in contas if l.strip().lower() == cfg.SO_CONTA]
                print(f"  (SO_CONTA={cfg.SO_CONTA}) -> {len(contas)} conta(s): "
                      f"{[l for _, l in contas]}")
            if SO_TIPO in ("padrao", "mp"):
                contas = [
                    (v, l) for v, l in contas
                    if _classes_da_conta(l)[1].lower() == SO_TIPO
                ]
                print(f"  (SO_TIPO={SO_TIPO}) -> {len(contas)} conta(s)")
            if cfg.MAX_CONTAS > 0:
                contas = contas[:cfg.MAX_CONTAS]
                print(f"  (MAX_CONTAS={cfg.MAX_CONTAS}) -> {len(contas)} conta(s)")

            # ---------- FASE 1: descobrir ----------
            dados, tot_n, tot_v = _descobrir_e_preview(ctx, contas, periodo)

            # ---------- FASE 1 termina aqui se for SCAN/DRY ----------
            if cfg.SCAN:
                print("\n  [SCAN] read-only — fim.")
                return
            if cfg.DRY_RUN or not CONFIRMAR:
                print("\n  [DRY] preview apenas. Para enviar de verdade:")
                print("    DRY_RUN=false SCAN=false CONFIRMAR=1 python -m ...")
                return

            # ---------- Emitir-se-ausente (envio avulso) ----------
            # Se o envio nao achou boleto (nunca emitido, ex.: cedente 0%) e EMITIR_SE_AUSENTE,
            # tenta EMITIR a 1a via cirurgicamente (NumDocumento+NOP, guarda de unicidade na
            # emissao) e RE-LISTA. Fail-closed: se a emissao nao casar exatamente 1, nao emite
            # e a guarda EXIGIR_UNICO abaixo aborta (tot_n continua 0).
            if EMITIR_SE_AUSENTE and tot_n == 0 and NUM_DOC:
                print(f"\n  [EMITIR_SE_AUSENTE] envio sem boleto — tentando EMITIR 1a via "
                      f"NUM_DOC={NUM_DOC} NOP={NOP or '-'}")
                try:
                    res = _emissao_core.emitir_por_documento(
                        ctx, num_doc=NUM_DOC, nop=(NOP or None), dry_run=False)
                except Exception as e:
                    res = {"status": "erro_emissao", "erro": str(e)[:150]}
                print(f"  [EMITIR] status={res.get('status')} total={res.get('total')} "
                      f"conta={res.get('conta', '-')}"
                      + (f" erro={res.get('erro')}" if res.get("erro") else ""))
                if res.get("status") == "emitido":
                    time.sleep(cfg.PAUSA_ENTRE_CONTAS)
                    print("  [re-lista pos-emissao]")
                    dados, tot_n, tot_v = _descobrir_e_preview(ctx, contas, periodo)

            # ---------- Guarda de unicidade (envio avulso) ----------
            # Fail-closed: so segue para o envio se o filtro casou EXATAMENTE 1 boleto.
            # tot_n==0 (nao emitido/nao localizado) OU tot_n>1 (ambiguo — doc pode colidir
            # entre cedentes) => aborta sem enviar. Protege contra boleto ao sacado errado.
            if EXIGIR_UNICO and tot_n != 1:
                print(f"\n  [EXIGIR_UNICO] esperava 1 boleto, encontrou {tot_n} "
                      f"-> ABORTADO (fail-closed, nada enviado).")
                return

            # ---------- FASE 2: enviar (so com CONFIRMAR=1) ----------
            if not dados:
                print("  nada a enviar.")
                return
            if tot_n > cfg.TETO:
                print(f"\n  [TRAVA] {tot_n} boletos > TETO={cfg.TETO}. ABORTADO por seguranca.")
                return
            print(f"\n  ===== FASE 2: ENVIANDO (conta a conta) | run_id={RUN_ID} =====")
            db_conn = _db.get_conn()
            try:
                enviados = _carregar_enviados(db_conn)
                for v, d in dados.items():
                    titulos_lookup = {t["id"]: t for t in d["titulos"]}
                    ids = [t["id"] for t in d["titulos"] if t["id"] not in enviados]
                    # Whitelist de titulos especifica (caso de teste, envio cirurgico)
                    if SO_TITULO_IDS:
                        antes = len(ids)
                        ids = [i for i in ids if i in SO_TITULO_IDS]
                        print(f"   [SO_TITULO_IDS] conta {v}: filtrou {antes} -> {len(ids)} id(s)")
                    ja = len(d["titulos"]) - len(ids)
                    if not ids:
                        print(f"   - {d['lab']} ({v}): todos {ja} ja enviados -> PULANDO")
                        continue
                    status = "falha"
                    erro_msg = None
                    try:
                        r = ctx.request.post(
                            cfg.URL_ENVIO_HTTP,
                            data=_body_envio(ids),
                            headers=HDR,
                            timeout=cfg.TIMEOUT_ENVIO_MS,
                        )
                        txt = r.body().decode("iso-8859-1", errors="replace")
                        if r.status == 200 and ("frmprintcobranca" in txt or "caminho=" in txt):
                            status = "ok"
                        elif r.status == 200:
                            status = "incerto"
                            erro_msg = f"HTTP 200 sem marcador de sucesso ({txt[:120]})"
                        else:
                            status = "falha"
                            erro_msg = f"HTTP {r.status}: {txt[:120]}"
                    except Exception as e:
                        if "timeout" in str(e).lower():
                            status = "enviado_timeout"
                            erro_msg = str(e)[:200]
                            print(f"   - {d['lab']} ({v}): TIMEOUT -> assumindo ENVIADO")
                        else:
                            status = "falha"
                            erro_msg = str(e)[:200]
                            print(f"   - {d['lab']} ({v}): EXCECAO {erro_msg[:70]}")
                    # Reconecta se conn caiu durante o POST longo.
                    try:
                        _registrar(
                            db_conn, conta_id=v, conta_label=d['lab'],
                            ids=ids, status=status,
                            titulos_lookup=titulos_lookup, erro=erro_msg,
                        )
                    except Exception as db_err:
                        print(f"   [db] conn caiu ({db_err}), reconectando...")
                        try: db_conn.close()
                        except Exception: pass
                        db_conn = _db.get_conn()
                        _registrar(
                            db_conn, conta_id=v, conta_label=d['lab'],
                            ids=ids, status=status,
                            titulos_lookup=titulos_lookup, erro=erro_msg,
                        )
                    print(f"   - {d['lab']} ({v}): {len(ids)} titulo(s) (+{ja} ja feitos) "
                          f"-> {status.upper()}", flush=True)
                    time.sleep(cfg.PAUSA_ENTRE_CONTAS)
            finally:
                try: db_conn.close()
                except Exception: pass

            print("\n  ===== FIM =====")
        finally:
            if prop is not None:
                try:
                    prop.close()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
