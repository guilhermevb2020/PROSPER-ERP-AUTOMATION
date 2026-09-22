# -*- coding: utf-8 -*-
"""O espelho do retorno no banco le a GRADE que o Smart devolve, nao as criticas.

Entre 21 e 22/09/2026, `_registrar_no_banco()` procurava `numTitulo`/`ocorrencia`/`valor`
— chaves das CRITICAS — em `res["detalhes"]`, que e a grade de `retorno.extrair_titulos`
(`numero_titulo`, `acao_tomada`, `valor_titulo`...). Resultado: 95 titulos em
`arquivo_titulo` so com o numero da linha — contagem certa, identificacao vazia — e o
teste de integracao nao viu porque alimentava o cliente com dicionarios ja mapeados.

Este teste parte do HTML em base64, como o upload devolve, e vai ate os argumentos que
chegam ao cliente de execucao. Quem mudar as colunas da grade ou o mapeamento quebra aqui.
"""
import base64
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src/processors/web/retorno_cobranca"))

import retorno  # noqa: E402
import processar_retorno_cobranca as robo  # noqa: E402


def grade_do_smart(linhas):
    """A grade como o upload devolve: HTML ISO-8859-1 em base64, uma <tr> por titulo,
    colunas na ordem de `retorno.extrair_titulos`."""
    html = "<table>" + "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in linha) + "</tr>" for linha in linhas
    ) + "</table>"
    return base64.b64encode(html.encode("iso-8859-1")).decode("ascii")


# valor, vencimento, sacado, acao tomada, status, juros/multa, numero, valor arq, pago, data
LINHAS = [
    ["1.234,56", "10/10/2026", "SACADO UM", "Liquidado", "OK", "0,00",
     "7021-001", "1.234,56", "1.234,56", "21/09/2026"],
    ["78,90", "11/10/2026", "SACADO DOIS", "Entrada Confirmada", "OK", "0,00",
     "7021-002", "78,90", "", "21/09/2026"],
]


def resultado_do_upload(tmp_path):
    """`res` como `retorno.processar` devolve para um arquivo aceito: a grade extraida
    do base64 e o total que o Smart informa."""
    dados = {"titulos": grade_do_smart(LINHAS), "valorTotalTitulos": "1.313,46"}
    caminho = tmp_path / "CP2109000001.RET"
    caminho.write_bytes(b"0" * 400)
    return {"arquivo": caminho.name, "titulos": 2, "conta": 395, "processado": True,
            "motivo": "OK", "hash": "abc", "detalhes": retorno.extrair_titulos(dados),
            "valor_total": dados["valorTotalTitulos"]}, caminho


def _capturar(monkeypatch):
    recebido = {}

    def registrar_arquivo(ex, tipo, sentido, **kw):
        recebido.update(kw, tipo=tipo, sentido=sentido)
        return 77

    monkeypatch.setattr(robo.execucao_job, "registrar_arquivo", registrar_arquivo)
    monkeypatch.setattr(robo.execucao_job, "registrar_evento_arquivo", lambda *a, **k: 1)
    return recebido


def test_titulos_da_grade_chegam_ao_cliente_com_numero_acao_e_valor(tmp_path, monkeypatch):
    res, caminho = resultado_do_upload(tmp_path)
    recebido = _capturar(monkeypatch)

    assert robo._registrar_no_banco(object(), res, str(caminho), bb=False) == 77
    assert (recebido["tipo"], recebido["sentido"]) == ("retorno_cobranca_cnab_400", "recebido")
    assert recebido["valor_total"] == "1.313,46", "o total do Smart tem de ir para arquivo.valor_total"
    assert recebido["titulos"] == [
        {"numero_linha": 1, "id_titulo": "7021-001", "codigo_ocorrencia": "Liquidado",
         "valor_titulo": "1.234,56"},
        {"numero_linha": 2, "id_titulo": "7021-002", "codigo_ocorrencia": "Entrada Confirmada",
         "valor_titulo": "78,90"},
    ], "as chaves da grade sao numero_titulo/acao_tomada/valor_titulo, nao as das criticas"


def test_bb_usa_o_mesmo_mapeamento(tmp_path, monkeypatch):
    res, caminho = resultado_do_upload(tmp_path)
    recebido = _capturar(monkeypatch)
    robo._registrar_no_banco(object(), res, str(caminho), bb=True)
    assert recebido["tipo"] == "retorno_bb"
    assert [t["id_titulo"] for t in recebido["titulos"]] == ["7021-001", "7021-002"]


def test_grade_vazia_nao_inventa_titulo(tmp_path, monkeypatch):
    res, caminho = resultado_do_upload(tmp_path)
    res["detalhes"] = []
    recebido = _capturar(monkeypatch)
    robo._registrar_no_banco(object(), res, str(caminho), bb=False)
    assert recebido["titulos"] == []


def test_arquivo_grande_sem_grade_nao_vira_titulo_fantasma(tmp_path, monkeypatch):
    """Com 518 titulos (22/09/2026) o Smart nao renderiza a grade: devolve uma linha so,
    "Visualizar Titulos", sem numero nem valor. Isso nao e titulo e nao entra em
    arquivo_titulo; a contagem do arquivo continua sendo a do contador do Smart."""
    res, caminho = resultado_do_upload(tmp_path)
    dados = {"titulos": grade_do_smart([["Visualizar Títulos"]]), "valorTotalTitulos": "0,00"}
    res.update(detalhes=retorno.extrair_titulos(dados), titulos=518,
               valor_total=dados["valorTotalTitulos"])
    assert res["detalhes"] == [{"valor_titulo": "Visualizar Títulos"}], "o extrator le o botao como linha"
    recebido = _capturar(monkeypatch)
    robo._registrar_no_banco(object(), res, str(caminho), bb=False)
    assert recebido["titulos"] == []
    assert recebido["qtd_registros"] == 518
