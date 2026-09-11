"""Geração Smart simulada; arquivos, interrupções e retomadas reais no disco."""

import importlib
import importlib.util
import json
import sys
import types
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest


@pytest.fixture
def origem(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]
                                   / "src/processors/web/robo_remessa"))
    with patch.dict(sys.modules):
        for nome in ("_nextcloud", "_sessao", "gerar", "login", "remessa_config",
                     "robo_remessa", "bb_geracao"):
            sys.modules.pop(nome, None)
        if importlib.util.find_spec("playwright") is None:
            # O host de testes não tem o Playwright; robo_remessa só o usa em main().
            api = types.ModuleType("playwright.sync_api")
            api.sync_playwright = Mock()
            pacote = types.ModuleType("playwright")
            pacote.sync_api = api
            sys.modules["playwright"] = pacote
            sys.modules["playwright.sync_api"] = api
        robo = importlib.import_module("robo_remessa")
        bb = importlib.import_module("bb_geracao")
        form = '''<form name="ConfirmarDadosConta">
        <input name="NumSequencial" value="36"><input name="existeEntrada" value="1">
        <input name="numBanco" value="001"><input name="numConta" value="395">
        <input name="carteira" value="17"><input name="modalidadeS" value="G">
        <input type="checkbox" name="prazo1" id="prazo" value="101" checked></form>'''
        header = list("01REMESSA".ljust(400))
        header[76:79] = "001"
        header[129:136] = "1234567"
        dados = ("\r\n".join(["".join(header), "7".ljust(400), "9".ljust(400)])
                 + "\r\n").encode()
        monkeypatch.setattr(robo.ger, "filtrar", Mock(return_value=form))
        gerar_real = robo.ger.gerar
        monkeypatch.setattr(robo.ger, "gerar", Mock(return_value={
            "ok": True, "enviado": True, "ids": [("1", 42)], "erros": []}))
        monkeypatch.setattr(robo, "baixar_id", Mock(return_value=("teste.REM", dados)))
        monkeypatch.setattr(robo, "listar_remessas", Mock())
        monkeypatch.setattr(robo.nuvem, "enviar", Mock(return_value=(True, "CNAB/arquivo.REM", "OK")))
        kwargs = {"conta": "395", "carteira": "17", "convenio": "1234567", "ambiente": "producao",
                  "pasta": str(tmp_path / "origem"), "dry_run": False}
        yield SimpleNamespace(bb=bb, robo=robo, kwargs=kwargs, ctx=object(), dados=dados,
                              pasta=tmp_path / "origem", gerar_real=gerar_real)


def rodar(o, **alteracoes):
    return o.bb.executar(o.robo, o.ctx, **{**o.kwargs, **alteracoes})


def test_intencao_e_gravada_antes_do_post_e_manifesto_so_apos_entrega(origem):
    o = origem
    resposta = o.robo.ger.gerar.return_value

    def gerar(*args, **kwargs):
        intencao, = o.pasta.rglob("intencao.json")
        assert "prazo1=101" in json.loads(intencao.read_text())["corpo"]
        assert not list(o.pasta.rglob("pronta.json"))
        return resposta

    o.robo.ger.gerar.side_effect = gerar
    resultado = rodar(o)
    assert resultado["estado"] == "pronta" and resultado["ids"] == [42]
    pronta, = o.pasta.rglob("pronta.json")
    manifesto = json.loads(pronta.read_text())
    assert manifesto["intencao"]["conta_smart"] == "395"
    assert (pronta.parent / "42.REM").read_bytes() == o.dados
    assert manifesto["arquivos"][0]["nome"] == "teste.REM"
    o.robo.ger.gerar.assert_called_once()
    o.robo.nuvem.enviar.assert_called_once_with(o.dados, "teste.REM")
    o.robo.listar_remessas.assert_not_called()


def test_simular_nao_grava_nem_gera_ou_entrega(origem):
    assert rodar(origem, dry_run=True)["estado"] == "simulado"
    assert not origem.pasta.exists()
    origem.robo.ger.gerar.assert_not_called()
    origem.robo.baixar_id.assert_not_called()


