# -*- coding: utf-8 -*-
"""
placar.py - mede a ACURACIA do Robo 7 comparando o veredito dele com o que o
operador REALMENTE fez com a operacao.

E a evidencia para decidir se o robo pode sair do DRY e ir para o servidor.

Como funciona: le os RESUMOs do log do --loop (o ultimo veredito de cada op) e
confronta com o estado final no espelho do banco (trs.operacao_desagio):

  robo PASSARIA  + op finalizada      -> CONCORDA   (o robo teria feito o mesmo)
  robo PASSARIA  + op NAO finalizada  -> ADIANTADO  (ninguem finalizou ainda; nao e erro,
                                                     mas se persistir vale entender por que)
  robo BARRADA   + op NAO finalizada  -> CONCORDA   (os dois seguraram)
  robo BARRADA   + op finalizada      -> DIVERGE    <<< os casos que importam:
                                                     saiu apesar da pendencia apontada

DIVERGE nao significa que o robo errou - hoje (28/08) as duas divergencias foram
operacoes que sairam ERRADAS (conta de origem trocada e pagamento zerado). Por
isso o relatorio mostra a conta e o valor pago de cada uma: e o que permite
julgar quem estava certo.

Uso (rodar da RAIZ):
  python finalizar_operacao/placar.py
  python finalizar_operacao/placar.py --log logs/r7_loop.log --dia 2026-08-28
"""
import argparse
import os
import re
import sys
from collections import OrderedDict

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(_AQUI)
for _p in (_AQUI, os.path.join(_RAIZ, "credito")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import r7_config as cfg  # noqa: E402

_LINHA_OP = re.compile(r"^  op (\d+)\s{2,}(.*?)\s{2,}(PASSARIA|BARRADA.*|ERRO -.*|FINALIZADA.*)\s*$")
_PENDENCIA = re.compile(r"^\s{5,}- (.+)$")


def ler_vereditos(caminho):
    """Ultimo veredito de cada op no log. {op: {cedente, veredito, pendencias}}."""
    vereditos = OrderedDict()
    atual = None
    with open(caminho, encoding="utf-8", errors="replace") as fh:
        for linha in fh:
            m = _LINHA_OP.match(linha.rstrip("\n"))
            if m:
                op, cedente, veredito = m.group(1), m.group(2).strip(), m.group(3).strip()
                atual = {"cedente": cedente, "veredito": veredito, "pendencias": []}
                vereditos[op] = atual           # sobrescreve: fica o ultimo ciclo
                continue
            if atual is not None:
                p = _PENDENCIA.match(linha.rstrip("\n"))
                if p:
                    atual["pendencias"].append(p.group(1).strip())
                elif linha.strip().startswith("op ") or not linha.strip():
                    pass
    return vereditos


def estado_no_banco(ops):
    """{op: {etapa, concluida, conta, valor_pago, data_fin}} do espelho."""
    if not ops:
        return {}
    try:
        import psycopg2
        import config as r1_config
        conn = psycopg2.connect(connect_timeout=r1_config.DB_CONNECT_TIMEOUT,
                                **r1_config.DB_CONFIG)
    except Exception as e:
        print(f"[ERRO] banco inacessivel: {e}")
        return {}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id_operacao, etapa, flag_operacao_concluida, conta_bancaria_pg, "
            "valor_pagamento_operacao, data_finalizacao "
            "FROM trs.operacao_desagio WHERE id_operacao = ANY(%s)",
            ([int(o) for o in ops if str(o).isdigit()],))
        return {str(r[0]): {"etapa": r[1], "concluida": r[2], "conta": r[3],
                            "valor_pago": r[4], "data_fin": r[5]} for r in cur.fetchall()}
    finally:
        conn.close()


def classificar(veredito, banco):
    """-> (classe, explicacao). Classificacao CRUA, so pelo log + banco."""
    if veredito.startswith("ERRO"):
        return "ERRO", "o robo nao conseguiu concluir a checagem"
    if not banco:
        return "SEM_DADO", "operacao nao esta no espelho do banco"
    finalizada = bool(banco.get("concluida")) or banco.get("etapa") == "CONCLUIDA"
    aprovou = veredito.startswith("PASSARIA") or veredito.startswith("FINALIZADA")
    if aprovou and finalizada:
        return "CONCORDA", "robo aprovaria; operador finalizou"
    if aprovou and not finalizada:
        return "ADIANTADO", f"robo aprovaria; ainda em '{banco.get('etapa')}'"
    if not aprovou and not finalizada:
        return "CONCORDA", f"robo barraria; segue em '{banco.get('etapa')}'"
    return "DIVERGE", "robo barraria, mas foi FINALIZADA"


# --------------------------------------------------------------------------- #
# Reverificacao: separa divergencia REAL de "resolveram depois"
# --------------------------------------------------------------------------- #
# Sem isso o placar MENTE: o veredito guardado e o do ULTIMO ciclo em que o robo
# olhou a op. Se as assinaturas chegaram DEPOIS (ou o loop estava parado), a op
# aparece como "barrada mas finalizada" sendo que ela ficou legitima no meio do
# caminho. Por isso conferimos AGORA como a operacao terminou de fato.
def _pagamento_suspeito(banco):
    """True se o pagamento gravado no banco esta claramente errado."""
    conta = (banco.get("conta") or "").strip().upper()
    valor = banco.get("valor_pago")
    if not conta:
        return True, "sem conta bancaria de pagamento"
    if conta != _norm_conta(cfg.CONTA_ORIGEM_ESPERADA):
        return True, f"conta de pagamento = '{banco.get('conta')}'"
    if valor is not None and float(valor) == 0:
        return True, "valor de pagamento = 0,00"
    return False, ""


