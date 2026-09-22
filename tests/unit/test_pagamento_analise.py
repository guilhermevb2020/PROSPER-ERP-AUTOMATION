#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes do `analise.py` do robo de pagamento — a leitura de tela da Fase 0.

POR QUE ESTES TESTES EXISTEM
----------------------------
O robo de pagamento ainda nao existe: o que existe e a descoberta da tela, e o
`analise.py` e quem decide, lendo o HTML, **que robo sera escrito**. Se ele
classificar errado, o robo inteiro nasce no molde errado — e os dois moldes
(`robo_remessa`, que posta formulario, e `retorno_cobranca`, que conversa por
`Acao`) nao se parecem em nada.

O QUE ELES TRAVAM
-----------------
1. Campo que so existe DENTRO do `<script>` NAO entra na lista de campos. E a
   armadilha medida no `robo_remessa/gerar.py`: a tela de cobranca tem um
   `<input name="Mens0${...}">` num template literal, que nao e elemento nenhum
   no DOM real e virava campo fantasma no POST.
2. O `Acao` do JS, ao contrario, TEM de ser achado — e o unico sinal de que a
   tela e do molde ajax, e ele so existe dentro do `<script>`. Ou seja: os dois
   varredores olham escopos diferentes, DE PROPOSITO, e o teste prende os dois.
3. Tela sem form e sem `Acao` vira `indefinido` e aponta os frames, em vez de
   ser chamada de "tela vazia" — que e como um erro de leitura se disfarca aqui.

RESTRICOES DE AMBIENTE
----------------------
- Rodam no HOST; o container `erp-automation` nao tem pytest.
- So `analise.py` pode ser importado: `descobrir.py` puxa `playwright` e
  `src.common.clients`, que nao resolvem no host. E exatamente por isso que a
  leitura de tela foi escrita como modulo puro, so com stdlib — mesma decisao
  (e mesma razao) do `retorno_cobranca/portao.py`.
"""
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src" / "processors" / "web" / "remessa_pagamento"))

from analise import (  # noqa: E402  (o sys.path tem de vir antes)
    MOLDE_AJAX,
    MOLDE_FORM,
    MOLDE_INDEFINIDO,
    analisar,
    atributo,
    classificar,
    coletar_links,
    frames,
    reparar_padding_info12_cnab240,
    sem_js,
)

BASE = "https://wvw.smartsecurities.com.br/smart/financeiro/tela.php"
SMART = "https://wvw.smartsecurities.com.br/smart"

# Tela do molde FORM. Reproduz as tres coisas que a de remessa de cobranca tem e
# que ja custaram tempo: dois forms (um deles o `aux`, que nao deve ir no POST),
# um checkbox `id=prazo` e o `<input>` fantasma dentro do <script>.
TELA_FORM = """
<html><body>
<a href="/smart/pagamento/gerarremessapagto.php">Gerar Remessa</a>
<a href="pagamento/consultapagto.php"><img src=x> Consulta de Pagamento</a>
<a href="../financeiro/downloadremessa.php">Download Remessa</a>
<script>
  function ir(){ window.open('/smart/pagamento/listaremessapagto.php'); }
  var molde = '<input name="Mens0${quantidadeMensagens.value}" value="fantasma">';
</script>
<form name="Form" method="POST" action="confirmarpagto.php">
  <input type="hidden" name="form_submit" value="1">
  <input type="text" name="NumSequencial" value="42">
  <input type="checkbox" name="pagto[]" id="prazo" value="991" checked>
  <select name="contaCorrente">
    <option value="0">-- selecione --</option>
    <option value="291" selected>mp cast</option>
    <option value="300">mp atacadao</option>
  </select>
  <textarea name="Mens0"></textarea>
  <input type="submit" name="bGerar" value="Gerar">
</form>
<form name="aux"><input name="contaCorrente2" value="nao usar"></form>
</body></html>
"""

# Tela do molde AJAX: nenhum form, tudo por `Acao` — como o Processar Retorno.
TELA_AJAX = """
<html><body><script>
  $.post('/smart/pagamento/ajax/ajaxpagtobmp.php', {Acao: 'VALIDAR_CONTA'});
  var x = {Acao:"GERAR_REMESSA_PAGAMENTO"};
  enviar({Acao: 'CONSULTAR_LOTE'});