def test_fila_vazia_nao_consumiu_sequencial(origem):
    origem.robo.ger.filtrar.return_value = origem.robo.ger.filtrar.return_value.replace(
        'name="existeEntrada" value="1"', 'name="existeEntrada" value="0"')
    assert rodar(origem)["estado"] == "sem_remessa"
    assert not list(origem.pasta.rglob("intencao.json"))
    origem.robo.ger.gerar.assert_not_called()


@pytest.mark.parametrize("falha", ["timeout", "resposta_sem_ids", "persistencia_resposta"])
def test_geracao_inconclusiva_nunca_vira_busca_historica_ou_novo_post(origem, monkeypatch, falha):
    o = origem
    if falha == "timeout":
        o.robo.ger.gerar.side_effect = TimeoutError("resposta perdida")
    elif falha == "resposta_sem_ids":
        o.robo.ger.gerar.return_value = {"ok": False, "enviado": True, "ids": []}
    else:
        original = o.bb._json

        def gravar(path, dados):
            if path.name == "resultado.json":
                raise OSError("disco cheio")
            return original(path, dados)

        monkeypatch.setattr(o.bb, "_json", gravar)
    with pytest.raises((o.bb.OrigemBBInconclusiva, OSError)):
        rodar(o)
    with pytest.raises(o.bb.OrigemBBInconclusiva):
        rodar(o)
    o.robo.ger.gerar.assert_called_once()
    o.robo.listar_remessas.assert_not_called()
    o.robo.baixar_id.assert_not_called()
    assert not list(o.pasta.rglob("pronta.json"))


def test_falha_upload_retoma_bytes_salvos_sem_regerar_nem_rebaixar(origem):
    o = origem
    o.robo.nuvem.enviar.return_value = (False, "CNAB/arquivo.REM", "falha")
    with pytest.raises(o.bb.OrigemBBInconclusiva):
        rodar(o)
    assert not list(o.pasta.rglob("pronta.json"))
    o.robo.nuvem.enviar.return_value = (True, "CNAB/arquivo.REM", "OK")
    assert rodar(o)["estado"] == "pronta"
    o.robo.ger.gerar.assert_called_once()
    o.robo.baixar_id.assert_called_once()
    o.robo.ger.filtrar.assert_called_once()


def test_falha_download_retoma_somente_id_da_resposta(origem):
    o = origem
    o.robo.baixar_id.return_value = (None, None)
    with pytest.raises(o.bb.OrigemBBInconclusiva):
        rodar(o)
    o.robo.baixar_id.return_value = ("teste.REM", o.dados)
    assert rodar(o)["ids"] == [42]
    o.robo.ger.gerar.assert_called_once()
    assert [c.args[1] for c in o.robo.baixar_id.call_args_list] == [42, 42]


@pytest.mark.parametrize("campo,velho,novo", [
    ("numBanco", "001", "274"), ("numConta", "395", "396"),
    ("carteira", "17", "18"), ("modalidadeS", "G", "X"),
])
def test_filtro_fora_de_escopo_nao_gera(origem, campo, velho, novo):
    o = origem
    o.robo.ger.filtrar.return_value = o.robo.ger.filtrar.return_value.replace(
        f'name="{campo}" value="{velho}"', f'name="{campo}" value="{novo}"')
    with pytest.raises(o.bb.OrigemBBInconclusiva):
        rodar(o)
    o.robo.ger.gerar.assert_not_called()


@pytest.mark.parametrize("mudanca", ["banco", "convenio", "html", "nome"])
def test_arquivo_errado_nao_e_entregue(origem, mudanca):
    o = origem
    dados, nome = o.dados, "teste.REM"
    if mudanca == "banco":
        dados = dados[:76] + b"274" + dados[79:]
    elif mudanca == "convenio":
        dados = dados.replace(b"1234567", b"7654321")
    elif mudanca == "html":
        dados = b"<html>login</html>"
    else:
        nome = "../teste.REM"
    o.robo.baixar_id.return_value = (nome, dados)
    with pytest.raises(o.bb.OrigemBBInconclusiva):
        rodar(o)
    o.robo.nuvem.enviar.assert_not_called()
    assert not list(o.pasta.rglob("pronta.json"))


