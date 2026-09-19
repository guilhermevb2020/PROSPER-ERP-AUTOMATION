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
        for nome in ('_nextcloud', '_sessao', 'exclusoes', 'falhas', 'gerar', 'login', 'remessa_config', 'robo_remessa'):
            sys.modules.pop(nome, None)
        r = importlib.import_module('robo_remessa')
        monkeypatch.setattr(r.cfg, 'PASTA_REMESSAS', str(tmp_path / 'remessas'))
        monkeypatch.setattr(r.cfg, 'ARQ_CONTROLE', str(tmp_path / 'controle.csv'))
        monkeypatch.setattr(r.cfg, 'ENVIAR_NEXTCLOUD', True)
        monkeypatch.setattr(r.cfg, 'ARQ_EXCLUSOES', str(tmp_path / 'sem_lista.json'))
        monkeypatch.setattr(r.cfg, 'PASTA_FALHAS', str(tmp_path / 'falhas'))
        monkeypatch.setattr(r.cfg, 'ARQ_REMESSAS_GERADAS', str(tmp_path / 'remessas_geradas.json'))
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


# --------------------------------------------------------------------------- #
# 18/09/2026 — a grade REAL da geracao MoneyPlus (medida em 40 telas): o "Sacado" e o
# CNPJ, nao ha nome nem nosso numero, e o vencimento esta na linha. Entrada que vence
# hoje ou antes fica retida na fila (o banco recusa com 16/92); a lista casa por
# documento + CNPJ do sacado.
# --------------------------------------------------------------------------- #
_CABECALHO = ("<tr><th></th><th>Instrução</th><th>Tipo</th><th>Nº</th><th>M</th><th>Sacado</th>"
              "<th>Vencimento</th><th>Valor (R$)</th><th>Cedente</th><th>Operação</th><th>Data</th>"
              "<th>Prazo</th><th>Juros</th><th>Multa</th></tr>")


def _linha(nome, valor, doc, cnpj, venc, instrucao="Envio de cobrança", marcado=True, desabilitado=False):
    attrs = (" checked" if marcado else "") + (" disabled" if desabilitado else "")
    return (f'<tr><td><input type="checkbox" name="{nome}" id="prazo" value="{valor}"{attrs}></td>'
            f"<td>{instrucao}</td><td>DMR</td><td>{doc}</td><td>C</td><td>{cnpj}</td><td>{venc}</td>"
            f"<td>1456.00</td><td>15.570.552/0001-02</td><td>64494</td><td>19/08/2026</td><td></td>"
            f"<td>12.00 %</td><td>2.00 %</td></tr>")


def _form_real(*linhas, banco="274"):
    return ('<form name="ConfirmarDadosConta">'
            f'<input name="NumSequencial" value="1098"><input name="existeEntrada" value="1">'
            f'<input name="numBanco" value="{banco}"><table>{_CABECALHO}{"".join(linhas)}</table></form>')


TECNOMIDIA = "28.020.670/0001-99"
GRADE_VITORIA = _form_real(
    _linha("titulo0", "897629", "13274-001", TECNOMIDIA, "18/09/2026"),
    _linha("titulo1", "897628", "13274-002", TECNOMIDIA, "03/10/2026"),
    _linha("titulo2", "897630", "13100-001", "11.111.111/0001-11", "10/09/2026",
           instrucao="Quitação ou cancelamento", desabilitado=True),
    _linha("titulo3", "912990", "13466-001", "22.259.571/0001-88", "19/09/2026"),
)


@pytest.fixture
def hoje_18_09(robo, monkeypatch):
    import datetime as dt
    r, _ = robo
    monkeypatch.setattr(r.exclusoes, "hoje_sp", lambda: dt.date(2026, 9, 18))


