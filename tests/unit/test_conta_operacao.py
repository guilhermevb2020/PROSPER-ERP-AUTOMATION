#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes da decisao do campo Conta (hook pre-salvar do robo de analise de credito).

POR QUE ESTES TESTES EXISTEM
----------------------------
O hook existe para destravar a operacao que chega com o campo Conta em
«Selecione a conta» — nesse estado o Smart mantem o `#SalvarOperacaoButton`
desabilitado, o robo desiste depois de 8s e a op volta em toda varredura (a op
62932 aparece 11 vezes nos logs de 20 a 26/08).

Mas o mesmo codigo que preenche uma conta VAZIA poderia, com um `if` errado,
TROCAR uma conta ja escolhida — e conta bancaria e para onde o dinheiro vai.
Nenhum robo deste repositorio tem autorizacao para isso.

Por isso a decisao foi separada num `decidir_conta()` puro (sem Playwright, sem
rede), e o caso «ja preenchida -> nao mexe» e o primeiro teste do arquivo. Mesmo
desenho do `analise.py` do robo de pagamento, e pela mesma razao: o container nao
tem pytest, o host tem.

RESTRICOES DE AMBIENTE
----------------------
`conta_operacao.py` so depende de stdlib no nivel de modulo, entao importa no
host sem Playwright instalado.
"""
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src" / "processors" / "web" / "credito"))

import conta_operacao as co  # noqa: E402

# A tela real, medida na captura de 26/08/2026: placeholder, duas contas de
# verdade e a saida «Informar posteriormente».
OPCOES = [
    {"value": "", "texto": "Selecione a conta"},
    {"value": "12", "texto": "Caixa"},
    {"value": "34", "texto": "Banco do Brasil Prospere"},
    {"value": "99", "texto": "Informar posteriormente"},
]


# --------------------------------------------------------------------------- #
# ⛔ A regra que nao pode ser quebrada
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("valor,texto", [
    ("12", "Caixa"),
    ("34", "Banco do Brasil Prospere"),
    ("99", "Informar posteriormente"),      # ja resolvida antes: tambem nao mexe
])
def test_conta_ja_preenchida_nunca_e_trocada(valor, texto):
    alvo, motivo = co.decidir_conta(OPCOES, valor, texto)
    assert alvo is None
    assert "nao mexe" in motivo


# --------------------------------------------------------------------------- #
# O caso que o hook existe para resolver
# --------------------------------------------------------------------------- #
def test_conta_vazia_escolhe_informar_posteriormente():
    alvo, motivo = co.decidir_conta(OPCOES, "", "Selecione a conta")
    assert alvo == "99"
    assert "Informar posteriormente" in motivo


@pytest.mark.parametrize("valor,texto", [
    ("", "Selecione a conta"),      # o caso da captura
    ("", ""),                       # value vazio e nada selecionado
    ("0", "Selecione a conta"),     # placeholder com value '0'
    ("0", ""),                      # so o value denuncia
    (None, None),                   # leitura falhou; trata como vazio
])
def test_todas_as_formas_de_conta_vazia_sao_reconhecidas(valor, texto):
    alvo, _ = co.decidir_conta(OPCOES, valor, texto)
    assert alvo == "99"


def test_placeholder_com_value_nao_vazio_ainda_conta_como_vazio():
    """Se o Smart der um id ao placeholder, o TEXTO ainda o denuncia."""
    opcoes = [{"value": "-1", "texto": "Selecione a conta"}] + OPCOES[1:]
    alvo, _ = co.decidir_conta(opcoes, "-1", "Selecione a conta")
    assert alvo == "99"


# --------------------------------------------------------------------------- #
# A opcao alvo e achada pelo TEXTO, nao pelo value (que e id de banco)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("texto_opcao", [
    "Informar posteriormente",
    "informar posteriormente",
    "  INFORMAR POSTERIORMENTE  ",
    "Informar posteriormente (a definir)",   # o Smart pode acrescentar sufixo
])
def test_opcao_alvo_e_casada_sem_depender_de_caixa_ou_espacos(texto_opcao):
    opcoes = [{"value": "", "texto": "Selecione a conta"},
              {"value": "77", "texto": texto_opcao}]
    alvo, _ = co.decidir_conta(opcoes, "", "Selecione a conta")
    assert alvo == "77"


def test_o_value_devolvido_e_o_da_opcao_alvo_e_nao_a_posicao():
    """Prende contra 'selecionar pelo indice', que quebra quando a lista muda."""
    opcoes = [{"value": "", "texto": "Selecione a conta"},
              {"value": "abc-123", "texto": "Informar posteriormente"},
              {"value": "12", "texto": "Caixa"}]
    alvo, _ = co.decidir_conta(opcoes, "", "Selecione a conta")
    assert alvo == "abc-123"


# --------------------------------------------------------------------------- #
# Recusas — o hook prefere nao fazer nada a fazer errado
# --------------------------------------------------------------------------- #
def test_sem_opcao_alvo_nao_inventa_outra_conta():
    """Se «Informar posteriormente» nao existe, NAO cai na primeira conta real."""
    opcoes = [{"value": "", "texto": "Selecione a conta"},
              {"value": "12", "texto": "Caixa"},
              {"value": "34", "texto": "Banco do Brasil Prospere"}]
    alvo, motivo = co.decidir_conta(opcoes, "", "Selecione a conta")
    assert alvo is None
    assert "nenhuma opcao casa" in motivo
    # o motivo lista o que havia na tela — e o que permite diagnosticar pelo log
    assert "Caixa" in motivo


def test_opcao_alvo_sem_value_e_recusada():
    """Selecionar uma opcao de value vazio deixaria o SALVAR desabilitado igual."""
    opcoes = [{"value": "", "texto": "Selecione a conta"},
              {"value": "", "texto": "Informar posteriormente"}]
    alvo, motivo = co.decidir_conta(opcoes, "", "Selecione a conta")
    assert alvo is None
    assert "value vazio" in motivo


@pytest.mark.parametrize("opcoes", [None, []])
def test_tela_sem_opcoes_nao_estoura(opcoes):
    alvo, motivo = co.decidir_conta(opcoes, "", "Selecione a conta")
    assert alvo is None
    assert motivo


# --------------------------------------------------------------------------- #
# Defaults — a regressao entra por aqui
# --------------------------------------------------------------------------- #
def test_nasce_desligado():
    """CONTA_PADRAO_APLICAR ausente = so log. Ligar e decisao explicita."""
    import os
    assert os.getenv("CONTA_PADRAO_APLICAR") is None
    assert co.APLICAR is False


def test_texto_alvo_padrao():
    assert co.ALVO == "informar posteriormente"