def test_erros_parciais_preservam_download_sem_liberar_envio(origem):
    o = origem
    o.robo.ger.gerar.return_value["erros"] = ["erro outro arquivo"]
    with pytest.raises(o.bb.OrigemBBInconclusiva):
        rodar(o)
    assert len(list(o.pasta.rglob("42.REM"))) == 1
    assert not list(o.pasta.rglob("pronta.json"))


def test_arquivo_modificado_nao_e_reentregue(origem):
    o = origem
    o.robo.nuvem.enviar.return_value = (False, "", "erro")
    with pytest.raises(o.bb.OrigemBBInconclusiva):
        rodar(o)
    arquivo, = o.pasta.rglob("42.REM")
    arquivo.write_bytes(o.dados.replace(b"001", b"274"))
    o.robo.nuvem.enviar.reset_mock()
    with pytest.raises(o.bb.OrigemBBInconclusiva, match="mudou"):
        rodar(o)
    o.robo.nuvem.enviar.assert_not_called()


def test_pendencia_em_outra_carteira_nao_e_ultrapassada(origem):
    o = origem
    o.robo.ger.gerar.side_effect = TimeoutError()
    with pytest.raises(TimeoutError):
        rodar(o)
    with pytest.raises(o.bb.OrigemBBInconclusiva, match="outro escopo"):
        rodar(o, carteira="18")
    o.robo.ger.gerar.assert_called_once()


def test_evidencia_imutavel(origem, tmp_path):
    path = tmp_path / "evidencia.json"
    origem.bb._publicar(path, b"original")
    origem.bb._publicar(path, b"original")
    with pytest.raises(origem.bb.OrigemBBInconclusiva):
        origem.bb._publicar(path, b"novo")
    assert path.read_bytes() == b"original"


def test_cli_bb_simula_mesmo_com_dry_run_global_desligado(origem, monkeypatch):
    o = origem
    monkeypatch.setattr(o.robo.cfg, "DRY_RUN", False)
    args = o.robo.montar_parser().parse_args([
        "--gerar", "--conta", "395", "--carteira", "17", "--bb-api-convenio", "1234567",
        "--bb-api-ambiente", "producao", "--bb-api-origem", str(o.pasta)])
    assert o.robo.executar(o.ctx, args) == o.robo.SAIU_OK
    assert not o.pasta.exists()
    o.robo.ger.gerar.assert_not_called()


def test_cli_bb_nao_aceita_reenvio_historico(origem):
    o = origem
    args = o.robo.montar_parser().parse_args([
        "--gerar", "--conta", "395", "--carteira", "17", "--bb-api-convenio", "1234567",
        "--bb-api-ambiente", "producao", "--ids", "42", "--pra-valer"])
    assert o.robo.executar(o.ctx, args) == o.robo.SAIU_RODADA_INCOMPLETA
    o.robo.ger.gerar.assert_not_called()


def controle_do_participante(tid, layout="antigo"):
    """Os dois layouts que o Smart já escreveu nas posições 38:63 (medidos em produção)."""
    if layout == "antigo":
        return f"{'395'.zfill(10)}{tid:015d}"
    return f"X03912{'395'.zfill(7)}{tid:012d}"


