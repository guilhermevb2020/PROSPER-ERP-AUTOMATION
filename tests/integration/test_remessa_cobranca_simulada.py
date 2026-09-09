"""Geracao CNAB400 com resposta Smart simulada e persistencia real em tmp."""
import base64
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

import pytest

FORM = '''<form name="ConfirmarDadosConta">
<input name="NumSequencial" value="123"><input name="existeEntrada" value="1">
<input type="checkbox" name="prazo1" id="prazo" value="101" checked>
<input type="checkbox" name="prazo2" id="prazo" value="102">
</form>'''
CNAB = ('01REMESSA'.ljust(400) + '\r\n' + '1'.ljust(400) + '\r\n' + '9'.ljust(400) + '\r\n').encode()
# Mesmo nome, conteudo diferente e ainda valido (o detalhe muda no ultimo char).
CNAB_OUTRO = ('01REMESSA'.ljust(400) + '\r\n' + '1'.ljust(399) + 'X' + '\r\n' + '9'.ljust(400) + '\r\n').encode()


@pytest.fixture
def robo(monkeypatch, tmp_path):
    pasta = Path(__file__).resolve().parents[2] / 'src/processors/web/robo_remessa'
    monkeypatch.syspath_prepend(str(pasta))
    with patch.dict(sys.modules):
        for nome in ('_nextcloud', '_sessao', 'gerar', 'login', 'remessa_config', 'robo_remessa'):
            sys.modules.pop(nome, None)
        r = importlib.import_module('robo_remessa')
        monkeypatch.setattr(r.cfg, 'PASTA_REMESSAS', str(tmp_path / 'remessas'))
        monkeypatch.setattr(r.cfg, 'ARQ_CONTROLE', str(tmp_path / 'controle.csv'))
        monkeypatch.setattr(r.cfg, 'ENVIAR_NEXTCLOUD', True)
        monkeypatch.setattr(r.ger, 'filtrar', Mock(return_value=FORM))
        monkeypatch.setattr(r, 'baixar_id', Mock(return_value=('teste.REM', CNAB)))
        monkeypatch.setattr(r.nuvem, 'enviar', Mock(return_value=(True, 'nuvem simulada', 'OK')))
        resultado = base64.b64encode(json.dumps({'idsSucesso': {'1': 42}}).encode()).decode()
        resp = SimpleNamespace(status=200, url='https://smart.invalid/gridremessagerada.php?resultado='+resultado, body=lambda:b'')
        ctx = SimpleNamespace(request=SimpleNamespace(post=Mock(return_value=resp)))
        yield r, ctx


def test_gera_baixa_valida_grava_e_nao_rebaixa(robo):
    r, ctx = robo
    out = r.ciclo_conta(ctx, '1', 'Conta sintetica', '2', dry_run=False)
    assert out['gerou'] and out['baixados'] == 1 and out['ids'] == [42]
    assert (Path(r.cfg.PASTA_REMESSAS) / 'teste.REM').read_bytes() == CNAB
    assert r.ler_controle()['42']['titulos'] == '1'
    corpo = parse_qs(ctx.request.post.call_args.kwargs['data'])
    assert corpo['prazo1'] == ['101'] and 'prazo2' not in corpo
    assert r.processar(ctx, [{'id':42}]) == 0
    r.baixar_id.assert_called_once()
    r.nuvem.enviar.assert_called_once()


def test_dry_run_nao_gera_baixa_ou_envia(robo):
    r, ctx = robo
    out = r.ciclo_conta(ctx, '1', 'Conta sintetica', '2', dry_run=True)
    assert not out['gerou']
    ctx.request.post.assert_not_called()
    r.baixar_id.assert_not_called()
    r.nuvem.enviar.assert_not_called()


@pytest.mark.parametrize('dados', [b'<html>login</html>', b'', b'01REMESSA\n1\n9'])
def test_download_invalido_nao_vira_remessa(robo, dados):
    r, ctx = robo
    r.baixar_id.return_value = ('teste.REM', dados)
    assert r.processar(ctx, [{'id':42}]) == 0
    assert not r.ler_controle()
    r.nuvem.enviar.assert_not_called()


def test_falha_nextcloud_preserva_arquivo_local(robo):
    r, ctx = robo
    r.nuvem.enviar.return_value = (False, 'nuvem simulada', 'indisponivel')
    assert r.processar(ctx, [{'id':42}]) == 1
    assert (Path(r.cfg.PASTA_REMESSAS) / 'teste.REM').read_bytes() == CNAB
    assert '42' in r.ler_controle()


