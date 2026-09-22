import hashlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src" / "processors" / "web" / "retorno_cobranca"))

import retorno  # noqa: E402


def _arquivo_valido(tmp_path):
    cabecalho = "0" + " " * 399
    detalhe = list("1" + " " * 399)
    detalhe[37:62] = "0" * 25
    trailer = "9" + " " * 399
    conteudo = (
        ("\r\n".join([cabecalho, "".join(detalhe), trailer]) + "\r\n")
        .encode("iso-8859-1")
    )
    sha256 = hashlib.sha256(conteudo).hexdigest()
    caminho = tmp_path / f"DEP010926123{sha256[:16].upper()}.RET"
    caminho.write_bytes(conteudo)
    return caminho


def _grade(**trocas):
    linha = {
        "valor_titulo": "50.880,00",
        "valor_titulo_arq": "50.880,00",
        "numero_titulo": "1856-001",
        "acao_tomada": "Liquidado",
        "status": "OK",
        "sacado": "SACADO",
    }
    linha.update(trocas)
    return [linha]


def _preparar(monkeypatch, grade):
    monkeypatch.setattr(retorno, "em_processamento", lambda *_: False)
    monkeypatch.setattr(retorno, "ja_processado", lambda *_: False)
    monkeypatch.setattr(retorno, "validar_banco_conta", lambda *_: "349")
    monkeypatch.setattr(
        retorno,
        "enviar",
        lambda *_: {"quantidadeTitulos": 1, "valorTotalTitulos": "50.880,00"},
    )
    monkeypatch.setattr(retorno, "extrair_titulos", lambda *_: grade)
    monkeypatch.setattr(retorno, "verificar_criticas", lambda *_: [])
    monkeypatch.setattr(retorno, "soltar_trava", lambda *_: None)


def test_dry_run_executa_portao_e_nao_chama_passo_irreversivel(tmp_path, monkeypatch):
    _preparar(monkeypatch, _grade())
    monkeypatch.setattr(
        retorno,
        "processar_arquivo",
        lambda *_: (_ for _ in ()).throw(AssertionError("nao pode processar")),
    )

    caminho = _arquivo_valido(tmp_path)
    resultado = retorno.processar(None, caminho, dry_run=True, modo_deposito=True)

    assert resultado["estado_final"] == "dry_run"
    assert resultado["portao"]["liberado"] is True
    assert resultado["passo_irreversivel_chamado"] is False
    assert resultado["sha256"] == hashlib.sha256(caminho.read_bytes()).hexdigest()


def test_portao_recusado_nao_chama_passo_irreversivel(tmp_path, monkeypatch):
    _preparar(monkeypatch, _grade(acao_tomada="Baixa"))
    monkeypatch.setattr(
        retorno,
        "processar_arquivo",
        lambda *_: (_ for _ in ()).throw(AssertionError("nao pode processar")),
    )

    resultado = retorno.processar(
        None, _arquivo_valido(tmp_path), dry_run=False, modo_deposito=True
    )

    assert resultado["estado_final"] == "recusado_portao"
    assert resultado["portao"]["liberado"] is False
    assert resultado["passo_irreversivel_chamado"] is False


def test_nome_sem_hash_do_conteudo_e_recusado_antes_de_falar_com_smart(tmp_path):
    caminho = _arquivo_valido(tmp_path)
    legado = caminho.with_name("DEP010926123.RET")
    caminho.rename(legado)

    resultado = retorno.processar(None, legado, dry_run=False, modo_deposito=True)

    assert resultado["estado_final"] == "recusado_portao"
    assert "SHA-256" in resultado["motivo"]


def test_resultado_exato_comprova_uma_baixa(tmp_path, monkeypatch):
    _preparar(monkeypatch, _grade())
    chamadas = []

    def _processar(*_):
        chamadas.append(True)
        return {"message": "OK", "liquidacao": 1, "refinan": None}

    monkeypatch.setattr(retorno, "processar_arquivo", _processar)

    resultado = retorno.processar(
        None, _arquivo_valido(tmp_path), dry_run=False, modo_deposito=True
    )

    assert chamadas == [True]
    assert resultado["processado"] is True
    assert resultado["estado_final"] == "processado_smart"
    assert resultado["confirmacao_smart"]["comprovado"] is True


def test_resposta_sem_message_vai_para_inconclusivo_sem_provar_baixa(
        tmp_path, monkeypatch):
    _preparar(monkeypatch, _grade())
    monkeypatch.setattr(
        retorno, "processar_arquivo", lambda *_: {"liquidacao": 1}
    )

    resultado = retorno.processar(
        None, _arquivo_valido(tmp_path), dry_run=False, modo_deposito=True
    )

    assert resultado["passo_irreversivel_chamado"] is True
    assert resultado["processado"] is False
    assert resultado["estado_final"] == "inconclusivo"
    assert resultado["confirmacao_smart"]["comprovado"] is False
