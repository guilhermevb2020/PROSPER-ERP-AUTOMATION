"""O fluxo BB API não trata status OK ou resposta vazia como efeito confirmado."""
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src" / "processors" / "web" / "robo_retorno"))

import bb_api  # noqa: E402
import retorno  # noqa: E402


def arquivo(tmp_path, codigo="06", documento="TESTE-001 "):
    assert len(documento) == 10
    header, detalhe, trailer = [list(" " * 400) for _ in range(3)]
    header[:19] = "02RETORNO01COBRANCA"
    header[26:40] = "03867" + "00098691" + "7"
    header[76:79] = "001"
    header[149:156] = "3770013"
    detalhe[0] = "7"
    detalhe[17:31] = header[26:40]
    detalhe[31:38] = "3770013"
    detalhe[38:63] = "0000000395000000000000001"
    detalhe[63:80] = "37700130000000001"
    detalhe[108:110] = codigo
    detalhe[110:116] = "090926"
    detalhe[116:126] = documento
    detalhe[152:165] = "0000000025000"
    detalhe[227:240] = "0000000001234" if codigo == "12" else " " * 13
    detalhe[253:266] = "0000000025000" if codigo == "06" else " " * 13
    trailer[:7] = "9201001"
    linhas = [header, detalhe, trailer]
    for i, linha in enumerate(linhas, 1):
        linha[394:400] = f"{i:06d}"
        assert len(linha) == 400
    p = tmp_path / "BBAPI.RET"
    p.write_bytes(("\r\n".join("".join(l) for l in linhas) + "\r\n").encode("latin-1"))
    return p


def grade(codigo="06", documento="TESTE-001"):
    acoes = {"02": "Entrada Confirmada", "06": "Liquidado", "10": "Baixa",
             "12": "Abatimento Concedido", "14": "Prorrogado"}
    return [{"numero_titulo": documento, "valor_titulo": "250,00", "valor_titulo_arq": "250,00",
             "valor_pago": "250,00" if codigo == "06" else "0,00",
             "abatimento": "12,34" if codigo == "12" else "0,00",
             "data_ocorrencia": "09/09/2026", "acao_tomada": acoes[codigo], "status": "OK"}]


def preparar(monkeypatch, linhas, resposta):
    monkeypatch.setattr(retorno, "em_processamento", lambda *_: False)
    monkeypatch.setattr(retorno, "ja_processado", lambda *_: False)
    monkeypatch.setattr(retorno, "validar_banco_conta", lambda *_: 395)
    monkeypatch.setattr(retorno, "enviar", lambda *_: {"quantidadeTitulos": len(linhas)})
    monkeypatch.setattr(retorno, "extrair_titulos", lambda *_: linhas)
    monkeypatch.setattr(retorno, "verificar_criticas", lambda *_: [])
    monkeypatch.setattr(retorno, "soltar_trava", lambda *_: None)
    chamada = Mock(return_value=resposta)
    monkeypatch.setattr(retorno, "processar_arquivo", chamada)
    return chamada


@pytest.mark.parametrize("codigo,contador", [("02", "confirmacao_entrada"), ("06", "liquidacao"),
                                           ("10", "baixa"), ("12", "abatimento_concedido"),
                                           ("14", "prorrogacao")])
def test_processamento_exige_acao_e_contador_correspondentes(tmp_path, monkeypatch, codigo, contador):
    chamada = preparar(monkeypatch, grade(codigo), {"message": "OK", contador: 1, "DifSistema": 0})
    resultado = retorno.processar(None, arquivo(tmp_path, codigo), dry_run=False, conta_bb_api=395)
    assert chamada.call_count == 1
    assert resultado["processado"] and resultado["estado_final"] == "processado_smart"


@pytest.mark.parametrize("mudanca", [
    {"acao_tomada": "Ocorrência não encontrada"}, {"acao_tomada": "Baixa"},
    {"numero_titulo": "OUTRO"}, {"valor_pago": "249,99"}, {"abatimento": "3,00"},
    {"data_ocorrencia": "08/09/2026"}, {"status": "Título não encontrado"},
    {"valor_titulo": "251,00"},
])
def test_divergencia_na_grade_impede_processamento(tmp_path, monkeypatch, mudanca):
    linhas = grade()
    linhas[0].update(mudanca)
    chamada = preparar(monkeypatch, linhas, {"message": "OK", "liquidacao": 1})
    resultado = retorno.processar(None, arquivo(tmp_path), dry_run=False, conta_bb_api=395)
    chamada.assert_not_called()
    assert resultado["estado_final"] == "recusado_portao"


