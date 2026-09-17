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
<table><tr><td>125060-003</td><td>XPACE TECNOLOGIA LTDA</td><td>R$ 1.234,50</td><td>30/10/2026</td>
<td><input type="checkbox" name="prazo1" id="prazo" value="101" checked></td></tr>
<tr><td>125058-001</td><td>RADIADORES RADIAL LTDA</td><td>R$ 10,00</td><td>30/10/2026</td>
<td><input type="checkbox" name="prazo2" id="prazo" value="102"></td></tr></table>
</form>'''
CNAB = ('01REMESSA'.ljust(400) + '\r\n' + '1'.ljust(400) + '\r\n' + '9'.ljust(400) + '\r\n').encode()
# Mesmo nome, conteudo diferente e ainda valido (o detalhe muda no ultimo char).
CNAB_OUTRO = ('01REMESSA'.ljust(400) + '\r\n' + '1'.ljust(399) + 'X' + '\r\n' + '9'.ljust(400) + '\r\n').encode()


@pytest.fixture
def robo(monkeypatch, tmp_path):
    pasta = Path(__file__).resolve().parents[2] / 'src/processors/web/robo_remessa'
    monkeypatch.syspath_prepend(str(pasta))
    with patch.dict(sys.modules):
        for nome in ('_nextcloud', '_sessao', 'exclusoes', 'gerar', 'login', 'remessa_config', 'robo_remessa'):
            sys.modules.pop(nome, None)
        r = importlib.import_module('robo_remessa')
        monkeypatch.setattr(r.cfg, 'PASTA_REMESSAS', str(tmp_path / 'remessas'))
        monkeypatch.setattr(r.cfg, 'ARQ_CONTROLE', str(tmp_path / 'controle.csv'))
        monkeypatch.setattr(r.cfg, 'ENVIAR_NEXTCLOUD', True)
        monkeypatch.setattr(r.cfg, 'ARQ_EXCLUSOES', str(tmp_path / 'sem_lista.json'))
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


@pytest.mark.parametrize('banco, tipos, esperado', [
    ('001', ['7', '5', '7', '7'], 3),
    ('001', ['1', '5', '1'], 2),
    ('274', ['1', '2', '1'], 2),
])
def test_download_conta_instrucoes_sem_contar_complementos(robo, banco, tipos, esperado):
    r, ctx = robo
    header = list('01REMESSA'.ljust(400))
    header[76:79] = banco
    linhas = [''.join(header), *(tipo.ljust(400) for tipo in tipos), '9'.ljust(400)]
    dados = ('\r\n'.join(linhas) + '\r\n').encode('latin-1')
    r.baixar_id.return_value = ('teste.REM', dados)

    assert r.processar(ctx, [{'id': 42}]) == 1
    assert r.ler_controle()['42']['titulos'] == str(esperado)
    assert (Path(r.cfg.PASTA_REMESSAS) / 'teste.REM').read_bytes() == dados
    r.nuvem.enviar.assert_called_once_with(dados, 'teste.REM')


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


@pytest.mark.parametrize('prazo_ativo', [None, '10'])
def test_campos_disabled_nao_vao_no_post_nem_sobrescrevem_prazo_ativo(robo, prazo_ativo):
    r, _ = robo
    ativo = '' if prazo_ativo is None else f'<input name="qtdDias" id="qtdDias1" value="{prazo_ativo}">'
    form = FORM.replace('</form>', ativo + '''
      <input name="qtdDias" id="qtdDias3" disabled value="">
      <input type="checkbox" id="prazo" name="titulo3" value="103" checked disabled="disabled">
      <input name="desabilitado" value="nunca" DISABLED></form>''')
    corpo = parse_qs(r.ger.montar_post(r.ger.ler_form(form)), keep_blank_values=True)
    assert 'titulo3' not in corpo and 'desabilitado' not in corpo
    if prazo_ativo is None:
        assert 'qtdDias' not in corpo
    else:
        assert corpo['qtdDias'] == [prazo_ativo]


# --------------------------------------------------------------------------- #
# POST que NAO responde: a duvida e a mesma do POST sem ids (11/09/2026)
# --------------------------------------------------------------------------- #
def test_timeout_no_post_recupera_a_remessa_pela_listagem(robo, monkeypatch):
    """Timeout nao diz se o Smart gerou. O robo RECUPERA pela listagem em vez de
    pular a conta — senao a remessa fica orfa, com o sequencial ja consumido."""
    r, ctx = robo
    ctx.request.post.side_effect = Exception('read ETIMEDOUT')
    monkeypatch.setattr(r, 'listar_remessas', Mock(return_value=[{'id': 42}]))
    out = r.ciclo_conta(ctx, '1', 'Conta sintetica', '2', dry_run=False)
    assert out['gerou'] and out['ids'] == [42] and out['baixados'] == 1
    assert not out['incerto']
    r.nuvem.enviar.assert_called_once()


def test_timeout_sem_remessa_na_listagem_fica_INCERTO(robo, monkeypatch):
    r, ctx = robo
    ctx.request.post.side_effect = Exception('Timeout 90000ms exceeded.')
    monkeypatch.setattr(r, 'listar_remessas', Mock(return_value=[]))
    out = r.ciclo_conta(ctx, '1', 'Conta sintetica', '2', dry_run=False)
    assert out['incerto'] is True and not out['gerou']
    assert 'CONFERIR NO SMART' in out['motivo']
    r.baixar_id.assert_not_called()


def _rodada(r, ctx, monkeypatch):
    monkeypatch.setattr(r, 'carregar_contas_carteiras', Mock(return_value=({}, {})))
    monkeypatch.setattr(r, 'resolver_conta', Mock(return_value=('1', 'Conta sintetica')))
    args = r.montar_parser().parse_args(['--gerar', '--conta', '1', '--pra-valer'])
    return r.rodada_geracao(ctx, args, dry=False)


def test_conta_pulada_por_erro_faz_a_rodada_sair_INCOMPLETA(robo, monkeypatch):
    """O caso de 11/09/2026: duas contas estouraram, a rodada saiu 0 e o hub
    marcou sucesso. Conta pulada por erro nao e conta sem remessa."""
    r, ctx = robo
    monkeypatch.setattr(r.ger, 'filtrar', Mock(side_effect=Exception('read ETIMEDOUT')))
    assert _rodada(r, ctx, monkeypatch) == r.SAIU_RODADA_INCOMPLETA


def test_rodada_normal_continua_saindo_OK(robo, monkeypatch):
    r, ctx = robo
    assert _rodada(r, ctx, monkeypatch) == r.SAIU_OK


# --------------------------------------------------------------------------- #
# 17/09/2026 — a lista de exclusao do process-automation segura o titulo do sacado
# sem numero no endereco; o resto do arquivo passa
# --------------------------------------------------------------------------- #
def _lista(tmp_path, gerado_em, **titulo):
    item = {"documento": "125060-003", "nosso_numero": "827786", "sacado": "XPACE TECNOLOGIA LTDA",
            "sacado_cnpj": "28251112000134", "conta": "291", "motivo": "sacado sem numero no endereco", **titulo}
    caminho = tmp_path / "exclusoes.json"
    caminho.write_text(json.dumps({"versao": 1, "gerado_em": gerado_em.isoformat(), "validade_horas": 30,
                                   "titulos": {"948710": item}, "sacados": {}}), encoding="utf-8")
    return str(caminho)


def test_titulo_da_lista_de_exclusao_e_desmarcado_e_nao_vai_no_post(robo, monkeypatch, tmp_path):
    import datetime as dt
    r, ctx = robo
    monkeypatch.setattr(r.cfg, "ARQ_EXCLUSOES", _lista(tmp_path, dt.datetime.now(dt.timezone.utc)))
    form_lido = r.ger.ler_form(FORM)
    assert form_lido["titulos"][0]["celulas"][:2] == ["125060-003", "XPACE TECNOLOGIA LTDA"]
    out = r.ciclo_conta(ctx, "1", "mp cast", "2", dry_run=False)
    assert out["excluidos"] == 1
    # so o prazo1 estava marcado e ele foi excluido: nada a gerar, nada postado
    assert not out["gerou"] and "nenhum titulo" in out["motivo"]
    ctx.request.post.assert_not_called()


def test_lista_exclui_um_e_o_outro_marcado_gera_normalmente(robo, monkeypatch, tmp_path):
    import datetime as dt
    r, ctx = robo
    monkeypatch.setattr(r.cfg, "ARQ_EXCLUSOES", _lista(tmp_path, dt.datetime.now(dt.timezone.utc)))
    monkeypatch.setattr(r.ger, "filtrar", Mock(return_value=FORM.replace('value="102">', 'value="102" checked>')))
    out = r.ciclo_conta(ctx, "1", "mp cast", "2", dry_run=False)
    assert out["excluidos"] == 1 and out["gerou"] and out["titulos"] == 1
    corpo = parse_qs(ctx.request.post.call_args.kwargs["data"])
    assert "prazo1" not in corpo and corpo["prazo2"] == ["102"]


def test_lista_velha_ou_ausente_nao_exclui_e_avisa(robo, monkeypatch, tmp_path, capsys):
    import datetime as dt
    r, ctx = robo
    velha = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=31)
    monkeypatch.setattr(r.cfg, "ARQ_EXCLUSOES", _lista(tmp_path, velha))
    out = r.ciclo_conta(ctx, "1", "mp cast", "2", dry_run=False)
    assert out["excluidos"] == 0 and out["gerou"]
    assert "IGNORADA" in capsys.readouterr().out
    monkeypatch.setattr(r.cfg, "ARQ_EXCLUSOES", str(tmp_path / "nao_existe.json"))
    ctx.request.post.reset_mock()
    out = r.ciclo_conta(ctx, "1", "mp cast", "2", dry_run=False)
    assert out["excluidos"] == 0 and "prazo1" in parse_qs(ctx.request.post.call_args.kwargs["data"])


def test_documento_igual_de_outro_sacado_nao_casa(robo, monkeypatch, tmp_path):
    """O mesmo numero de documento existe em cedentes diferentes: exige o sacado (ou o
    nosso numero, ou o id) alem do documento."""
    import datetime as dt
    r, ctx = robo
    monkeypatch.setattr(r.cfg, "ARQ_EXCLUSOES", _lista(tmp_path, dt.datetime.now(dt.timezone.utc),
                                                          sacado="OUTRA EMPRESA LTDA", nosso_numero="1"))
    out = r.ciclo_conta(ctx, "1", "mp cast", "2", dry_run=False)
    assert out["excluidos"] == 0 and out["gerou"]
