# -*- coding: utf-8 -*-
"""
listar_fila.py - lista, AO VIVO, as operacoes na etapa de entrada do Robo 7
("Aguardando Ass."), direto da tela do Smart.

Por que nao usar o banco: `trs.operacao_desagio` e um ESPELHO com atraso de ~1
dia - as operacoes de HOJE (que sao justamente as que o R7 vai finalizar) ainda
nao estao la. O banco entra so p/ ENRIQUECER (cedente/valor) o que ja veio da
tela; op sem espelho aparece assim mesmo.

Read-only: so faz a consulta da tela (mesma funcao que o R1 usa).

Uso (rodar da RAIZ, com sessao logada):
  python robo7_finalizar/listar_fila.py
  python robo7_finalizar/listar_fila.py --cdp 9222 --sem-banco
"""
import argparse
import os
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(_AQUI)
for _p in (_AQUI, os.path.join(_RAIZ, "credito")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import r7_config as cfg              # noqa: E402
import _analisar_credito_base as robo  # noqa: E402

# nome REAL da tabela (a antiga trs.operacoes_desagio nao existe mais)
TABELA = os.environ.get("R7_TABELA_ESPELHO", "trs.operacao_desagio")


def enriquecer(ops):
    """{op: {cedente, valor, etapa}} do espelho; {} se o banco nao responder."""
    if not ops:
        return {}
    try:
        import psycopg2
        import config as r1_config
        conn = psycopg2.connect(connect_timeout=r1_config.DB_CONNECT_TIMEOUT,
                                **r1_config.DB_CONFIG)
    except Exception as e:
        print(f"  (banco indisponivel: {e} - segue so com a tela)")
        return {}
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT id_operacao, cedente, valor_liquido, etapa, tipo_operacao "
            f"FROM {TABELA} WHERE id_operacao = ANY(%s)",
            ([int(o) for o in ops if str(o).isdigit()],))
        return {str(r[0]): {"cedente": r[1], "valor": r[2], "etapa": r[3], "tipo": r[4]}
                for r in cur.fetchall()}
    except Exception as e:
        print(f"  (erro ao consultar {TABELA}: {e})")
        return {}
    finally:
        conn.close()


def listar(ctx):
    """Numeros das ops na etapa de entrada, ao vivo (Home + Smart)."""
    return robo.listar_operacoes_etapa(ctx, cfg.VALOR_ETAPA_ENTRADA,
                                       cfg.ROTULO_ETAPA_ENTRADA)


def main():
    ap = argparse.ArgumentParser(description="Lista a fila do Robo 7 ao vivo.")
    ap.add_argument("--cdp", default=str(cfg.CDP_PORT))
    ap.add_argument("--sem-banco", action="store_true", help="nao enriquece pelo espelho")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{args.cdp}")
        except Exception as e:
            print(f"[ERRO] CDP {args.cdp} nao responde: {e}\n"
                  "       Suba a sessao: python robo7_finalizar/sessao_r7.py")
            return 2
        ctx = browser.contexts[0]
        print(f"=== FILA DO ROBO 7 | etapa '{cfg.ROTULO_ETAPA_ENTRADA}' | CDP {args.cdp} ===")
        ops = listar(ctx)

    if not ops:
        print("\n  (nenhuma operacao na etapa - ou a sessao caiu; confira a janela)")
        return 0

    extra = {} if args.sem_banco else enriquecer(ops)
    print(f"\n  {len(ops)} operacao(oes):\n")
    for op in ops:
        info = extra.get(str(op))
        if info:
            valor = f"R$ {info['valor']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            print(f"    {op}  {str(info['cedente'])[:42]:<42} {valor:>16}  {info['tipo']}")
        else:
            print(f"    {op}  (de hoje - ainda nao esta no espelho do banco)")
    print(f"\n  ops = {','.join(str(o) for o in ops)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