def test_grade_real_e_lida_pelo_cabecalho(robo):
    r, _ = robo
    form = r.ger.ler_form(GRADE_VITORIA)
    assert [t["nome"] for t in form["titulos"]] == ["titulo0", "titulo1", "titulo3"]  # o desabilitado nao entra
    colunas = form["titulos"][0]["colunas"]
    assert colunas["Nº"] == "13274-001" and colunas["Sacado"] == TECNOMIDIA and colunas["Vencimento"] == "18/09/2026"
    assert colunas["Instrução"] == "Envio de cobrança"
    assert r.exclusoes.vencimento_da_linha(form["titulos"][0]).isoformat() == "2026-09-18"


def test_entrada_que_vence_hoje_fica_retida_e_o_resto_sai(robo, monkeypatch, hoje_18_09, capsys):
    """13274-001 TECNOMIDIA, 18/09/2026: vencimento de hoje, o MoneyPlus recusa com 16/92.
    Retido, continua na fila do Smart; o 13274-002 e o 13466-001 (vence amanha) saem."""
    r, ctx = robo
    monkeypatch.setattr(r.ger, "filtrar", Mock(return_value=GRADE_VITORIA))
    out = r.ciclo_conta(ctx, "312", "mp vitoria", "9", dry_run=False)
    assert [a["documento"] for a in out["retidos"]] == ["13274-001"] and out["excluidos"] == 0
    assert out["gerou"] and out["titulos"] == 2
    corpo = parse_qs(ctx.request.post.call_args.kwargs["data"])
    assert "titulo0" not in corpo and corpo["titulo1"] == ["897628"] and corpo["titulo3"] == ["912990"]
    assert "retido na fila: 13274-001" in capsys.readouterr().out


def test_tudo_retido_nao_gera_nada(robo, monkeypatch, hoje_18_09):
    r, ctx = robo
    monkeypatch.setattr(r.ger, "filtrar", Mock(return_value=_form_real(
        _linha("titulo0", "897629", "13274-001", TECNOMIDIA, "18/09/2026"),
        _linha("titulo1", "897631", "13275-001", TECNOMIDIA, "17/09/2026"))))
    out = r.ciclo_conta(ctx, "312", "mp vitoria", "9", dry_run=False)
    assert len(out["retidos"]) == 2 and not out["gerou"] and "nenhum titulo" in out["motivo"]
    ctx.request.post.assert_not_called()


def test_vencimento_de_amanha_outro_banco_e_outra_instrucao_nao_sao_retidos(robo, monkeypatch):
    import datetime as dt
    r, _ = robo
    form = r.ger.ler_form(GRADE_VITORIA)
    assert r.exclusoes.reter_vencidos(form, dt.date(2026, 9, 17), log=lambda *_: None) == []
    form = r.ger.ler_form(GRADE_VITORIA.replace('value="274"', 'value="001"'))
    assert r.exclusoes.reter_vencidos(form, dt.date(2026, 9, 18), log=lambda *_: None) == []
    form = r.ger.ler_form(_form_real(_linha("titulo0", "1", "13274-001", TECNOMIDIA, "18/09/2026",
                                            instrucao="Prorrogação de vencimento")))
    assert r.exclusoes.reter_vencidos(form, dt.date(2026, 9, 18), log=lambda *_: None) == []


def test_grade_sem_cabecalho_nao_retem_e_avisa(robo, monkeypatch, hoje_18_09, capsys):
    """Sem a coluna "Vencimento" legivel nada e retido: a conferencia do envio avisa."""
    r, ctx = robo
    sem_cabecalho = FORM.replace('<input name="existeEntrada" value="1">',
                                 '<input name="existeEntrada" value="1"><input name="numBanco" value="274">')
    monkeypatch.setattr(r.ger, "filtrar", Mock(return_value=sem_cabecalho))
    out = r.ciclo_conta(ctx, "1", "mp cast", "2", dry_run=False)
    assert out["retidos"] == [] and out["gerou"]
    assert "sem vencimento legivel" in capsys.readouterr().out


