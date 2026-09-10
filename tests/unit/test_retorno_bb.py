"""A liquidacao BB usa o contador comprovado pelo processamento no Smart."""

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src" / "processors" / "web" / "robo_retorno"))

import retorno  # noqa: E402


@pytest.mark.parametrize("banco,contadores,esperado", [
    ("001", {"liquidacao": 1, "refinan": None}, []),
    ("001", {"liquidacao": None, "refinan": 1},
     ["Liquidado: grade=1 contador=0"]),
    ("274", {"liquidacao": None, "refinan": 1}, []),
    (None, {"refinan": 1}, []),
])
def test_contador_de_liquidacao_depende_do_banco(banco, contadores, esperado):
    assert retorno.conferir_divergencias(
        {"Liquidado": 1}, contadores, banco_compe=banco,
    ) == esperado


def test_fluxo_le_banco_do_header_para_conferir_resultado(tmp_path, monkeypatch):
    header = list(" " * 400)
    header[0] = "0"
    header[76:79] = "001"
    arquivo = tmp_path / "BBTESTE.RET"
    arquivo.write_text("\n".join(["".join(header), "7" + " " * 399,
                                  "9" + " " * 399]), encoding="latin-1")
    monkeypatch.setattr(retorno, "em_processamento", lambda *_: False)
    monkeypatch.setattr(retorno, "ja_processado", lambda *_: False)
    monkeypatch.setattr(retorno, "validar_banco_conta", lambda *_: 395)
    monkeypatch.setattr(retorno, "enviar", lambda *_: {"quantidadeTitulos": 1})
    monkeypatch.setattr(retorno, "extrair_titulos", lambda *_: [{
        "numero_titulo": "TESTE", "valor_titulo": "250,00",
        "valor_titulo_arq": "250,00", "acao_tomada": "Liquidado", "status": "OK",
    }])
    monkeypatch.setattr(retorno, "processar_arquivo", lambda *_: {
        "message": "OK", "liquidacao": 1, "refinan": None,
    })
    monkeypatch.setattr(retorno, "verificar_criticas", lambda *_: [])
    monkeypatch.setattr(retorno, "soltar_trava", lambda *_: None)

    resultado = retorno.processar(None, arquivo, dry_run=False, usar_portao=True)

    assert resultado["processado"] is True
    assert resultado["divergencias"] == []