@pytest.mark.parametrize("resposta", [
    {}, {"liquidacao": 1}, {"message": "OK"}, {"message": "OK", "liquidacao": 2},
    {"message": "OK", "liquidacao": 1, "refinan": 1},
    {"message": "OK", "liquidacao": 1, "DifSistema": 1},
    {"message": "OK", "liquidacao": True}, {"message": "OK", "liquidacao": 1.9},
    {"message": "OK", "liquidacao": 1, "desconhecido": "erro"}, "erro", None,
])
def test_resposta_incompleta_ou_divergente_fica_inconclusiva(tmp_path, monkeypatch, resposta):
    chamada = preparar(monkeypatch, grade(), resposta)
    resultado = retorno.processar(None, arquivo(tmp_path), dry_run=False, conta_bb_api=395)
    assert chamada.call_count == 1
    assert not resultado["processado"] and resultado["estado_final"] == "inconclusivo"


def test_queda_depois_do_envio_nao_e_confirmacao(tmp_path, monkeypatch):
    chamada = preparar(monkeypatch, grade(), {})
    chamada.side_effect = TimeoutError("resposta perdida")
    resultado = retorno.processar(None, arquivo(tmp_path), dry_run=False, conta_bb_api=395)
    assert resultado["passo_irreversivel_chamado"] and not resultado["processado"]
    assert resultado["estado_final"] == "inconclusivo"
    assert chamada.call_count == 1


def test_conta_diferente_recusa_antes_do_upload(tmp_path, monkeypatch):
    preparar(monkeypatch, grade(), {})
    upload = Mock()
    monkeypatch.setattr(retorno, "enviar", upload)
    with pytest.raises(retorno.ErroRetorno, match="conta Smart"):
        retorno.processar(None, arquivo(tmp_path), dry_run=False, conta_bb_api=999)
    upload.assert_not_called()


def test_dry_run_confere_mas_nao_processa(tmp_path, monkeypatch):
    chamada = preparar(monkeypatch, grade(), {})
    resultado = retorno.processar(None, arquivo(tmp_path), dry_run=True, conta_bb_api=395)
    assert resultado["estado_final"] == "dry_run"
    chamada.assert_not_called()


def test_grade_vazia_nao_e_sucesso(tmp_path, monkeypatch):
    chamada = preparar(monkeypatch, [], {})
    resultado = retorno.processar(None, arquivo(tmp_path), dry_run=False, conta_bb_api=395)
    assert resultado["estado_final"] == "recusado_portao"
    chamada.assert_not_called()


def test_envelope_misto_nao_aceita_outra_conta(tmp_path):
    linhas = arquivo(tmp_path).read_text().splitlines()
    linhas[1] = linhas[1][:31] + "7654321" + linhas[1][38:]
    assert not bb_api.avaliar_grade(linhas, grade(), 1)["liberado"]


def test_espaco_duplo_no_documento_casa_com_a_grade_colapsada(tmp_path, monkeypatch):
    """14/09/2026: o ERP guarda `Q  19902/A`, o arquivo leva os dois espaços e a grade
    volta colapsada em `Q 19902/A`. A comparação crua recusou o arquivo inteiro de 100
    liquidações (BBAPI000002632A181A8EADBC493.RET), 99 delas idênticas."""
    chamada = preparar(monkeypatch, grade(documento="Q 19902/A"),
                       {"message": "OK", "liquidacao": 1, "DifSistema": 0})
    resultado = retorno.processar(None, arquivo(tmp_path, documento="Q  19902/A"),
                                  dry_run=False, conta_bb_api=395)
    assert chamada.call_count == 1
    assert resultado["processado"] and resultado["estado_final"] == "processado_smart"


@pytest.mark.parametrize("na_grade", ["Q 19902/B", "Q 19902-A", "Q19902/A", "BQ 19902/A"])
def test_so_o_espaco_interno_e_tolerado_no_documento(tmp_path, monkeypatch, na_grade):
    chamada = preparar(monkeypatch, grade(documento=na_grade), {"message": "OK", "liquidacao": 1})
    resultado = retorno.processar(None, arquivo(tmp_path, documento="Q  19902/A"),
                                  dry_run=False, conta_bb_api=395)
    chamada.assert_not_called()
    assert resultado["estado_final"] == "recusado_portao"