def test_lista_casa_pela_linha_real_documento_e_cnpj_do_sacado(robo, monkeypatch, tmp_path, hoje_18_09):
    """A grade real nao mostra nome nem nosso numero: o casamento de 17/09 nunca acharia
    a linha. Documento + CNPJ do sacado acha; CNPJ de outro sacado nao."""
    import datetime as dt
    r, ctx = robo
    agora = dt.datetime.now(dt.timezone.utc)
    monkeypatch.setattr(r.cfg, "ARQ_EXCLUSOES", _lista(tmp_path, agora, documento="13274-002",
                                                          sacado_cnpj="28020670000199", nosso_numero="827806",
                                                          sacado="TECNOMIDIA COMUNICACAO LTDA"))
    monkeypatch.setattr(r.ger, "filtrar", Mock(return_value=GRADE_VITORIA))
    out = r.ciclo_conta(ctx, "312", "mp vitoria", "9", dry_run=False)
    assert out["excluidos"] == 1 and [a["documento"] for a in out["retidos"]] == ["13274-001"]
    assert set(parse_qs(ctx.request.post.call_args.kwargs["data"])) & {"titulo0", "titulo1", "titulo3"} == {"titulo3"}
    monkeypatch.setattr(r.cfg, "ARQ_EXCLUSOES", _lista(tmp_path, agora, documento="13274-002",
                                                          sacado_cnpj="99999999000199", nosso_numero="1",
                                                          sacado="OUTRA"))
    ctx.request.post.reset_mock()
    assert r.ciclo_conta(ctx, "312", "mp vitoria", "9", dry_run=False)["excluidos"] == 0


# --------------------------------------------------------------------------- #
# 18/09/2026 — a remessa que o Smart gerou e que nao chegou ao banco deixa rastro.
# Em 15/09 a da MP PROSPERE (id 26381, 60 titulos) foi descartada por dois registros de
# 406 bytes (nosso numero de 17 digitos da BB Ativos) e sumiu com uma linha de log.
# --------------------------------------------------------------------------- #
def _registro_longo(doc="104-001", nosso="34913460000444530"):
    linha = list(" " * 400)
    linha[0] = "1"
    linha[70:81] = list("00000000000")
    linha[108:110] = list("01")
    linha[110:120] = list(doc.ljust(10))
    texto = "".join(linha)
    # o Smart escreve os 17 digitos no campo de 11: o registro cresce 6 bytes
    return texto[:70] + nosso + texto[81:]


def test_arquivo_descartado_vira_falha_com_os_culpados_nomeados(robo, monkeypatch, tmp_path):
    r, ctx = robo
    ruim = ('01REMESSA'.ljust(400) + '\r\n' + _registro_longo() + '\r\n' + '9'.ljust(400) + '\r\n').encode()
    r.baixar_id.return_value = ('CB15090000021.REM', ruim)
    grade = [{"documento": "104-001", "sacado_cnpj": "08.747.539/0003-82", "vencimento": "19/09/2026", "valor": "567.00"}]
    assert r.processar(ctx, [{"id": 26381, "rotulo": "mp prospere Envio de cobranca registrado", "conta": "404",
                               "titulos_grade": grade}]) == 0
    registro = json.loads((tmp_path / "falhas" / "26381.json").read_text(encoding="utf-8"))
    assert registro["conta"] == "404" and registro["motivo"].startswith("DESCARTADO")
    assert registro["nome_arquivo"] == "CB15090000021.REM"
    assert registro["titulos"][0]["documento"] == "104-001" and registro["titulos"][0]["nosso_numero"] == "34913460000444530"
    (culpado,) = registro["culpados"]
    assert culpado["documento"] == "104-001" and culpado["bytes"] == 406 and "outro banco" in culpado["motivo"]
    assert (tmp_path / "falhas" / "26381.REM").read_bytes() == ruim and registro["conteudo_cnab"] is True
    assert not r.ler_controle(), "arquivo descartado nao pode entrar no controle"


