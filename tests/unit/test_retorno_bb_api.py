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


# --------------------------------------------------------------------------- #
# Título que o Smart já tinha liquidado (BUG-679)
# --------------------------------------------------------------------------- #
import base64  # noqa: E402

DIV = '<div class="w-full leading-5 text-sm">'


def arquivo_n(tmp_path, documentos):
    """Como `arquivo`, mas com N liquidações — a forma das entregas 26 e 27."""
    header, trailer = [list(" " * 400) for _ in range(2)]
    header[:19] = "02RETORNO01COBRANCA"
    header[26:40] = "03867" + "00098691" + "7"
    header[76:79] = "001"
    header[149:156] = "3770013"
    trailer[:7] = "9201001"
    linhas = [header]
    for i, documento in enumerate(documentos, 1):
        assert len(documento) <= 10
        documento = documento.ljust(10)
        detalhe = list(" " * 400)
        detalhe[0] = "7"
        detalhe[17:31] = header[26:40]
        detalhe[31:38] = "3770013"
        detalhe[38:63] = f"00000003950000000000{i:05d}"
        detalhe[63:80] = f"3770013{i:010d}"
        detalhe[108:110] = "06"
        detalhe[110:116] = "090926"
        detalhe[116:126] = documento
        detalhe[152:165] = "0000000025000"
        detalhe[253:266] = "0000000025000"
        linhas.append(detalhe)
    linhas.append(trailer)
    for i, linha in enumerate(linhas, 1):
        linha[394:400] = f"{i:06d}"
        assert len(linha) == 400
    p = tmp_path / "BBAPI.RET"
    p.write_bytes(("\r\n".join("".join(l) for l in linhas) + "\r\n").encode("latin-1"))
    return p


def grade_n(documentos):
    return [g for d in documentos for g in grade(documento=d.strip())]


def varretorno(html):
    return base64.b64encode(html.encode("latin-1")).decode("ascii")


def ja_liquidados(*documentos):
    """A mensagem real da entrega 27: um `<div>` por título, com espaço de alinhamento."""
    return varretorno("".join(f"{DIV}Título {d}   já liquidado anteriormente</div>" for d in documentos))


def por_operacao(*documentos):
    """A mensagem da entrega 24: OUTRO motivo, em títulos que o Smart processou."""
    return varretorno("".join(
        f'{DIV}Título <span class="font-bold">{d}</span> já liquidado via pagamento da '
        f'<span class="font-bold">Op. 65432</span></div>' for d in documentos))


def test_titulo_ja_liquidado_conta_como_entregue(tmp_path, monkeypatch):
    """14/09/2026, entrega 27: 44 liquidações, `liquidacao=36` + `refinan=8`, os 8 nomeados.

    A soma fecha e nenhuma baixa faltou — os 44 estavam quitados no ERP. Sem isto a
    entrega fica pendente para sempre, sem job que a feche (BUG-679).
    """
    documentos = ["TESTE-001", "TESTE-002"]
    chamada = preparar(monkeypatch, grade_n(documentos),
                       {"message": "OK", "liquidacao": 1, "refinan": 1, "msgLiquidados": True,
                        "DifSistema": 0, "varRetorno2": ja_liquidados("TESTE-002")})
    resultado = retorno.processar(None, arquivo_n(tmp_path, documentos), dry_run=False, conta_bb_api=395)
    assert chamada.call_count == 1
    assert resultado["processado"] and resultado["estado_final"] == "processado_smart"


def test_entrega_inteira_ja_liquidada_fecha_sem_contador_de_liquidacao(tmp_path, monkeypatch):
    """11/09/2026, entrega 22: um título só, `liquidacao` ausente e `refinan=1`."""
    chamada = preparar(monkeypatch, grade(),
                       {"message": "OK", "refinan": 1, "msgLiquidados": True,
                        "DifSistema": 0, "varRetorno2": ja_liquidados("TESTE-001")})
    resultado = retorno.processar(None, arquivo(tmp_path), dry_run=False, conta_bb_api=395)
    assert chamada.call_count == 1
    assert resultado["processado"] and resultado["estado_final"] == "processado_smart"


