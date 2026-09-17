#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes do portao da automação de retorno de retorno - o que decide se a grade vira baixa.

POR QUE ESTES TESTES EXISTEM
----------------------------
O `PROCESSAR_ARQUIVO` e irreversivel: depois dele o titulo esta baixado no
Smart. O BUG-548 mostrou o custo do erro - a baixa entrou no titulo de OUTRO
sacado, e a operacao teve de ser revertida a mao. O `portao.py` e a ultima
conferencia antes desse passo.

O QUE ELES TRAVAM
-----------------
1. O caso do BUG-548 (a grade e o arquivo discordando) e RECUSADO - e recusado
   AINDA QUE o `status` diga `OK`. E a prova de que o `status` sozinho nao
   serviria de portao.
2. O criterio PADRAO nao produz recusa falsa: rodado contra 1.238 titulos
   REAIS de banco (1.242 linhas, 4 delas rodape), de tres capturas, ele
   bloqueia ZERO arquivo.

RESTRICOES DE AMBIENTE (conferidas em 21/08/2026)
-------------------------------------------------
- Rodam no HOST (`pytest 9.1.1` / `python 3.12.3`); o container
  `erp-automation` NAO tem pytest.
- So `portao.py` pode ser importado aqui. O `retorno.py` e o `robo_retorno.py`
  puxam `playwright` e `src.common.clients`, que nao resolvem no host - e por
  isso que o portao foi escrito como modulo puro, so com stdlib.
- Os CSV de `data/robo_retorno/` sao capturas DATADAS e entram aqui SO PARA
  LEITURA. Nenhum caminho agendado da automação de retorno os reescreve: o `_gravar_titulos`
  so roda quando alguem passa `--csv-titulos <caminho>` a mao
  (`robo_retorno.py:410`), e os tres nomes abaixo nao sao default de nada.