def _norm_conta(s):
    return " ".join(str(s or "").split()).strip().upper()


def reverificar(ctx, op, veredito_pendencias):
    """Confere AGORA se a op esta conforme. -> (ok, motivo)."""
    import checagem_docs
    tem_pend_doc = any(p.startswith(("Aditivo", "Nota promiss", "Duplicata", "Letra"))
                       for p in veredito_pendencias)
    if not tem_pend_doc:
        return True, "pendencia era so de pagamento"
    try:
        import classe_risco_tool as crt
        from smart_session import Smart
        dados = crt.carregar_operacao(Smart.attach(ctx), op)
        tipos = [t.get("tipoTitulo", "") for t in dados["titulos"]]
    except Exception:
        tipos = []
    try:
        r = checagem_docs.conferir(ctx, op, tipos)
    except Exception as e:
        return None, f"nao consegui reverificar: {str(e)[:80]}"
    if r["ok"]:
        return True, "documentos JA estao assinados (foram assinados depois)"
    return False, "documentos CONTINUAM pendentes: " + "; ".join(r["pendencias"])[:160]


def main():
    ap = argparse.ArgumentParser(description="Acuracia do Robo 7 (veredito x realidade).")
    ap.add_argument("--log", default=os.path.join("logs", "r7_loop.log"))
    ap.add_argument("--dia", default="", help="so ops finalizadas nesta data (AAAA-MM-DD)")
    ap.add_argument("--cdp", default=str(cfg.CDP_PORT))
    ap.add_argument("--sem-reverificar", action="store_true",
                    help="nao reconsulta o doc2you (mais rapido, porem o placar MENTE:"
                         " conta como divergencia o que so foi assinado depois)")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not os.path.exists(args.log):
        print(f"[ERRO] log nao encontrado: {args.log}")
        return 2
    vereditos = ler_vereditos(args.log)
    if not vereditos:
        print(f"[ERRO] nenhum veredito lido de {args.log}")
        return 1
    banco = estado_no_banco(list(vereditos))

    brutos = []
    for op, v in vereditos.items():
        b = banco.get(op, {})
        if args.dia and b.get("data_fin") and str(b["data_fin"]) != args.dia:
            continue
        classe, explic = classificar(v["veredito"], b)
        brutos.append([op, v, b, classe, explic])

    # REVERIFICA as divergencias (ver comentario em reverificar()).
    candidatos = [x for x in brutos if x[3] == "DIVERGE"]
    if candidatos and not args.sem_reverificar:
        print(f"  reverificando {len(candidatos)} divergencia(s) no doc2you...\n")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                ctx = p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.cdp}").contexts[0]
            except Exception as e:
                print(f"  [aviso] CDP {args.cdp} indisponivel ({str(e)[:60]}) - "
                      "as divergencias ficam SEM reverificacao")
                ctx = None
            for item in candidatos:
                if ctx is None:
                    break
                op, v, b = item[0], item[1], item[2]
                ok_doc, motivo = reverificar(ctx, op, v["pendencias"])
                susp, motivo_pag = _pagamento_suspeito(b)
                if susp:
                    item[3], item[4] = "DIVERGE", f"FINALIZADA com {motivo_pag}"
                elif ok_doc is True:
                    item[3], item[4] = "RESOLVIDO_DEPOIS", motivo
                elif ok_doc is False:
                    item[3], item[4] = "DIVERGE", motivo
                else:
                    item[3], item[4] = "SEM_DADO", motivo

    grupos = {}
    for op, v, b, classe, explic in brutos:
        grupos.setdefault(classe, []).append((op, v, b, explic))

    total = sum(len(v) for v in grupos.values())
    print(f"=== PLACAR DO ROBO 7 | {total} operacao(oes) | log: {args.log} ===\n")
    for classe in ("CONCORDA", "RESOLVIDO_DEPOIS", "DIVERGE", "ADIANTADO", "ERRO", "SEM_DADO"):
        itens = grupos.get(classe, [])
        if not itens:
            continue
        print(f"  {classe}: {len(itens)}")
    # RESOLVIDO_DEPOIS conta como acerto: o robo barrou, assinaram depois e a op
    # foi finalizada - o robo estava certo NO MOMENTO em que olhou. ADIANTADO e
    # ERRO ficam FORA da base: ainda nao ha desfecho p/ comparar.
    conc = len(grupos.get("CONCORDA", [])) + len(grupos.get("RESOLVIDO_DEPOIS", []))
    div = len(grupos.get("DIVERGE", []))
    base = conc + div
    if base:
        print(f"\n  concordancia: {conc}/{base} = {100.0 * conc / base:.0f}%"
              f"   ({div} divergencia(s) REAL(is))")
        print("  (RESOLVIDO_DEPOIS = robo barrou, assinaram depois e finalizaram "
              "- nao e erro do robo)")

    for classe, titulo in (("DIVERGE", "DIVERGENCIAS REAIS - finalizadas com a pendencia ainda de pe"),
                           ("ADIANTADO", "APROVADAS PELO ROBO E AINDA NAO FINALIZADAS"),
                           ("ERRO", "CHECAGENS QUE FALHARAM")):
        itens = grupos.get(classe, [])
        if not itens:
            continue
        print(f"\n--- {titulo} ({len(itens)}) ---")
        for op, v, b, explic in itens:
            print(f"\n  op {op}  {v['cedente'][:40]}")
            print(f"     {explic}")
            if b:
                print(f"     conta={b.get('conta')} | pago={b.get('valor_pago')} | "
                      f"finalizada={b.get('data_fin')}")
            for p in v["pendencias"][:5]:
                print(f"     - {p[:150]}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