@pytest.mark.parametrize("resposta", [
    {"refinan": 1},                                                             # sem a mensagem
    {"refinan": 1, "msgLiquidados": True},                                       # mensagem ausente
    {"refinan": 1, "msgLiquidados": "1", "varRetorno2": ja_liquidados("TESTE-001")},   # flag não booleana
    {"refinan": 2, "msgLiquidados": True, "varRetorno2": ja_liquidados("TESTE-001")},  # nomeia menos
    {"refinan": 1, "msgLiquidados": True, "varRetorno2": ja_liquidados("T-1", "T-2")},  # nomeia mais
    {"refinan": 1, "msgLiquidados": True, "varRetorno2": ja_liquidados("DE-OUTRO")},   # não é nosso
    {"refinan": 1, "msgLiquidados": True, "varRetorno2": por_operacao("TESTE-001")},   # outro motivo
    {"refinan": "x", "msgLiquidados": True, "varRetorno2": ja_liquidados("TESTE-001")},  # ilegível
])
def test_ja_liquidado_sem_prova_titulo_a_titulo_fica_inconclusivo(tmp_path, monkeypatch, resposta):
    """⛔ O contador sozinho não fecha entrega: o Smart tem de NOMEAR cada título."""
    chamada = preparar(monkeypatch, grade(), {"message": "OK", "DifSistema": 0, **resposta})
    resultado = retorno.processar(None, arquivo(tmp_path), dry_run=False, conta_bb_api=395)
    assert chamada.call_count == 1
    assert not resultado["processado"] and resultado["estado_final"] == "inconclusivo"


def test_refinan_nao_pode_exceder_as_liquidacoes_enviadas(tmp_path, monkeypatch):
    """Entrega de BAIXA não absorve `refinan`: ali ele é divergência."""
    chamada = preparar(monkeypatch, grade("10"),
                       {"message": "OK", "baixa": 1, "refinan": 1, "msgLiquidados": True,
                        "DifSistema": 0, "varRetorno2": ja_liquidados("TESTE-001")})
    resultado = retorno.processar(None, arquivo(tmp_path, "10"), dry_run=False, conta_bb_api=395)
    assert chamada.call_count == 1
    assert not resultado["processado"] and resultado["estado_final"] == "inconclusivo"


def encerrados(*, por_op=(), anteriormente=()):
    """A mensagem real da entrega 43: os dois motivos no MESMO `varRetorno2`."""
    return varretorno(
        "".join(f'{DIV}Título <span class="font-bold">{d}</span> já liquidado via pagamento da '
                f'<span class="font-bold">Op. 65519</span></div>' for d in por_op)
        + "".join(f"{DIV}Título {d}   já liquidado anteriormente</div>" for d in anteriormente))


def test_titulo_quitado_no_pagamento_de_operacao_conta_como_entregue(tmp_path, monkeypatch):
    """18/09/2026, entrega 43: 3 liquidações, `refinan=2` + `tituloPagtoOperacao=1`, sem
    `liquidacao`, os três nomeados. O contrato não conhecia o contador: inconclusivo e exit 6."""
    documentos = ["TESTE-001", "TESTE-002", "TESTE-003"]
    chamada = preparar(monkeypatch, grade_n(documentos),
                       {"message": "OK", "refinan": 2, "tituloPagtoOperacao": 1, "msgLiquidados": True,
                        "DifSistema": 0,
                        "varRetorno2": encerrados(por_op=["TESTE-001"], anteriormente=["TESTE-002", "TESTE-003"])})
    resultado = retorno.processar(None, arquivo_n(tmp_path, documentos), dry_run=False, conta_bb_api=395)
    assert chamada.call_count == 1
    assert resultado["processado"] and resultado["estado_final"] == "processado_smart"