"""
import csv
import sys
from functools import lru_cache
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src" / "processors" / "web" / "robo_retorno"))

from portao import (  # noqa: E402  (o sys.path tem de vir antes)
    APROVADO,
    POR_ACAO,
    POR_GRADE_VAZIA,
    POR_QUANTIDADE,
    POR_SEM_CASAMENTO,
    POR_STATUS,
    POR_VALOR,
    POR_VALOR_ARQUIVO_ILEGIVEL,
    RECUSADO,
    RESUMO,
    STATUS_TOLERADOS_NA_LIQUIDACAO,
    _num,
    avaliar_cnab_deposito,
    avaliar_grade,
    avaliar_resultado_deposito,
    avaliar_titulo,
    e_linha_de_resumo,
)

DADOS = RAIZ / "data" / "robo_retorno"

# Medido em 21/08/2026 rodando o portao contra as capturas. Cada numero aqui e
# um assert: se um deles mudar, ou a captura mudou ou o criterio mudou - e nos
# dois casos alguem tem de olhar antes de mexer no numero.
#
#   arquivos ..... quantos .RET distintos a captura tem
#   titulos ...... linhas avaliadas (ja fora as de rodape)
#   resumo ....... linhas do bloco de rodape da grade
#   bloq_status .. arquivos que CAIRIAM com exigir_status_ok=True
#   rec_status ... titulos que CAIRIAM com exigir_status_ok=True
#
# ⏪ 17/09/2026: `Data de vencimento diferente` em linha `Liquidado` deixou de
# recusar (STATUS_TOLERADOS_NA_LIQUIDACAO) — a entrega BB 38, 67 pagamentos,
# caiu inteira por um titulo assim. Das 9 recusas medidas em 21/08, 7 eram
# `Liquidado` (4 na prod_0408, 3 na 0508) e sairam; ficaram as 2 da prod_0408
# — o mesmo titulo 1645-001 em `Prorrogado` e `Entrada Rejeitada`, num unico
# arquivo (CBR6432340308202620223.ret) —, que continuam recusando.
MEDIDO = {
    "titulos_prod_0408.csv": {
        "arquivos": 79, "titulos": 800, "resumo": 4,
        "bloq_status": 1, "rec_status": 2,
    },
    "titulos_0508.csv": {
        "arquivos": 107, "titulos": 289, "resumo": 0,
        "bloq_status": 0, "rec_status": 0,
    },
    "titulos_teste.csv": {
        "arquivos": 71, "titulos": 149, "resumo": 0,
        "bloq_status": 0, "rec_status": 0,
    },
}
CAPTURAS = sorted(MEDIDO)

# O unico arquivo real que traz bloco de rodape na grade.
ARQUIVO_COM_RODAPE = "CBR643228308202620800.ret"

# O unico `status != OK` que aparece nas tres capturas. E liquidacao LEGITIMA:
# o banco pagou em data diferente da vencida. E a razao de `exigir_status_ok`
# ser False por padrao.
STATUS_LEGITIMO = "Data de vencimento diferente"


@lru_cache(maxsize=None)
def _carregar(nome):
    """As linhas da captura, como o `extrair_titulos` as entrega ao portao.

    O CSV tem BOM - dai o `utf-8-sig`. Linhas de rodape vem CURTAS (menos
    colunas que o cabecalho), e o `DictReader` preenche o que falta com None:
    e exatamente o `None` que o portao tem de aguentar.
    """
    caminho = DADOS / nome
    assert caminho.is_file(), (
        f"a captura {caminho} sumiu - sem ela nenhum numero deste arquivo "
        f"pode ser reproduzido"
    )
    with open(caminho, encoding="utf-8-sig", newline="") as fh:
        return tuple(csv.DictReader(fh))


@lru_cache(maxsize=None)
def _por_arquivo(nome):
    """A captura agrupada por .RET - o veredito do portao e POR ARQUIVO."""
    grades = {}
    for linha in _carregar(nome):
        grades.setdefault(linha["arquivo"], []).append(linha)
    return grades


def _linha_bug548(**troca):
    """A grade do BUG-548, com os numeros que o incidente registrou.

    O Smart resolveu `R$ 4.033,33 / CONSORCIO DCDC` para um pagamento que era
    `123410C / R$ 6.108,23 / RALTTEK`. Os dois lados estao na MESMA linha da
    grade, e e disso que o portao vive.
    """
    linha = {
        "arquivo": "CP0408001234.RET",
        "conta": "349",
        "valor_titulo": "4.033,33",          # <- o que o SMART resolveu
        "vencimento": "31/08/2026",
        "sacado": "CONSORCIO DCDC",          # <- e para QUEM ele resolveu
        "acao_tomada": "Liquidado",
        "status": "OK",                      # <- o status nao acusa nada
        "juros_multa": "0,00",
        "numero_titulo": "123410C",          # <- o que o ARQUIVO mandou
        "valor_titulo_arq": "6.108,23",      # <- e por quanto
        "valor_pago": "6.108,23",
        "data_ocorrencia": "04/08/2026",
    }
    linha.update(troca)
    return linha


# ---------------------------------------------------------------------------
# O caso que o portao existe para pegar - BUG-548
# ---------------------------------------------------------------------------

def test_bug548_recusa_quando_o_valor_do_smart_diverge_do_valor_do_arquivo():
    """A baixa no titulo do outro sacado tem de bater no portao.

    E o unico sinal que estava disponivel no momento do erro: a propria grade
    poe os dois lados lado a lado, e eles discordam em R$ 2.074,90.
    """
    veredito, motivo, _ = avaliar_titulo(_linha_bug548())

    assert veredito == RECUSADO
    assert motivo == POR_VALOR


def test_bug548_e_recusado_MESMO_COM_STATUS_OK__prova_que_status_nao_seria_o_portao():
    """O TESTE MAIS IMPORTANTE DESTE ARQUIVO.

    Quem olhasse so o `status` teria deixado o BUG-548 passar: a grade dizia
    `OK`. O portao recusa a linha do mesmo jeito, e recusa POR VALOR - nao por
    status - com o criterio padrao E com `exigir_status_ok=True`.

    Se um dia esta prova cair, o portao virou um leitor de `status`, e o modo
    de falha que ele foi escrito para pegar volta a passar.
    """
    linha = _linha_bug548()
    assert linha["status"] == "OK", "o caso so prova algo se o status disser OK"

    for exigir in (False, True):
        veredito, motivo, _ = avaliar_titulo(linha, exigir_status_ok=exigir)
        assert veredito == RECUSADO, f"passou com exigir_status_ok={exigir}"
        assert motivo == POR_VALOR, (
            f"com exigir_status_ok={exigir} a recusa veio por {motivo!r}; "
            f"o par de valores tem de ser o discriminador, nao o status"
        )


def test_bug548_o_detalhe_traz_os_dois_lados_para_o_relato():
    """O relato tem de dizer QUAL titulo e POR QUE, sem reabrir o CSV."""
    _, _, detalhe = avaliar_titulo(_linha_bug548())

    assert "4033.33" in detalhe        # o lado do Smart
    assert "6108.23" in detalhe        # o lado do arquivo
    assert "CONSORCIO DCDC" in detalhe  # para quem o Smart resolveu


def test_bug548_bloqueia_o_ARQUIVO_inteiro_porque_o_smart_nao_processa_linha_avulsa():
    """Um titulo recusado derruba o arquivo - o Smart processa o .RET inteiro."""
    boa = _linha_bug548(valor_titulo="1.155,60", valor_titulo_arq="1.155,60",
                        numero_titulo="6328-001", sacado="CONSTRUTORA RIBEIRO")
    grade = avaliar_grade([boa, _linha_bug548()])

    assert grade["liberado"] is False
    assert grade["avaliados"] == 2
    assert len(grade["recusados"]) == 1

    recusado = grade["recusados"][0]
    assert recusado["numero_titulo"] == "123410C"
    assert recusado["motivo"] == POR_VALOR
    assert recusado["acao_tomada"] == "Liquidado"


# ---------------------------------------------------------------------------
# `_num` - e a promessa de que None NAO e zero
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto, esperado", [
    ("1.234,56", 1234.56),          # formato BR: ponto e milhar, virgula e decimal
    ("R$ 1.234,56", 1234.56),       # com simbolo, como sai do HTML
    ("1.621.341,89", 1621341.89),   # dois pontos de milhar
    ("4184,99", 4184.99),           # sem milhar
    ("0,00", 0.0),                  # zero LEGITIMO - diferente de ilegivel
    ("-50,25", -50.25),
    ("123", 123.0),                 # inteiro sem decimal
])
def test_num_le_o_formato_do_brasil(texto, esperado):
    assert _num(texto) == esperado


@pytest.mark.parametrize("texto", [
    None,                    # coluna ausente na linha (rodape vem curto)
    "",                      # celula vazia
    "   ",                   # so espaco
    "R$",                    # so o simbolo
    "abc",                   # lixo
    "Entrada Confirmada",    # texto no lugar do numero (linha de rodape)
    "1,2,3",                 # numero malformado
])
def test_num_devolve_None_quando_nao_da_para_ler(texto):
    """`None` e o sinal de 'nao consegui ler' - e nao pode virar 0.0."""
    assert _num(texto) is None


def test_num_distingue_zero_legitimo_de_ilegivel():
    """`0,00` e um valor; `''` e a ausencia dele. Nao podem colidir."""
    assert _num("0,00") == 0.0
    assert _num("") is None
    assert _num("0,00") is not None


def test_None_NAO_e_tratado_como_zero_quando_o_lado_do_SMART_vem_vazio():
    """Campo vazio nao pode virar 'R$ 0,00' e passar por divergencia.

    Se `None` fosse zero, esta linha sairia como POR_VALOR com `smart=0.00` -
    um motivo INVENTADO, que manda a pessoa procurar uma divergencia de valor
    onde o que houve foi o Smart nao ter casado titulo nenhum.
    """
    _, motivo, detalhe = avaliar_titulo(_linha_bug548(valor_titulo=""))

    assert motivo == POR_SEM_CASAMENTO
    assert motivo != POR_VALOR
    assert "0.00" not in detalhe
    assert "(vazio)" in detalhe


def test_None_NAO_e_tratado_como_zero_quando_o_lado_do_ARQUIVO_vem_ilegivel():
    """A outra ponta da mesma promessa - e esta seria uma recusa FALSA.

    Com o lado do arquivo ilegivel nao ha par para comparar. Se `None` virasse
    0.0, todo titulo com essa coluna vazia seria recusado por 'divergencia'
    contra um zero que ninguem escreveu - e o portao passaria a barrar arquivo
    bom, que e justamente o que ele nao pode fazer.
    """
    for ilegivel in ("", None, "---"):
        veredito, motivo, _ = avaliar_titulo(
            _linha_bug548(valor_titulo_arq=ilegivel))
        assert veredito == APROVADO, (
            f"valor_titulo_arq={ilegivel!r} produziu {veredito}/{motivo}")


@pytest.mark.parametrize("ilegivel", ["", None, "---"])
def test_modo_estrito_recusa_valor_do_arquivo_ilegivel(ilegivel):
    veredito, motivo, _ = avaliar_titulo(
        _linha_bug548(valor_titulo_arq=ilegivel),
        exigir_valor_arquivo=True,
    )

    assert veredito == RECUSADO
    assert motivo == POR_VALOR_ARQUIVO_ILEGIVEL


# ---------------------------------------------------------------------------
# POR_SEM_CASAMENTO - o Smart nao resolveu titulo
# ---------------------------------------------------------------------------

def test_recusa_quando_o_smart_nao_resolveu_titulo_mas_o_arquivo_mandou_valor():
    """Sem o lado do Smart nao ha o que conferir - e o que nao se confere nao sobe."""
    linha = _linha_bug548(valor_titulo="", sacado="")
    veredito, motivo, detalhe = avaliar_titulo(linha)

    assert veredito == RECUSADO
    assert motivo == POR_SEM_CASAMENTO
    assert "6.108,23" in detalhe, "o relato tem de dizer o que o arquivo mandou"


def test_sem_casamento_recusa_antes_de_olhar_o_status():
    """Nem `status=OK` compra a passagem de uma linha sem casamento."""
    linha = _linha_bug548(valor_titulo=None, status="OK")
    veredito, motivo, _ = avaliar_titulo(linha, exigir_status_ok=True)

    assert veredito == RECUSADO
    assert motivo == POR_SEM_CASAMENTO


# ---------------------------------------------------------------------------
# `e_linha_de_resumo` - o rodape da grade nao e titulo
# ---------------------------------------------------------------------------

def test_o_rodape_real_da_grade_e_classificado_como_RESUMO():
    """A linha vem do CSV de producao, com as colunas TROCADAS como o Smart as da.

    Sem este filtro, `valor_titulo='Entrada Confirmada'` viraria ilegivel, a
    linha seria recusada por SEM_CASAMENTO e o portao derrubaria um arquivo
    inteiro por causa de um rodape.
    """
    rodape = {
        "arquivo": ARQUIVO_COM_RODAPE, "conta": "364",
        "valor_titulo": "Entrada Confirmada",   # <- na verdade e a ACAO
        "vencimento": "324",                    # <- na verdade e a CONTAGEM
        "sacado": "1.621.341,89",               # <- na verdade e o TOTAL
        "acao_tomada": "Visualizar Títulos",
        "status": None, "numero_titulo": None, "valor_titulo_arq": None,
    }

    assert e_linha_de_resumo(rodape) is True
    assert avaliar_titulo(rodape)[0] == RESUMO


def test_titulo_de_verdade_nao_e_confundido_com_rodape():
    assert e_linha_de_resumo(_linha_bug548()) is False


def test_o_rodape_nao_conta_como_titulo_avaliado_nem_derruba_o_arquivo():
    rodape = {"valor_titulo": "Liquidado", "vencimento": "42",
              "sacado": "50.789,05", "acao_tomada": "Visualizar Títulos",
              "status": None, "numero_titulo": None, "valor_titulo_arq": None}
    boa = _linha_bug548(valor_titulo="6.108,23")

    grade = avaliar_grade([boa, rodape])

    assert grade["liberado"] is True
    assert grade["avaliados"] == 1
    assert grade["resumo"] == 1


def test_o_ramo_do_rotulo_alcanca_o_acento__o_Smart_escreve_Visualizar_Titulos():
    """O rodape e pego pelos DOIS ramos, e isso foi conquistado, nao dado.

    Na primeira versao o `e_linha_de_resumo` comparava `acao_tomada` contra
    `"visualizar titulos"` SEM acento, e o Smart escreve COM. O ramo do rotulo
    ficava inerte: as 4 linhas de rodape das capturas eram pegas so pelo OUTRO
    ramo, o de `numero_titulo` e `status` vazios. Funcionava por acaso — o
    rodape real sempre vem sem os dois campos — e ramo morto dentro de um
    portao e armadilha para quem mexer depois. Este teste trava o conserto.
    """
    so_o_rotulo = {"valor_titulo": "Entrada Confirmada", "vencimento": "324",
                   "sacado": "1.621.341,89", "acao_tomada": "Visualizar Titulos",
                   "status": "OK", "numero_titulo": "1962-001",
                   "valor_titulo_arq": ""}
    com_acento = dict(so_o_rotulo, acao_tomada="Visualizar T\u00edtulos")

    # o ramo do rotulo pega os dois, com e sem acento
    assert e_linha_de_resumo(so_o_rotulo) is True
    assert e_linha_de_resumo(com_acento) is True

    # e um titulo de verdade, com acao_tomada normal, NAO e confundido
    titulo = dict(so_o_rotulo, acao_tomada="Liquidado")
    assert e_linha_de_resumo(titulo) is False


# ---------------------------------------------------------------------------
# Grade vazia - nao pode estourar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("detalhes", [[], None])
def test_grade_vazia_nao_estoura_e_libera__nao_ha_o_que_recusar(detalhes):
    """Upload sem grade nao e motivo de recusa: nao ha titulo a conferir.

    Quem decide o que fazer com um upload sem detalhes e o chamador; o portao
    so responde que nao encontrou divergencia nenhuma.
    """
    grade = avaliar_grade(detalhes)

    assert grade["liberado"] is True
    assert grade["avaliados"] == 0
    assert grade["resumo"] == 0
    assert grade["recusados"] == []


def test_grade_vazia_e_recusada_quando_ha_quantidade_esperada():
    grade = avaliar_grade([], quantidade_esperada=1, quantidade_arquivo=1)

    assert grade["liberado"] is False
    assert POR_GRADE_VAZIA in grade["erros_grade"]


@pytest.mark.parametrize("upload,arquivo", [(0, 0), (2, 1), (1, 2)])
def test_modo_estrito_exige_mesma_quantidade_no_arquivo_upload_e_grade(
        upload, arquivo):
    grade = avaliar_grade(
        [_linha_bug548(valor_titulo="6.108,23")],
        quantidade_esperada=upload,
        quantidade_arquivo=arquivo,
    )

    assert grade["liberado"] is False
    assert POR_QUANTIDADE in grade["sumario"]


def test_modo_deposito_exige_acao_liquidado_e_status_ok():
    acao = avaliar_grade(
        [_linha_bug548(valor_titulo="6.108,23", acao_tomada="Baixa")],
        quantidade_esperada=1,
        quantidade_arquivo=1,
        exigir_acao="Liquidado",
        exigir_status_ok=True,
        exigir_valor_arquivo=True,
    )
    status = avaliar_grade(
        [_linha_bug548(valor_titulo="6.108,23", status="PENDENTE")],
        quantidade_esperada=1,
        quantidade_arquivo=1,
        exigir_acao="Liquidado",
        exigir_status_ok=True,
        exigir_valor_arquivo=True,
    )

    assert acao["recusados"][0]["motivo"] == POR_ACAO
    assert status["recusados"][0]["motivo"] == POR_STATUS


def _cnab_deposito(identificador="0" * 25):
    cabecalho = "0" + " " * 399
    detalhe = list("1" + " " * 399)
    detalhe[37:62] = identificador
    trailer = "9" + " " * 399
    return [cabecalho, "".join(detalhe), trailer]


def test_cnab_deposito_exige_400_posicoes_e_identificador_de_25_digitos():
    valido = avaliar_cnab_deposito(_cnab_deposito())
    sem_id = avaliar_cnab_deposito(_cnab_deposito(" " * 25))
    curto = avaliar_cnab_deposito(["0" * 399, "1" * 400, "9" * 400])

    assert valido == {
        "liberado": True,
        "quantidade": 1,
        "erros": [],
        "sumario": "1 detalhe(s) CNAB valido(s)",
    }
    assert sem_id["liberado"] is False
    assert "identificador CNAB" in sem_id["sumario"]
    assert curto["liberado"] is False
    assert "399 posicoes" in curto["sumario"]


def test_resultado_deposito_so_comprova_liquidacao_exata_sem_refinan():
    comprovado = avaliar_resultado_deposito(
        {"message": "OK", "liquidacao": "1", "refinan": None}, 1
    )
    sem_message = avaliar_resultado_deposito({"liquidacao": 1}, 1)
    refinanciado = avaliar_resultado_deposito(
        {"message": "OK", "liquidacao": 1, "refinan": 1}, 1
    )
    outro = avaliar_resultado_deposito(
        {"message": "OK", "liquidacao": 1, "baixa": 1}, 1
    )

    assert comprovado["comprovado"] is True
    assert sem_message["comprovado"] is False
    assert refinanciado["comprovado"] is False
    assert outro["comprovado"] is False


# ---------------------------------------------------------------------------
# O sumario - a linha que vai para o relato
# ---------------------------------------------------------------------------

def test_sumario_do_arquivo_liberado_diz_quantos_conferiu():
    boa = _linha_bug548(valor_titulo="6.108,23")
    grade = avaliar_grade([boa, dict(boa, numero_titulo="123411C")])

    assert grade["sumario"] == "2 titulo(s) conferido(s), nenhuma divergencia"


def test_sumario_do_arquivo_recusado_conta_por_motivo():
    grade = avaliar_grade([_linha_bug548(),
                           _linha_bug548(valor_titulo="", numero_titulo="123411C")])

    assert grade["liberado"] is False
    assert grade["sumario"] == (
        "2 de 2 titulo(s) recusado(s): "
        f"{POR_SEM_CASAMENTO} (1), {POR_VALOR} (1)"
    )


# ---------------------------------------------------------------------------
# As capturas REAIS - o criterio padrao nao pode barrar arquivo bom
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("captura", CAPTURAS)
def test_a_captura_tem_o_tamanho_medido(captura):
    """Guarda das guardas: se a captura mudou, os numeros abaixo nao valem mais."""
    esperado = MEDIDO[captura]
    linhas = _carregar(captura)

    assert len(linhas) == esperado["titulos"] + esperado["resumo"]
    assert len(_por_arquivo(captura)) == esperado["arquivos"]


@pytest.mark.parametrize("captura", CAPTURAS)
def test_o_criterio_PADRAO_nao_bloqueia_NENHUM_arquivo_real(captura):
    """A contrapartida do teste do BUG-548: o portao nao pode barrar o que presta.

    Medido sobre `.RET` REAIS de banco. Um portao que recusa arquivo bom seria
    desligado na primeira semana, e ai o BUG-548 volta a passar.
    """
    esperado = MEDIDO[captura]
    bloqueados, recusados, avaliados, resumo = [], 0, 0, 0

    for arquivo, grade in _por_arquivo(captura).items():
        v = avaliar_grade(grade)
        avaliados += v["avaliados"]
        resumo += v["resumo"]
        recusados += len(v["recusados"])
        if not v["liberado"]:
            bloqueados.append((arquivo, v["sumario"]))

    assert bloqueados == [], f"recusa falsa em {captura}: {bloqueados}"
    assert recusados == 0
    assert avaliados == esperado["titulos"]
    assert resumo == esperado["resumo"]


def test_as_tres_capturas_somam_1238_titulos_reais_sem_uma_recusa():
    """O numero que sustenta o `POR QUE ELE EXISTE` do `portao.py`."""
    total = sum(MEDIDO[c]["titulos"] for c in CAPTURAS)
    assert total == 1238

    recusados = sum(
        len(avaliar_grade(grade)["recusados"])
        for captura in CAPTURAS
        for grade in _por_arquivo(captura).values()
    )
    assert recusados == 0


@pytest.mark.parametrize("captura", CAPTURAS)
def test_as_linhas_de_rodape_reais_sao_as_medidas(captura):
    """4 em `titulos_prod_0408.csv`, todas do mesmo .RET; zero nas outras duas."""
    rodapes = [linha for linha in _carregar(captura) if e_linha_de_resumo(linha)]

    assert len(rodapes) == MEDIDO[captura]["resumo"]
    if rodapes:
        assert {linha["arquivo"] for linha in rodapes} == {ARQUIVO_COM_RODAPE}


# ---------------------------------------------------------------------------
# `exigir_status_ok=True` - por que NAO e o padrao
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("captura", CAPTURAS)
def test_exigir_status_ok_barraria_liquidacao_LEGITIMA(captura):
    """O custo medido de ligar o status - e a razao de o padrao ser False.

    Todas as recusas que aparecem aqui sao `Data de vencimento diferente`. Desde
    17/09/2026 a linha `Liquidado` com esse status passa (o banco pagou em data
    diferente da vencida, o dinheiro entrou e o valor BATE dos dois lados);
    sobram as acoes que NAO sao liquidacao — `Prorrogado`, `Entrada Rejeitada` —,
    onde o status continua recusando o arquivo.
    """
    esperado = MEDIDO[captura]
    bloqueados, recusados = [], []

    for arquivo, grade in _por_arquivo(captura).items():
        v = avaliar_grade(grade, exigir_status_ok=True)
        recusados.extend(v["recusados"])
        if not v["liberado"]:
            bloqueados.append(arquivo)

    assert len(bloqueados) == esperado["bloq_status"]
    assert len(recusados) == esperado["rec_status"]

    # e todas elas sao legitimas: nenhuma e divergencia de valor
    for r in recusados:
        assert r["motivo"] == POR_STATUS, (
            f"{captura} tem recusa por {r['motivo']!r} - se aparecer "
            f"{POR_VALOR!r} aqui, o criterio padrao esta deixando erro passar")
        assert STATUS_LEGITIMO in r["detalhe"]
        assert r["acao_tomada"] != "Liquidado", "liquidacao com esse status nao recusa mais"


@pytest.mark.parametrize("acao,veredito_esperado", [
    ("Liquidado", APROVADO), ("liquidado", APROVADO),
    ("Prorrogado", RECUSADO), ("Entrada Confirmada", RECUSADO), ("Entrada Rejeitada", RECUSADO),
    ("", RECUSADO),
])
def test_data_de_vencimento_diferente_so_passa_em_LIQUIDACAO(acao, veredito_esperado):
    """17/09/2026: a entrega BB 38 (67 pagamentos de 16 e 17/09) foi recusada inteira
    porque o 11893-001 veio `Data de vencimento diferente` — boleto vencendo 14/09 no
    banco e 30/09 no ERP, pago em 17/09. Pagamento e pagamento; a data e informativa.
    Em qualquer outra acao o status continua recusando o arquivo."""
    linha = {"numero_titulo": "11893-001", "valor_titulo": "425,90", "valor_titulo_arq": "425,90",
             "sacado": "SACADO", "status": STATUS_LEGITIMO, "acao_tomada": acao}
    veredito, motivo, _ = avaliar_titulo(linha, exigir_status_ok=True, exigir_valor_arquivo=True)
    assert veredito == veredito_esperado
    assert motivo == ("" if veredito_esperado == APROVADO else POR_STATUS)
    assert STATUS_LEGITIMO.lower() in STATUS_TOLERADOS_NA_LIQUIDACAO


def test_liquidacao_com_OUTRO_status_fora_de_OK_continua_recusada():
    linha = {"numero_titulo": "1", "valor_titulo": "10,00", "valor_titulo_arq": "10,00",
             "status": "Titulo nao encontrado", "acao_tomada": "Liquidado"}
    veredito, motivo, _ = avaliar_titulo(linha, exigir_status_ok=True)
    assert (veredito, motivo) == (RECUSADO, POR_STATUS)
    # e o valor divergente vence a tolerancia: BUG-548 continua barrado
    linha_548 = {**linha, "status": STATUS_LEGITIMO, "valor_titulo_arq": "6.108,23"}
    assert avaliar_titulo(linha_548, exigir_status_ok=True)[1] == POR_VALOR


def test_ligar_o_status_nao_encontra_NENHUM_erro_de_casamento_novo():
    """A prova de que o status nao acrescenta poder de deteccao, so custo.

    Somando as tres capturas: com o status ligado sobem 2 recusas (eram 9 ate a
    tolerancia de 17/09/2026 para `Liquidado`), e as 2 sao por status. Nenhuma
    divergencia de valor aparece que o padrao ja nao pegue - e o padrao pega
    zero, porque nao ha nenhuma nos dados reais.
    """
    por_motivo = {}
    for captura in CAPTURAS:
        for grade in _por_arquivo(captura).values():
            for r in avaliar_grade(grade, exigir_status_ok=True)["recusados"]:
                por_motivo[r["motivo"]] = por_motivo.get(r["motivo"], 0) + 1

    assert por_motivo == {POR_STATUS: 2}
    assert POR_VALOR not in por_motivo
    assert POR_SEM_CASAMENTO not in por_motivo
