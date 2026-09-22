"""Duas etapas e idempotencia do retorno, com transporte simulado."""
import hashlib
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def robo(monkeypatch, tmp_path):
    pasta = Path(__file__).resolve().parents[2] / 'src/processors/web/retorno_pagamento'
    monkeypatch.syspath_prepend(str(pasta))
    with patch.dict(sys.modules):
        for nome in ('_nextcloud', 'retorno_pagamento', 'retorno_pagamento_config', 'processar_retorno_pagamento'):
            sys.modules.pop(nome, None)
        r = importlib.import_module('processar_retorno_pagamento')
        monkeypatch.setattr(r.cfg, 'ARQ_CONTROLE', str(tmp_path / 'controle.csv'))
        monkeypatch.setattr(r, 'salvar_resposta', Mock(return_value='evidencia.html'))
        monkeypatch.setattr(r.nuvem, 'baixar', Mock(return_value=b'retorno sintetico'))
        monkeypatch.setattr(r.nuvem, 'mover_para', Mock())
        yield r


def resposta(html, ok=True):
    return {'ok_rede': ok, 'status': 200 if ok else None,
            'html': html, 'erro_rede': None if ok else 'timeout simulado'}


@pytest.mark.parametrize('duplicado', [False, True])
def test_dry_run_nao_confirma_nem_move_arquivo(robo, monkeypatch, duplicado):
    enviar = Mock(side_effect=AssertionError('POST proibido em dry run'))
    monkeypatch.setattr(robo.ret, 'enviar', enviar)
    feitos = {hashlib.md5(b'retorno sintetico').hexdigest()} if duplicado else set()
    robo.tratar(object(), 'teste.RET', True, feitos)
    enviar.assert_not_called()
    robo.nuvem.mover_para.assert_not_called()
    assert not Path(robo.cfg.ARQ_CONTROLE).exists()


def test_confirma_segunda_etapa_antes_de_arquivar(robo, monkeypatch):
    eventos = []
    def enviar(*args):
        eventos.append('upload')
        return resposta('<input name="target" value="staged/teste.ret">')
    def confirmar(ctx, url, target):
        assert target == 'staged/teste.ret'
        eventos.append('confirmacao')
        return resposta('<html>Processamento concluido</html>')
    monkeypatch.setattr(robo.ret, 'enviar', enviar)
    monkeypatch.setattr(robo.ret, 'confirmar', confirmar)
    robo.nuvem.mover_para.side_effect = lambda *args: eventos.append('arquivo')
    assert robo.tratar(object(), 'teste.RET', False, set()) == 'ok'
    assert eventos == ['upload', 'confirmacao', 'arquivo']
    assert hashlib.md5(b'retorno sintetico').hexdigest() in robo.hashes_ja_tratados()


@pytest.mark.parametrize('falha', ['rede_upload', 'sem_target', 'rede_confirmacao', 'sessao_confirmacao'])
def test_falha_mantem_arquivo_na_entrada(robo, monkeypatch, falha):
    upload = resposta('<input name="target" value="staged/teste.ret">')
    confirmacao = resposta('<html>Concluido</html>')
    if falha == 'rede_upload': upload = resposta(None, False)
    if falha == 'sem_target': upload = resposta('<html>Previa sem formulario</html>')
    if falha == 'rede_confirmacao': confirmacao = resposta(None, False)
    if falha == 'sessao_confirmacao': confirmacao = resposta('expira.php')
    monkeypatch.setattr(robo.ret, 'enviar', Mock(return_value=upload))
    monkeypatch.setattr(robo.ret, 'confirmar', Mock(return_value=confirmacao))
    assert robo.tratar(object(), 'teste.RET', False, set()) == 'pendente'
    robo.nuvem.mover_para.assert_not_called()
    assert not Path(robo.cfg.ARQ_CONTROLE).exists()
    if falha in ('rede_upload', 'sem_target'): robo.ret.confirmar.assert_not_called()


def test_duplicado_nao_repete_baixa(robo, monkeypatch):
    monkeypatch.setattr(robo.ret, 'enviar', Mock())
    feitos = {hashlib.md5(b'retorno sintetico').hexdigest()}
    assert robo.tratar(object(), 'teste.RET', False, feitos) == 'repete'
    robo.ret.enviar.assert_not_called()
    robo.nuvem.mover_para.assert_called_once()