def test_so_o_contador_de_operacao_tambem_fecha(tmp_path, monkeypatch):
    chamada = preparar(monkeypatch, grade(),
                       {"message": "OK", "tituloPagtoOperacao": 1, "DifSistema": 0,
                        "varRetorno2": encerrados(por_op=["TESTE-001"])})
    resultado = retorno.processar(None, arquivo(tmp_path), dry_run=False, conta_bb_api=395)
    assert chamada.call_count == 1
    assert resultado["processado"] and resultado["estado_final"] == "processado_smart"


@pytest.mark.parametrize("resposta", [
    {"liquidacao": 1, "tituloPagtoOperacao": 1},                                                 # contador sem nome
    {"liquidacao": 1, "tituloPagtoOperacao": 1, "varRetorno2": ja_liquidados("TESTE-001")},       # frase do OUTRO
    {"liquidacao": 1, "tituloPagtoOperacao": 1, "varRetorno2": encerrados(por_op=["DE-OUTRO"])},  # não é nosso
    {"tituloPagtoOperacao": 2, "varRetorno2": encerrados(por_op=["TESTE-001"])},                  # nomeia menos
    {"liquidacao": 1, "tituloPagtoOperacao": 1,
     "varRetorno2": encerrados(por_op=["TESTE-001", "TESTE-002"])},                               # nomeia mais
    {"liquidacao": 1, "tituloPagtoOperacao": "x", "varRetorno2": encerrados(por_op=["TESTE-001"])},  # ilegível
    # ilegível escondido atrás de um `refinan` bem provado
    {"liquidacao": 1, "tituloPagtoOperacao": "x", "refinan": 1, "msgLiquidados": True,
     "varRetorno2": ja_liquidados("TESTE-001")},
    # o MESMO título citado pelos dois contadores: a soma fecharia (2 de 2) sem provar o TESTE-002
    {"tituloPagtoOperacao": 1, "refinan": 1, "msgLiquidados": True,
     "varRetorno2": encerrados(por_op=["TESTE-001"], anteriormente=["TESTE-001"])},
])
def test_pagamento_de_operacao_sem_prova_titulo_a_titulo_fica_inconclusivo(tmp_path, monkeypatch, resposta):
    """⛔ Mesma régua do `refinan`: o contador sozinho não fecha entrega."""
    documentos = ["TESTE-001", "TESTE-002"]
    chamada = preparar(monkeypatch, grade_n(documentos), {"message": "OK", "DifSistema": 0, **resposta})
    resultado = retorno.processar(None, arquivo_n(tmp_path, documentos), dry_run=False, conta_bb_api=395)
    assert chamada.call_count == 1
    assert not resultado["processado"] and resultado["estado_final"] == "inconclusivo"


def test_contador_de_operacao_fora_de_liquidacao_continua_divergencia(tmp_path, monkeypatch):
    """Em BAIXA o contador não absorve nada: ali o Smart processa e a frase é só aviso."""
    chamada = preparar(monkeypatch, grade("10"),
                       {"message": "OK", "baixa": 1, "tituloPagtoOperacao": 1, "DifSistema": 0,
                        "varRetorno2": encerrados(por_op=["TESTE-001"])})
    resultado = retorno.processar(None, arquivo(tmp_path, "10"), dry_run=False, conta_bb_api=395)
    assert chamada.call_count == 1
    assert not resultado["processado"] and resultado["estado_final"] == "inconclusivo"


def test_mensagem_de_liquidado_por_operacao_nao_atrapalha_entrega_normal(tmp_path, monkeypatch):
    """14/09/2026, entrega 24: `varRetorno2` preenchido, sem `refinan`, tudo processado."""
    chamada = preparar(monkeypatch, grade("10"),
                       {"message": "OK", "baixa": 1, "DifSistema": 0,
                        "varRetorno2": por_operacao("TESTE-001")})
    resultado = retorno.processar(None, arquivo(tmp_path, "10"), dry_run=False, conta_bb_api=395)
    assert chamada.call_count == 1
    assert resultado["processado"] and resultado["estado_final"] == "processado_smart"