def test_recupera_geracao_sem_ids_pela_listagem(robo, monkeypatch):
    r, ctx = robo
    ctx.request.post.return_value = SimpleNamespace(status=200, url='', body=lambda:b'Sem ids')
    monkeypatch.setattr(r, 'listar_remessas', Mock(return_value=[{'id':42}]))
    out = r.ciclo_conta(ctx, '1', 'Conta sintetica', '2', dry_run=False)
    assert out['gerou'] and out['baixados'] == 1
    assert out['motivo'] == 'recuperado pela listagem'
    ctx.request.post.assert_called_once()


def test_nome_repetido_no_disco_sobe_ao_nextcloud_com_o_nome_do_smart(robo):
    """Duas contas, mesmo dia, mesmo sequencial: o disco desempata com `_dup`, mas o
    Nextcloud recebe o nome do Smart — o banco le o sequencial do nome e recusaria
    `CB08090000011_dup212306.REM` (WJ MOREIRA, 08/09/2026)."""
    r, ctx = robo
    assert r.processar(ctx, [{'id': 42}]) == 1
    r.baixar_id.return_value = ('teste.REM', CNAB_OUTRO)
    assert r.processar(ctx, [{'id': 43}]) == 1
    locais = sorted(p.name for p in Path(r.cfg.PASTA_REMESSAS).iterdir())
    assert locais[0] == 'teste.REM'
    assert locais[1].startswith('teste_dup') and locais[1].endswith('.REM')
    assert (Path(r.cfg.PASTA_REMESSAS) / locais[1]).read_bytes() == CNAB_OUTRO
    assert r.ler_controle()['43']['arquivo'] == locais[1]
    assert [c.args[1] for c in r.nuvem.enviar.call_args_list] == ['teste.REM', 'teste.REM']


@pytest.mark.parametrize('local, nuvem', [
    ('CB08090000011_dup212306.REM', 'CB08090000011.REM'),
    ('CB08090000011_dup212306.rem', 'CB08090000011.rem'),
    ('CB08090000011.REM', 'CB08090000011.REM'),
    ('CB08090000011_dup2123.REM', 'CB08090000011_dup2123.REM'),   # so o formato exato do disco
])
def test_nome_para_nuvem_tira_so_o_sufixo_dup_do_disco(robo, local, nuvem):
    r, _ = robo
    assert r.nome_para_nuvem(local) == nuvem


def test_subir_pendentes_sobe_o_dup_com_o_nome_do_smart(robo, monkeypatch):
    r, _ = robo
    pasta = Path(r.cfg.PASTA_REMESSAS)
    pasta.mkdir(parents=True)
    (pasta / 'CB08090000011.REM').write_bytes(CNAB)
    (pasta / 'CB08090000011_dup212306.REM').write_bytes(CNAB_OUTRO)
    monkeypatch.setattr(r.nuvem, 'disponivel', lambda: True)
    assert r.subir_pendentes() == r.SAIU_OK
    enviados = [(c.args[0], c.args[1]) for c in r.nuvem.enviar.call_args_list]
    assert enviados == [(CNAB, 'CB08090000011.REM'), (CNAB_OUTRO, 'CB08090000011.REM')]


def _args(r, *extra):
    return r.montar_parser().parse_args(['--gerar', '--conta', '1', *extra])


def test_simular_forca_dry_run_mesmo_com_dry_run_desligado_no_ambiente(robo, monkeypatch):
    """No container o robo_remessa.env poe DRY_RUN_REM=false: `--gerar` sem flag gera de
    verdade. `--simular` e a saida para olhar a fila sem consumir sequencial."""
    r, ctx = robo
    monkeypatch.setattr(r.cfg, 'DRY_RUN', False)
    monkeypatch.setattr(r, 'resolver_conta', Mock(return_value=('1', 'Conta sintetica')))
    assert r.executar(ctx, _args(r, '--simular')) == r.SAIU_OK
    ctx.request.post.assert_not_called()
    r.nuvem.enviar.assert_not_called()


def test_sem_flag_com_dry_run_desligado_gera_de_verdade(robo, monkeypatch):
    r, ctx = robo
    monkeypatch.setattr(r.cfg, 'DRY_RUN', False)
    monkeypatch.setattr(r, 'resolver_conta', Mock(return_value=('1', 'Conta sintetica')))
    assert r.executar(ctx, _args(r)) == r.SAIU_OK
    ctx.request.post.assert_called_once()


def test_pra_valer_e_simular_nao_convivem(robo):
    r, _ = robo
    with pytest.raises(SystemExit):
        _args(r, '--pra-valer', '--simular')