def test_download_que_falha_vira_falha_com_os_titulos_da_grade(robo, tmp_path):
    r, ctx = robo
    r.baixar_id.return_value = (None, None)
    r.processar(ctx, [{"id": 7, "rotulo": "mp cast Envio de cobranca registrado", "conta": "291",
                       "titulos_grade": [{"documento": "125060-003", "sacado_cnpj": "1", "vencimento": "", "valor": ""}]}])
    registro = json.loads((tmp_path / "falhas" / "7.json").read_text(encoding="utf-8"))
    assert registro["motivo"] == "download do Smart falhou" and registro["titulos"][0]["documento"] == "125060-003"
    assert registro["arquivo"] is None and not (tmp_path / "falhas" / "7.REM").exists()


def test_ciclo_leva_os_titulos_da_grade_so_para_o_arquivo_de_entradas(robo, monkeypatch, tmp_path, hoje_18_09):
    r, ctx = robo
    monkeypatch.setattr(r.ger, "filtrar", Mock(return_value=GRADE_VITORIA))
    resultado = base64.b64encode(json.dumps({'idsSucesso': {'1': 55, '3': 56}}).encode()).decode()
    ctx.request.post.return_value = SimpleNamespace(
        status=200, url='https://smart.invalid/gridremessagerada.php?resultado=' + resultado, body=lambda: b'')
    r.baixar_id.return_value = (None, None)
    r.ciclo_conta(ctx, "312", "mp vitoria", "9", dry_run=False)
    entradas = json.loads((tmp_path / "falhas" / "55.json").read_text(encoding="utf-8"))
    baixas = json.loads((tmp_path / "falhas" / "56.json").read_text(encoding="utf-8"))
    assert [t["documento"] for t in entradas["titulos"]] == ["13274-002", "13466-001"]  # 13274-001 retido
    assert baixas["titulos"] == []


def test_exportar_controle_diz_o_id_do_smart_pelo_nome_do_smart(robo, tmp_path):
    r, _ = robo
    controle = {"26271": {"arquivo": "CB09090000012.REM", "tipo": "mp prospere Envio", "md5": "a", "baixado_em": "x"},
                "26299": {"arquivo": "CB10090000013_dup211530.REM", "tipo": "mp prospere Envio", "md5": "b",
                          "baixado_em": "y"},
                # 18/09/2026: o mesmo nome em duas contas — os dois ficam, e o md5 separa
                "26249": {"arquivo": "CB08090000011.REM", "tipo": "mp prospere Envio", "md5": "c", "baixado_em": "z"},
                "26256": {"arquivo": "CB08090000011.REM", "tipo": "mp wj moreira Envio", "md5": "d", "baixado_em": "z"}}
    assert r.falhas.exportar_controle(controle) == 3
    mapa = json.loads((tmp_path / "remessas_geradas.json").read_text(encoding="utf-8"))
    assert [(c["id"], c["md5"]) for c in mapa["CB09090000012.REM"]] == [(26271, "a")]
    assert mapa["CB10090000013.REM"][0]["id"] == 26299
    assert sorted((c["id"], c["md5"]) for c in mapa["CB08090000011.REM"]) == [(26249, "c"), (26256, "d")]


def test_download_que_volta_html_nao_aponta_culpado_nem_grava_rem(robo, tmp_path):
    """Sessao do Smart caida: o corpo e HTML, o arquivo no Smart esta integro. Cada linha do
    HTML virava "registro com N bytes" e o vigia mandava consertar o que nao existe."""
    r, ctx = robo
    r.baixar_id.return_value = ("CB16090001832.REM", b"<html>\n<body>Sua sessao expirou</body>\n</html>\n")
    r.processar(ctx, [{"id": 58, "rotulo": "mp cast Envio de cobranca registrado", "conta": "291",
                       "titulos_grade": [{"documento": "125060-003", "sacado_cnpj": "1", "vencimento": "", "valor": ""}]}])
    registro = json.loads((tmp_path / "falhas" / "58.json").read_text(encoding="utf-8"))
    assert registro["culpados"] == [] and registro["arquivo"] is None and registro["conteudo_cnab"] is False
    assert registro["titulos"][0]["documento"] == "125060-003"
    assert not (tmp_path / "falhas" / "58.REM").exists()

