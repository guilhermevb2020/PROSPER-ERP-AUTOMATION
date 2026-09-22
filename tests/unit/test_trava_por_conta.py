# -*- coding: utf-8 -*-
"""A trava financeira e por CONTA do Smart, nao por projeto.

Medido em 22/09/2026 sobre 10 dias: a remessa de cobranca das 18h segurava a trava por
18-29 min e o pagamento (a cada 5 min, espera de 300 s) falhava com exit 6 de 1 a 4 vezes
por dia, sem ganho nenhum — cobranca entra como `prosperito`, pagamento como
`prosperito_financeiro`, e contas diferentes nao disputam sessao. Desde entao cada
familia tem a sua trava; dentro da familia a exclusividade continua.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
WEB = RAIZ / "src/processors/web"
COBRANCA = ["remessa_cobranca/run_agendado.sh", "remessa_cobranca/run_bb.sh",
            "remessa_cobranca/run_cancelamento.sh", "retorno_cobranca/run_agendado.sh",
            "retorno_cobranca/run_bb.sh", "retorno_cobranca/run_deposito.sh"]
PAGAMENTO = ["remessa_pagamento/run_agendado.sh", "retorno_pagamento/run_agendado.sh"]
SOURCE = re.compile(r'^\s*\.\s+["\']?[^\n]*smart_financeiro_lock\.sh', re.M)
DEFINE = re.compile(r'^TRAVA_SMART_FINANCEIRO="\$\{TRAVA_SMART_FINANCEIRO:-(/tmp/[a-z_]+\.lock)\}"', re.M)


def _partes(rel):
    s = (WEB / rel).read_text(encoding="utf-8")
    m = SOURCE.search(s)
    assert m, f"{rel} nao carrega a trava"
    return s, m.start()


def test_a_familia_de_cobranca_usa_a_propria_trava_antes_de_carregar_o_lock():
    for rel in COBRANCA:
        s, i = _partes(rel)
        d = DEFINE.search(s)
        assert d and d.group(1) == "/tmp/smart_cobranca.lock", f"{rel}: sem trava de cobranca"
        assert d.start() < i, f"{rel}: a variavel tem de vir ANTES do `. smart_financeiro_lock.sh`"


def test_a_familia_de_pagamento_fica_na_trava_original():
    """A conta financeira e a que so admite UMA sessao: e o caso que a trava nasceu para
    proteger. Nada muda para ela — nem o caminho, nem o inode."""
    for rel in PAGAMENTO:
        s, _ = _partes(rel)
        assert not DEFINE.search(s), f"{rel}: pagamento nao define trava propria"
        assert "smart_cobranca.lock" not in s


def test_a_trava_honra_a_variavel_e_as_duas_familias_nao_se_cruzam():
    lock = (RAIZ / "src/common/smart_financeiro_lock.sh").read_text(encoding="utf-8")
    assert '"${TRAVA_SMART_FINANCEIRO:-/tmp/smart_financeiro.lock}"' in lock
    assert "/tmp/smart_cobranca.lock" != "/tmp/smart_financeiro.lock"
