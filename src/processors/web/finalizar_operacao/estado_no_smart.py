# -*- coding: utf-8 -*-
"""
estado_no_smart.py - a operacao FOI finalizada? Pergunta ao SMART, nao ao banco.

Por que existe: a confirmacao pelo espelho do Postgres (`confirmar_no_banco`)
deu FALSO NEGATIVO na 1a finalizacao real (op 64997, 01/09/2026) - o espelho NAO
e instantaneo. O robo entao reportou "falha ao finalizar" numa operacao que
tinha finalizado, e por isso nao mandou os avisos nem registrou o CSV.
O Smart atualiza na hora, entao a fonte da verdade e ele.

Criterio: na tela de Resumir, o botao FINALIZAR (`id="pagamento"`) so existe
enquanto a operacao NAO foi finalizada. Sumiu = finalizada.

Uso:
  python finalizar_operacao/estado_no_smart.py 64997 64887
"""
import re
import sys
import os

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(_AQUI)
for _p in (_AQUI, os.path.join(_RAIZ, "operacoes")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_RE_BOTAO = re.compile(r"""id=['"]pagamento['"]""", re.I)


def resumir_html(s, op):
    """(html, numCedente) da tela de Resumir da operacao, por HTTP puro."""
    import classe_risco_tool as crt
    from smart_session import BASE
    dados = crt.carregar_operacao(s, op)
    ced = dados.get("numCedente") or ""
    st, html = s.get(f"{BASE}/operacao/novoresumir.php?op={op}&ced={ced}", timeout=60_000)
    if st != 200:
        raise RuntimeError(f"novoresumir.php devolveu {st}")
    return html, ced


def finalizada(s, op):
    """-> (True/False/None, detalhe). None = nao deu p/ saber."""
    try:
        html, _ced = resumir_html(s, op)
    except Exception as e:
        return None, f"nao consegui ler o Resumir: {str(e)[:110]}"
    if "expira.php" in html:
        return None, "sessao do Smart expirada"
    tem_botao = bool(_RE_BOTAO.search(html))
    if tem_botao:
        return False, "o botao Finalizar AINDA existe na tela"
    return True, "o botao Finalizar nao existe mais na tela"


def main():
    ops = sys.argv[1:] or ["64997"]
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from smart_session import Smart
    import r7_config as cfg
    with Smart(cdp=cfg.CDP_URL) as s:
        for op in ops:
            ok, detalhe = finalizada(s, op)
            marca = {True: "FINALIZADA", False: "NAO finalizada", None: "?"}[ok]
            print(f"  op {op}: {marca} - {detalhe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
