"""Persistência da entrega BB: uma única tentativa, mesmo após queda do ERP."""

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src/processors/web/robo_retorno"))

import artefatos  # noqa: E402
import bb_entrega  # noqa: E402
import retorno  # noqa: E402
import robo_retorno as robo  # noqa: E402
from test_retorno_bb_api import arquivo, grade, preparar  # noqa: E402


def ler_recibos(pasta):
    return [json.loads(p.read_text()) for p in pasta.rglob("*.json")]


def test_intencao_precede_smart_e_repeticao_usa_prova_sem_http(tmp_path, monkeypatch):
    caminho = arquivo(tmp_path)
    recibos = tmp_path / "recibos"
    chamada = preparar(monkeypatch, grade(), {})

    def confirmar(*_):
        dados = ler_recibos(recibos)
        assert len(dados) == 1
        assert dados[0]["schema"] == bb_entrega.SCHEMA
        assert dados[0]["metadados"]["etapa"] == "intencao"
        assert dados[0]["portao"]["liberado"]
        assert dados[0]["sha256"] == hashlib.sha256(caminho.read_bytes()).hexdigest()
        return {"message": "OK", "liquidacao": 1, "DifSistema": 0}

    chamada.side_effect = confirmar
    primeiro = bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos, dry_run=False)
    assert primeiro["processado"]
    assert len(ler_recibos(recibos)) == 2
    proibido = Mock(side_effect=AssertionError("repetição fez HTTP"))
    monkeypatch.setattr(retorno, "em_processamento", proibido)
    segundo = bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos, dry_run=False)
    assert segundo["estado_final"] == "ja_processado"
    assert segundo["reutilizado"]
    assert not segundo["passo_irreversivel_chamado"]
    assert chamada.call_count == 1
    proibido.assert_not_called()


@pytest.mark.parametrize("falha", [TimeoutError, KeyboardInterrupt])
def test_resposta_perdida_ou_processo_morto_nao_repete(tmp_path, monkeypatch, falha):
    caminho = arquivo(tmp_path)
    recibos = tmp_path / "recibos"
    chamada = preparar(monkeypatch, grade(), {})
    chamada.side_effect = falha("queda simulada")
    if falha is KeyboardInterrupt:
        with pytest.raises(KeyboardInterrupt):
            bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos, dry_run=False)
    else:
        assert bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos,
                                   dry_run=False)["inconclusivo"]
    segundo = bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos, dry_run=False)
    assert segundo["estado_final"] == "inconclusivo"
    assert not segundo["processado"]
    assert chamada.call_count == 1


@pytest.mark.parametrize("etapa", ["intencao", "resultado"])
def test_falha_na_persistencia_interrompe_e_nao_rearma(tmp_path, monkeypatch, etapa):
    caminho = arquivo(tmp_path)
    recibos = tmp_path / "recibos"
    chamada = preparar(monkeypatch, grade(), {"message": "OK", "liquidacao": 1})
    gravar = artefatos.gravar_recibo_atomico

    def falhar(*args, **kwargs):
        if kwargs["metadados"]["etapa"] == etapa:
            if etapa == "intencao":
                gravar(*args, **kwargs)  # queda depois da publicação, antes de retornar
            raise OSError("disco indisponível")
        return gravar(*args, **kwargs)

    monkeypatch.setattr(artefatos, "gravar_recibo_atomico", falhar)
    with pytest.raises(OSError):
        bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos, dry_run=False)
    monkeypatch.setattr(artefatos, "gravar_recibo_atomico", gravar)
    assert bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos,
                               dry_run=False)["inconclusivo"]
    assert chamada.call_count == (0 if etapa == "intencao" else 1)


def test_erro_auxiliar_apos_confirmacao_nao_perde_prova(tmp_path, monkeypatch):
    caminho = arquivo(tmp_path)
    recibos = tmp_path / "recibos"
    chamada = preparar(monkeypatch, grade(), {"message": "OK", "liquidacao": 1})
    monkeypatch.setattr(retorno, "verificar_criticas", Mock(side_effect=TimeoutError("consulta auxiliar")))
    with pytest.raises(TimeoutError):
        bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos, dry_run=False)
    assert bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos,
                               dry_run=False)["estado_final"] == "ja_processado"
    assert chamada.call_count == 1