</script></body></html>
"""

# Tela que so contem outra tela. E o caso que nao pode ser lido como "vazia".
TELA_FRAME = """
<html><frameset>
  <frame name="menu" src="/smart/php/menu.php">
  <iframe src="pagamento/gerarremessapagto.php"></iframe>
</frameset></html>
"""


# --------------------------------------------------------------------------- #
# 1. o campo fantasma do <script> nao pode entrar
# --------------------------------------------------------------------------- #
def test_campo_dentro_de_script_nao_vira_campo():
    """A armadilha do gerar.py: `<input>` em template literal nao e elemento."""
    info = analisar(TELA_FORM, BASE)
    todos = [c["nome"] for f in info["forms"] for c in f["campos"]]
    assert not any("${" in n for n in todos), todos
    assert "Mens0" in todos          # o textarea REAL continua la


def test_sem_js_remove_script_style_e_comentario():
    sujo = "<b>a</b><script>x</script><style>y</style><!-- z --><i>b</i>"
    limpo = sem_js(sujo)
    assert "<b>a</b>" in limpo and "<i>b</i>" in limpo
    for fora in ("x", "y", "z"):
        assert f">{fora}<" not in limpo


# --------------------------------------------------------------------------- #
# 2. leitura do form
# --------------------------------------------------------------------------- #
def test_forms_na_ordem_com_action_absoluta():
    info = analisar(TELA_FORM, BASE)
    assert [f["nome"] for f in info["forms"]] == ["Form", "aux"]
    principal = info["forms"][0]
    assert principal["method"] == "POST"
    assert principal["action"] == f"{SMART}/financeiro/confirmarpagto.php"


def test_select_traz_as_opcoes_que_viram_a_conta():
    """O valor de CONTA_PAG sai daqui — sem as opcoes, nao ha o que configurar."""
    info = analisar(TELA_FORM, BASE)
    sel = [c for c in info["forms"][0]["campos"] if c["elem"] == "select"][0]
    assert sel["nome"] == "contaCorrente"
    assert ("291", "mp cast") in sel["opcoes"]
    assert ("0", "-- selecione --") in sel["opcoes"]


def test_checkbox_marcado_e_reportado():
    info = analisar(TELA_FORM, BASE)
    caixa = [c for c in info["forms"][0]["campos"] if c["id"] == "prazo"][0]
    assert caixa["marcado"] is True and caixa["valor"] == "991"


@pytest.mark.parametrize("tag,nome,esperado", [
    ('<input name="a" value="1">', "name", "a"),
    ("<input name='b'>", "name", "b"),
    ('<a href="x.php?y=1&amp;z=2">', "href", "x.php?y=1&z=2"),   # entidade
    ('<input value="1">', "name", None),
    ("", "name", None),
])
def test_atributo(tag, nome, esperado):
    assert atributo(tag, nome) == esperado


# --------------------------------------------------------------------------- #
# 3. links: as tres formas, e a resolucao de caminho relativo
# --------------------------------------------------------------------------- #
def test_coleta_as_tres_formas_de_link():
    links = coletar_links(TELA_FORM, BASE)
    # <a href> absoluto, com rotulo
    assert links[f"{SMART}/pagamento/gerarremessapagto.php"] == "Gerar Remessa"
    # <a href> relativo, rotulo com tag dentro
    assert links[f"{SMART}/financeiro/pagamento/consultapagto.php"] \
        == "Consulta de Pagamento"
    # `..` resolvido
    assert f"{SMART}/financeiro/downloadremessa.php" in links
    # window.open dentro do <script> — so o segundo varredor pega
    assert f"{SMART}/pagamento/listaremessapagto.php" in links


def test_filtro_por_termo_acha_a_arvore_de_pagamento():
    links = coletar_links(TELA_FORM, BASE)
    casam = [u for u, r in links.items()
             if "pagamento" in u.lower() or "pagamento" in (r or "").lower()]
    assert len(casam) == 3
    assert all("pagto" in u or "pagamento" in u for u in casam)


# --------------------------------------------------------------------------- #
# 4. a classificacao — que robo sera escrito
# --------------------------------------------------------------------------- #
def test_tela_com_form_vira_molde_form():
    molde, motivo = classificar(analisar(TELA_FORM, BASE))
    assert molde == MOLDE_FORM
    assert "robo_remessa" in motivo


def test_tela_com_acao_vira_molde_ajax():
    info = analisar(TELA_AJAX, BASE)
    assert info["ajax"] == [f"{SMART}/pagamento/ajax/ajaxpagtobmp.php"]
    assert info["acoes"] == ["CONSULTAR_LOTE", "GERAR_REMESSA_PAGAMENTO",
                             "VALIDAR_CONTA"]
    molde, motivo = classificar(info)
    assert molde == MOLDE_AJAX and "retorno_cobranca" in motivo


def test_acao_ganha_de_form():
    """A tela de Processar Retorno TEM forms e mesmo assim e ajax.

    Se o form ganhasse, o robo nasceria postando formulario numa tela que so
    responde a `Acao` — e cada POST voltaria vazio, que aqui e indistinguivel
    de "nao ha pagamento a gerar".
    """
    misto = TELA_FORM + TELA_AJAX
    molde, _ = classificar(analisar(misto, BASE))
    assert molde == MOLDE_AJAX


def test_tela_de_frame_nao_e_confundida_com_vazia():
    info = analisar(TELA_FRAME, BASE)
    molde, motivo = classificar(info)
    assert molde == MOLDE_INDEFINIDO and "frame" in motivo
    assert frames(TELA_FRAME, BASE) == [
        f"{SMART}/financeiro/pagamento/gerarremessapagto.php",
        f"{SMART}/php/menu.php",
    ]


def test_form_sem_campo_nenhum_nao_conta_como_molde_form():
    """Form de busca vazio nao e a tela de trabalho."""
    molde, _ = classificar(analisar("<form name='x'></form>", BASE))
    assert molde == MOLDE_INDEFINIDO


# --------------------------------------------------------------------------- #
# 5. nada disso pode explodir numa pagina degenerada
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("lixo", [
    "", "   ", "<html></html>", "<form><select></select></form>",
    "<a href=>x</a>", "<input name=", "<script>", "nao e html",
])
def test_pagina_degenerada_nao_levanta(lixo):
    info = analisar(lixo, BASE)
    assert isinstance(info["forms"], list)
    assert classificar(info)[0] in (MOLDE_FORM, MOLDE_AJAX, MOLDE_INDEFINIDO)
    assert isinstance(coletar_links(lixo, BASE), dict)
    assert frames(lixo, BASE) == []


def test_html_none_nao_levanta():
    """`buscar()` devolve None quando a sessao caiu — nao pode virar traceback."""
    info = analisar(None, BASE)
    assert info["forms"] == [] and info["links"] == {}
    assert classificar(info)[0] == MOLDE_INDEFINIDO


# --------------------------------------------------------------------------- #
# 6. montar_filtro — o unico POST da descoberta, e as travas dele
# --------------------------------------------------------------------------- #
# A tela real, medida em 21/08/2026: financeiro/pagtobmp/pagtobmppesquisa.php.
# A grade so aparece com o filtro submetido — `pagtobmpgrid.php` no GET devolve
# este mesmo formulario, vazio.
TELA_PAGTOBMP = """
<form name="carteira" method="POST" action="pagtobmpgrid.php">
  <input type="hidden" name="pesquisar" value="1">
  <input type="date" name="data1"><input type="date" name="data2">
  <input type="text" name="operacao1">
  <select name="IdContaBancaria">
    <option value="">Selecione</option>
    <option value="404">mp prospere | 274 | 0001 | 0986952</option>
  </select>
  <select name="pagtobmp">
    <option value="P">Pendente</option>
    <option value="G">Gerado</option>
  </select>
  <input type="submit" name="bGerarRemessa" value="Gerar Remessa">
  <input type="button" name="bExcluir" value="Excluir">