def preparar_resposta_direta(o, comandos=("01", "01"), layout="antigo", controles=None):
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    header = list(o.dados.decode().splitlines()[0])
    header[94:100] = agora.strftime("%d%m%y")
    detalhes = []
    for indice, (tid, comando) in enumerate(zip((101, 102), comandos, strict=True)):
        linha = list("7".ljust(400))
        linha[38:63] = (controles[indice] if controles else controle_do_participante(tid, layout))
        linha[108:110] = comando
        detalhes.append("".join(linha))
    dados = ("\r\n".join(["".join(header), detalhes[0], "5".ljust(400), detalhes[1], "9".ljust(400)])
             + "\r\n").encode("latin-1")
    form = o.robo.ger.filtrar.return_value.replace("prazo1", "titulo1").replace(
        "</form>", '<input type="checkbox" name="titulo2" id="prazo" value="102" checked></form>')
    instrucoes = ""
    for indice, comando in enumerate(comandos, 1):
        if comando != "01":
            form = form.replace(
                f'<input type="checkbox" name="titulo{indice}" id="prazo" value="{100 + indice}" checked>', "")
            instrucoes += f"{100 + indice}@"
    form = form.replace("</form>", f'<input name="instrucoes" value="{instrucoes}"></form>')
    o.robo.ger.filtrar.return_value = form
    item = {"id": 42, "cc": "395", "arquivo": "teste.REM", "data": agora.strftime("%d/%m/%Y %H:%M")}
    o.robo.listar_remessas.return_value = [item]
    o.robo.baixar_id.return_value = ("teste.REM", dados)
    response = SimpleNamespace(status=200, url="https://smart.invalid/financeiro/mandarremessa.php?file=42",
                               headers={"content-type": "application/octet-stream", "set-cookie": "NAO_SALVAR"},
                               body=lambda: dados)
    o.ctx = SimpleNamespace(request=SimpleNamespace(post=Mock(return_value=response)))
    o.robo.ger.gerar.side_effect = o.gerar_real
    return dados


def test_cnab_direto_preserva_resposta_e_retoma_upload_sem_novo_post(origem):
    o = origem
    dados = preparar_resposta_direta(o)
    o.robo.nuvem.enviar.return_value = (False, "", "indisponível")
    with pytest.raises(o.bb.OrigemBBInconclusiva):
        rodar(o)
    resposta, = o.pasta.rglob("resultado.json")
    original = resposta.read_bytes()
    assert len(json.loads(original)["resposta_http"]["body_base64"]) > 1500
    assert b"NAO_SALVAR" not in original
    o.robo.nuvem.enviar.return_value = (True, "CNAB/teste.REM", "OK")
    assert rodar(o)["ids"] == [42]
    assert resposta.read_bytes() == original
    assert (resposta.parent / "42.REM").read_bytes() == dados
    o.ctx.request.post.assert_called_once()
    o.robo.baixar_id.assert_called_once()


@pytest.mark.parametrize("comandos", [("01", "02"), ("01", "06"), ("01", "04"), ("02", "06")])
def test_download_direto_confere_entradas_e_instrucoes_e_retoma_sem_regerar(origem, comandos):
    o = origem
    dados = preparar_resposta_direta(o, comandos)
    o.robo.nuvem.enviar.return_value = (False, "", "indisponível")
    with pytest.raises(o.bb.OrigemBBInconclusiva):
        rodar(o)
    resposta, = o.pasta.rglob("resultado.json")
    original = resposta.read_bytes()
    o.robo.nuvem.enviar.return_value = (True, "CNAB/teste.REM", "OK")
    assert rodar(o)["ids"] == [42]
    assert (resposta.parent / "42.REM").read_bytes() == dados
    assert resposta.read_bytes() == original
    o.ctx.request.post.assert_called_once()


@pytest.mark.parametrize("layout", ["antigo", "novo"])
def test_download_direto_le_o_id_nos_dois_layouts_do_controle(origem, layout):
    o = origem
    dados = preparar_resposta_direta(o, ("01", "06"), layout=layout)
    assert rodar(o)["ids"] == [42]
    arquivo, = o.pasta.rglob("42.REM")
    assert arquivo.read_bytes() == dados
    o.ctx.request.post.assert_called_once()