def test_previa_nao_cria_intencao_e_depois_permite_processar(tmp_path, monkeypatch):
    caminho = arquivo(tmp_path)
    recibos = tmp_path / "recibos"
    chamada = preparar(monkeypatch, grade(), {"message": "OK", "liquidacao": 1})
    bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos, dry_run=True)
    assert all(r["metadados"]["etapa"] == "resultado" for r in ler_recibos(recibos))
    chamada.assert_not_called()
    assert bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos, dry_run=False)["processado"]
    assert chamada.call_count == 1


def test_entregas_concorrentes_do_mesmo_conteudo_nao_passam(tmp_path, monkeypatch):
    caminho = arquivo(tmp_path)
    recibos = tmp_path / "recibos"
    chamada = preparar(monkeypatch, grade(), {})

    def confirmar(*_):
        with pytest.raises(BlockingIOError):
            bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos, dry_run=False)
        return {"message": "OK", "liquidacao": 1}

    chamada.side_effect = confirmar
    assert bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos, dry_run=False)["processado"]
    assert chamada.call_count == 1


def test_recibo_divergente_nao_e_sucesso_nem_autoriza_reenvio(tmp_path, monkeypatch):
    caminho = arquivo(tmp_path)
    recibos = tmp_path / "recibos"
    chamada = preparar(monkeypatch, grade(), {"message": "OK", "liquidacao": 1})
    bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos, dry_run=False)
    for p in recibos.rglob("*.json"):
        dados = json.loads(p.read_text())
        if dados["metadados"]["etapa"] == "resultado":
            dados["resposta_processamento"]["liquidacao"] = 2
            p.write_text(json.dumps(dados))
    with pytest.raises(ValueError, match="sem prova"):
        bb_entrega.processar(None, caminho, conta=395, pasta_recibos=recibos, dry_run=False)
    assert chamada.call_count == 1


@pytest.mark.parametrize("pra_valer", [False, True])
def test_cli_bb_exige_flag_real_mesmo_com_env_legado_e_grava_recibos(tmp_path, monkeypatch, pra_valer):
    caminho = arquivo(tmp_path)
    recibos = tmp_path / "recibos"
    chamada = preparar(monkeypatch, grade(), {"message": "OK", "liquidacao": 1})
    monkeypatch.setattr(robo.cfg, "DRY_RUN", False)
    monkeypatch.setattr(robo.cfg, "ARQ_CONTROLE", str(tmp_path / "controle.csv"))
    monkeypatch.setattr(robo, "sync_playwright", MagicMock())
    monkeypatch.setattr(robo.smart_sessao, "sessao", MagicMock())
    monkeypatch.setattr(robo.smart_sessao, "sessao_viva", Mock(return_value=True))
    args = ["robo_retorno.py", "--pasta", str(tmp_path), "--conta-bb-api", "395",
            "--recibos-dir", str(recibos), "--pausa", "0"]
    monkeypatch.setattr(sys, "argv", args + (["--pra-valer"] if pra_valer else []))
    assert robo.main() == 0
    assert chamada.call_count == int(pra_valer)
    assert caminho.exists() is not pra_valer
    assert any(r["processado"] is pra_valer for r in ler_recibos(recibos))


@pytest.mark.parametrize("extras", [[], ["--deposito"], ["--aceitar-conta-desconhecida"], ["--limite", "0"]])
def test_cli_bb_configuracao_invalida_nao_abre_browser(tmp_path, monkeypatch, extras):
    browser = Mock(side_effect=AssertionError("browser não deveria abrir"))
    monkeypatch.setattr(robo, "sync_playwright", browser)
    args = ["robo_retorno.py", "--pasta", str(tmp_path), "--conta-bb-api", "395", *extras]
    if extras:
        args += ["--recibos-dir", str(tmp_path / "recibos")]
    monkeypatch.setattr(sys, "argv", args)
    assert robo.main() == 4
    browser.assert_not_called()