</form>
"""


def _form_pagtobmp():
    return analisar(TELA_PAGTOBMP, BASE)["forms"][0]


def test_select_expoe_o_valor_que_o_navegador_mandaria():
    """Sem `selected`, vale a PRIMEIRA opcao — que e o que o browser envia."""
    from analise import montar_filtro  # noqa: F401  (garante o import do modulo)
    campos = {c["nome"]: c for c in _form_pagtobmp()["campos"]}
    assert campos["IdContaBancaria"]["valor"] == ""      # 1a opcao = "Selecione"
    assert campos["pagtobmp"]["valor"] == "P"           # 1a opcao = Pendente


def test_filtro_nao_leva_botao_nenhum():
    """A trava que mais importa: numa tela de PAGAMENTO, botao gera remessa."""
    from analise import montar_filtro
    corpo, campos = montar_filtro(_form_pagtobmp())
    assert "bGerarRemessa" not in campos and "bGerarRemessa" not in corpo
    assert "bExcluir" not in campos and "bExcluir" not in corpo
    assert campos["pesquisar"] == "1"


def test_filtro_aplica_os_overrides():
    from analise import montar_filtro
    _corpo, campos = montar_filtro(
        _form_pagtobmp(), {"IdContaBancaria": "404", "pagtobmp": "P"})
    assert campos["IdContaBancaria"] == "404" and campos["pagtobmp"] == "P"


def test_filtro_recusa_form_que_nao_e_de_busca():
    """Se a tela mudar e `pesquisar` sumir, o form virou outra coisa: nao posta."""
    from analise import montar_filtro
    outro = analisar(
        '<form name="x" action="y.php"><input name="confirmar" value="1"></form>',
        BASE)["forms"][0]
    with pytest.raises(ValueError, match="nao parece ser de busca"):
        montar_filtro(outro)


def test_filtro_ignora_placeholder_de_template():
    from analise import montar_filtro
    sujo = TELA_PAGTOBMP.replace(
        '<input type="text" name="operacao1">',
        '<input type="text" name="operacao1"><input name="Mens${i}" value="x">')
    corpo, campos = montar_filtro(analisar(sujo, BASE)["forms"][0])
    assert not any("${" in k for k in campos) and "%24%7B" not in corpo


# --------------------------------------------------------------------------- #
# 7. inspecionar_arquivo — o que separa arquivo de pagina de erro
# --------------------------------------------------------------------------- #
def _cnab(n_linhas, largura):
    return ("\n".join("X" * largura for _ in range(n_linhas))).encode("latin-1")


@pytest.mark.parametrize("dados,esperado", [
    (_cnab(3, 240), "CNAB-240"),
    (_cnab(3, 400), "CNAB-400"),
])
def test_layout_e_deduzido_e_nao_suposto(dados, esperado):
    """Cobranca e 400; pagamento costuma ser 240 — 'costuma' nao serve."""
    from analise import inspecionar_arquivo
    r = inspecionar_arquivo(dados)
    assert r["layout"] == esperado and r["ok"] is True and r["linhas"] == 3


def test_html_nunca_passa_por_arquivo():
    """A licao do robo_remessa: sessao caida devolve HTML com status 200.

    Sem esta trava, a pagina de erro e gravada com nome de `.REM`, entra na
    pasta que o Financeiro olha e so quebra no banco.
    """
    from analise import inspecionar_arquivo
    r = inspecionar_arquivo(b"<html><body>Sessao expirada</body></html>")
    assert r["ok"] is False and r["e_html"] is True
    assert "HTML" in r["motivo"]


def test_json_tambem_e_recusado():
    from analise import inspecionar_arquivo
    assert inspecionar_arquivo(b'{"erro": "sem permissao"}')["ok"] is False


def test_resposta_vazia_e_recusada():
    from analise import inspecionar_arquivo
    r = inspecionar_arquivo(b"")
    assert r["ok"] is False and "vazia" in r["motivo"]


def test_linhas_de_tamanhos_diferentes_nao_passam():
    """Download truncado no meio: as linhas deixam de ter largura unica."""
    from analise import inspecionar_arquivo
    truncado = _cnab(2, 240) + b"\nXXX"
    r = inspecionar_arquivo(truncado)
    assert r["ok"] is False and "tamanhos diferentes" in r["motivo"]


def test_linha_em_branco_no_fim_nao_atrapalha():
    from analise import inspecionar_arquivo
    assert inspecionar_arquivo(_cnab(2, 240) + b"\n\n")["ok"] is True


def _segmento_b_curto(g100, chave, sufixo=b"0" * 14):
    prefixo = bytearray(b" " * 127)
    prefixo[7:8] = b"3"
    prefixo[13:14] = b"B"
    prefixo[14:17] = g100.encode("ascii").ljust(3)
    return bytes(prefixo) + chave + sufixo


@pytest.mark.parametrize("g100,chave", [
    ("01", b"11971805955"),
    ("02", b" contabil@example.com"),
    ("03", b"12345678901"),
    ("04", b"82d8e173-09e1-4ec8-92ff-725290316d66"),
])
def test_repara_so_padding_da_informacao_12(g100, chave):
    curta = _segmento_b_curto(g100, chave)
    dados = b"X" * 240 + b"\r\n" + curta + b"\r\n"

    reparado, quantidade = reparar_padding_info12_cnab240(dados)

    linhas = reparado.split(b"\r\n")
    assert quantidade == 1
    assert len(linhas[1]) == 240
    assert linhas[1][127:226].rstrip(b" ") == chave.strip(b" ")
    assert linhas[1][-14:] == b"0" * 14
    assert reparado.endswith(b"\r\n"), "a quebra de linha original deve ser preservada"


@pytest.mark.parametrize("mutacao", ["segmento_a", "g100_05", "chave_invalida"])
def test_padding_curto_fora_do_padrao_nao_e_reparado(mutacao):
    linha = bytearray(_segmento_b_curto("02", b"contabil@example.com"))
    if mutacao == "segmento_a":
        linha[13:14] = b"A"
    elif mutacao == "g100_05":
        linha[14:17] = b"05 "
    else:
        linha[127:-14] = b"sem-arroba"
    original = bytes(linha) + b"\n"

    reparado, quantidade = reparar_padding_info12_cnab240(original)

    assert quantidade == 0
    assert reparado == original


def test_linha_cnab240_completa_nao_e_alterada_pelo_reparo():
    completa = (
        _segmento_b_curto("02", b"contabil@example.com")[:127]
        + b"contabil@example.com".ljust(99, b" ")
        + b"0" * 14
        + b"\r\n"
    )
    reparado, quantidade = reparar_padding_info12_cnab240(completa)
    assert quantidade == 0
    assert reparado == completa


# --------------------------------------------------------------------------- #
# 8. a grade e o POST de geracao — copia fiel do GerarMultipag
# --------------------------------------------------------------------------- #
# Markup espelhado do HTML REAL capturado em 21/08/2026 (data/sandbox/.../debug).
_GRADE = """
<form name="multipagForm" method="POST" action="pagtobmpgrid.php">
  <input type="hidden" name="processar" id="processar" value="0">
  <input type="hidden" name="IdContaBancaria" value="404">
  <input type="hidden" name="carteira" value="">
  <input type="hidden" name="NumBanco" value="">
  <input type="hidden" name="checkeds" value="">
  <input type="hidden" name="checkedsPIX" value="">
  <input type="hidden" name="todosCheckeds" value="">
  <input type="hidden" name="temPIX" value="">
  <input type="hidden" name="acao" id="acao" value="0">
  <input type="checkbox" name="selecionarTodos" id="selecionarTodos">
  <input type="checkbox" name="ckTitulo" value="143" data-tipopix="0">
  <input type="checkbox" name="ckTitulo" value="144" data-tipopix="1">
  <td><a id="Link_0" href="../mandarsispag.php?file=22">CP2108000001.REM</a></td>