@pytest.mark.parametrize("controle", [
    "Y03912" + "395".zfill(7) + f"{102:012d}",    # prefixo que o Smart nunca escreveu
    "X03912" + "396".zfill(7) + f"{102:012d}",    # outra conta no layout novo
    "396".zfill(10) + f"{102:015d}",              # outra conta no layout antigo
    "395".zfill(10) + f"{102:014d}" + "A",        # ID com letra
])
def test_controle_fora_dos_dois_layouts_e_inconclusivo(origem, controle):
    o = origem
    preparar_resposta_direta(o, ("01", "01"), controles=[controle_do_participante(101), controle])
    with pytest.raises(o.bb.OrigemBBInconclusiva):
        rodar(o)
    o.robo.nuvem.enviar.assert_not_called()
    assert not list(o.pasta.rglob("pronta.json"))


@pytest.mark.parametrize("controle,esperado", [
    ("0000000395000000000907046", "907046"),    # 26282.REM, 10/09/2026
    ("X039120000395000000909174", "909174"),    # remessa 40, 11/09/2026
])
def test_id_do_controle_nos_dois_layouts_reais(origem, controle, esperado):
    assert origem.bb._id_do_controle(controle, "395") == esperado


@pytest.mark.parametrize("controle", [
    "X039120000396000000909174", "0000000396000000000907046",
    "Z039120000395000000909174", "000000039500000000A907046", "0000000395000000000907046 ",
])
def test_id_do_controle_recusa_layout_desconhecido(origem, controle):
    with pytest.raises(origem.bb.OrigemBBInconclusiva):
        origem.bb._id_do_controle(controle, "395")


@pytest.mark.parametrize("lista", ["", "103@", "102@102@", "101@"])
def test_download_direto_recusa_instrucao_ausente_extra_ou_de_outro_titulo(origem, lista):
    o = origem
    preparar_resposta_direta(o, ("01", "06"))
    o.robo.ger.filtrar.return_value = o.robo.ger.filtrar.return_value.replace(
        'name="instrucoes" value="102@"', f'name="instrucoes" value="{lista}"')
    with pytest.raises(o.bb.OrigemBBInconclusiva):
        rodar(o)
    o.robo.nuvem.enviar.assert_not_called()
    assert not list(o.pasta.rglob("pronta.json"))


@pytest.mark.parametrize("falha", ["bytes", "duplicado", "conta", "data", "titulos"])
def test_cnab_direto_nao_libera_download_sem_prova(origem, falha):
    o = origem
    dados = preparar_resposta_direta(o)
    if falha == "bytes":
        o.robo.baixar_id.return_value = ("teste.REM", dados.replace(b"000000000000102", b"000000000000103"))
    elif falha == "duplicado":
        o.robo.listar_remessas.return_value.append({**o.robo.listar_remessas.return_value[0], "id": 43})
    elif falha in ("conta", "data"):
        o.robo.listar_remessas.return_value[0]["cc" if falha == "conta" else "data"] = (
            "396" if falha == "conta" else "01/01/2020 00:00")
    else:
        o.robo.ger.filtrar.return_value = o.robo.ger.filtrar.return_value.replace('value="102"', 'value="103"')
    with pytest.raises(o.bb.OrigemBBInconclusiva):
        rodar(o)
    o.robo.nuvem.enviar.assert_not_called()
    assert not list(o.pasta.rglob("pronta.json"))


def test_prefixo_legado_so_retoma_id_explicito_sem_alterar_resultado(origem):
    o = origem
    dados = preparar_resposta_direta(o)
    real = o.gerar_real

    def legado(*args, **kwargs):
        res = real(*args, **kwargs)
        res.pop("resposta_http")
        return res

    o.robo.ger.gerar.side_effect = legado
    with pytest.raises(o.bb.OrigemBBInconclusiva):
        rodar(o)
    o.robo.listar_remessas.assert_not_called()
    resposta, = o.pasta.rglob("resultado.json")
    original = resposta.read_bytes()
    assert o.bb.recuperar_download_direto(o.robo, o.ctx, pasta=resposta.parent, smart_id=42)["ids"] == [42]
    assert resposta.read_bytes() == original
    assert (resposta.parent / "42.REM").read_bytes() == dados
    assert json.loads((resposta.parent / "download_direto.json").read_text())["metodo"] == "legado_conferido"
    o.ctx.request.post.assert_called_once()