</form>
"""
_BOTAO_GERAR = ('<button type="button" onclick="GerarMultipag(this, 1)">'
                '<span>Gerar Pagamento BMP Money Plus</span></button>')
_BOTAO_CANCELAR = ('<button type="button" onclick="GerarMultipag(this, 3)">'
                   '<span>Cancelar Pagamento BMP Money Plus</span></button>')


def test_grade_le_titulos_botoes_e_arquivos():
    from analise import ler_grade
    g = ler_grade(_GRADE + _BOTAO_GERAR, BASE)
    assert g["titulos"] == [{"id": "143", "pix": False}, {"id": "144", "pix": True}]
    assert g["botoes"] == [{"acao": 1, "rotulo": "Gerar Pagamento BMP Money Plus"}]
    assert g["arquivos"][0] == {"id": "22", "nome": "CP2108000001.REM"}
    assert g["campos"]["IdContaBancaria"] == "404"
    assert "selecionarTodos" not in g["campos"]     # checkbox nao e campo fixo


def test_post_de_geracao_e_copia_fiel_do_js():
    """As virgulas no fim nao sao descuido: e o que o `+=` do JS produz."""
    from analise import montar_geracao, ler_grade
    _corpo, campos = montar_geracao(ler_grade(_GRADE + _BOTAO_GERAR, BASE), acao=1)
    assert campos["checkeds"] == "143,"          # nao-PIX
    assert campos["checkedsPIX"] == "144,"       # PIX
    assert campos["todosCheckeds"] == "143,144,"  # ordem do DOM
    assert campos["temPIX"] == "1"
    assert campos["acao"] == "1" and campos["processar"] == "1"


def test_separacao_pix_decide_os_lotes_do_cnab():
    """Medido no CP2108000001.REM: lote 0001 forma 41 (TED), 0002 forma 45 (PIX).

    Tudo em `checkeds` sairia como TED — errado e em silencio.
    """
    from analise import montar_geracao, ler_grade
    so_ted = _GRADE.replace('data-tipopix="1"', 'data-tipopix="0"')
    _c, campos = montar_geracao(ler_grade(so_ted + _BOTAO_GERAR, BASE))
    assert campos["checkeds"] == "143,144," and campos["checkedsPIX"] == ""
    assert campos["temPIX"] == "0"


def test_tipopix_ausente_cai_no_ramo_nao_pix():
    """No JS, `dataset.tipopix && ... == 1`: ausente e falsy -> checkeds."""
    from analise import montar_geracao, ler_grade
    sem = _GRADE.replace(' data-tipopix="1"', '').replace(' data-tipopix="0"', '')
    _c, campos = montar_geracao(ler_grade(sem + _BOTAO_GERAR, BASE))
    assert campos["checkedsPIX"] == "" and campos["checkeds"] == "143,144,"


def test_gerar_sobre_grade_de_GERADO_e_recusado():
    """⛔ A trava que mais importa: la o unico botao e CANCELAR.

    Mesmo form, mesmo endpoint, mesmos titulos — so muda o digito de `acao`.
    """
    from analise import montar_geracao, ler_grade
    with pytest.raises(ValueError, match="nao oferece a acao 1"):
        montar_geracao(ler_grade(_GRADE + _BOTAO_CANCELAR, BASE), acao=1)


def test_grade_sem_titulo_e_recusada():
    from analise import montar_geracao, ler_grade
    vazia = re.sub(r'<input type="checkbox" name="ckTitulo"[^>]*>', "", _GRADE)
    with pytest.raises(ValueError, match="nenhum titulo"):
        montar_geracao(ler_grade(vazia + _BOTAO_GERAR, BASE))


def test_botao_nunca_entra_no_post_de_geracao():
    from analise import montar_geracao, ler_grade
    com_botao = _GRADE.replace(
        '<input type="checkbox" name="selecionarTodos" id="selecionarTodos">',
        '<input type="submit" name="bEnviar" value="x">')
    _c, campos = montar_geracao(ler_grade(com_botao + _BOTAO_GERAR, BASE))
    assert "bEnviar" not in campos


# --------------------------------------------------------------------------- #
# 9. o nome do arquivo — ele carrega o SEQUENCIAL da remessa
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cabecalho,esperado", [
    # as duas formas medidas no Smart, em 21/08/2026
    ('attachment; filename="CP2108000003.REM"', "CP2108000003.REM"),
    ("attachment; filename=CP2108000001.REM", "CP2108000001.REM"),
    ("attachment; filename*=UTF-8''CP2108000003.REM", "CP2108000003.REM"),
])
def test_nome_sai_do_content_disposition(cabecalho, esperado):
    """Salvar como `gerado_<timestamp>` jogaria fora a identidade do arquivo.

    Duas geracoes seguidas sairam `CP2108000001` e `CP2108000003`: e por esse
    numero que se conversa com o banco e se acha a remessa depois.
    """
    from analise import nome_do_arquivo
    assert nome_do_arquivo(cabecalho) == esperado


def test_sem_header_cai_no_padrao():
    from analise import nome_do_arquivo
    assert nome_do_arquivo("") == "remessa.REM"
    assert nome_do_arquivo(None, padrao="x.REM") == "x.REM"


@pytest.mark.parametrize("malicioso", [
    'attachment; filename="../../etc/passwd"',
    'attachment; filename="..\\\\..\\\\windows\\\\system32\\\\x"',
    'attachment; filename="/tmp/fora.REM"',
])
def test_nome_nunca_escapa_da_pasta(malicioso):
    """O header vem do servidor: caminho dentro dele escreveria fora da saida."""
    from analise import nome_do_arquivo
    nome = nome_do_arquivo(malicioso)
    assert "/" not in nome and "\\" not in nome and ".." != nome
