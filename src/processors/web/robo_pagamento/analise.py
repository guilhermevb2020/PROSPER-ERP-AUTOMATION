# -*- coding: utf-8 -*-
"""
analise.py - le uma tela do Smart e diz o que o robo precisa saber sobre ela.

Modulo PURO de proposito: so stdlib, sem playwright e sem `src.common`. E o que
permite testa-lo no HOST, onde o pytest existe — o container `erp-automation`
nao o tem. Mesmo desenho (e mesma razao) do `robo_retorno/portao.py`.

Quem faz rede e o `descobrir.py`; aqui so entra HTML que ja chegou.

O QUE ESTE MODULO DECIDE
------------------------
Duas coisas, e a segunda e a que define o robo inteiro:

1) `coletar_links()` — onde ficam as telas da arvore de pagamento;
2) `analisar()` + `classificar()` — a tela POSTA FORMULARIO ou conversa por
   AJAX? As duas telas de CNAB ja mapeadas neste repo sao uma de cada tipo:

       remessa de cobranca  -> <form> com action    -> robo_remessa
       processar retorno    -> ajax + parametro Acao -> robo_retorno

   e os dois robos ficaram bem diferentes por causa disso. So o HTML diz qual e
   o caso da tela de Pagamento BMP.

A ARMADILHA QUE O `analisar()` EVITA
------------------------------------
Campo que so existe DENTRO do `<script>` nao e elemento nenhum no DOM real. A
tela de remessa de cobranca tem um

    <input name="Mens0${quantidadeMensagensParaBancoAux.value}" ...>

dentro de um template literal, e o `gerar.py` levou isso para o POST antes de
aprender a remover `<script>`/`<style>`/comentario ANTES de varrer. Este modulo
ja nasce com a licao aplicada — e com teste que a trava.
"""
import html as _html
import re
import urllib.parse

# Moldes possiveis (texto estavel: o relatorio e os testes citam)
MOLDE_FORM = "form"            # posta formulario, como a remessa de cobranca
MOLDE_AJAX = "ajax"            # conversa por parametro `Acao`, como o retorno
MOLDE_INDEFINIDO = "indefinido"


def absoluto(base, alvo):
    """Resolve um alvo relativo contra a URL da pagina."""
    return urllib.parse.urljoin(base, _html.unescape((alvo or "").strip()))


def atributo(tag, nome):
    """Valor de um atributo dentro de uma tag crua. None se nao houver."""
    m = re.search(rf'{nome}\s*=\s*"([^"]*)"', tag or "", re.I) or \
        re.search(rf"{nome}\s*=\s*'([^']*)'", tag or "", re.I)
    return _html.unescape(m.group(1)) if m else None


def sem_js(html):
    """Tira <script>, <style> e comentario. Ver a armadilha no docstring."""
    limpo = re.sub(r"<script\b.*?</script>", " ", html or "", flags=re.S | re.I)
    limpo = re.sub(r"<style\b.*?</style>", " ", limpo, flags=re.S | re.I)
    return re.sub(r"<!--.*?-->", " ", limpo, flags=re.S)


def coletar_links(html, base):
    """{url absoluta: rotulo} de tudo que aponta para um `.php`.

    Colhe as tres formas que o Smart usa, e as tres precisam existir: `href=`,
    `window.open(...)` e qualquer string entre aspas terminada em `.php` dentro
    do JS — o menu de varias telas e montado por funcao, nao por `<a>`.

    Varre o HTML INTEIRO, com o `<script>` incluido: aqui o JS e fonte, nao
    ruido. E o oposto de `analisar()`, e a diferenca e deliberada.
    """
    achados = {}

    for m in re.finditer(
            r"<a\b[^>]*href\s*=\s*[\"']([^\"'#][^\"']*)[\"'][^>]*>(.*?)</a>",
            html or "", re.I | re.S):
        alvo = m.group(1)
        if ".php" not in alvo.lower():
            continue
        rotulo = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(2))).strip()
        url = absoluto(base, alvo)
        # o rotulo melhor ganha: o mesmo .php aparece varias vezes, as vezes com
        # o texto vazio (link de icone)
        if rotulo or url not in achados:
            achados[url] = rotulo or achados.get(url, "")

    for m in re.finditer(r"[\"']([^\"'\s]+\.php(?:\?[^\"'\s]*)?)[\"']",
                         html or "", re.I):
        achados.setdefault(absoluto(base, m.group(1)), "")

    return achados


def _campos_do_form(corpo):
    """Inputs, selects e textareas de um <form>, na ordem em que aparecem."""
    campos = []
    for tag in re.findall(r"<input\b[^>]*>", corpo, re.I):
        campos.append({
            "elem": "input",
            "nome": atributo(tag, "name") or "",
            "tipo": (atributo(tag, "type") or "text").lower(),
            "valor": atributo(tag, "value") or "",
            "id": atributo(tag, "id") or "",
            "marcado": re.search(r"\bchecked\b", tag, re.I) is not None,
        })
    for bloco in re.findall(r"<select\b.*?</select>", corpo, re.S | re.I):
        cabeca = bloco.split(">")[0]
        opcoes = [(atributo(o, "value") or "",
                   re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", o)).strip())
                  for o in re.findall(r"<option[^>]*>[^<]*", bloco, re.I)]
        marcada = re.search(r"<option[^>]*\bselected\b[^>]*>", bloco, re.I)
        escolhido = (atributo(marcada.group(0), "value") if marcada
                     else (opcoes[0][0] if opcoes else ""))
        campos.append({
            "elem": "select", "tipo": "select",
            "nome": atributo(cabeca, "name") or "",
            "id": atributo(cabeca, "id") or "",
            "opcoes": opcoes,
            # o que o navegador MANDARIA: a option `selected`, ou a primeira
            "valor": escolhido or "",
        })
    for tag in re.findall(r"<textarea\b[^>]*>", corpo, re.I):
        campos.append({
            "elem": "textarea", "tipo": "textarea",
            "nome": atributo(tag, "name") or "",
            "id": atributo(tag, "id") or "",
        })
    return campos


def analisar(html, base):
    """Tudo que o robo precisa saber sobre uma tela.

    Retorna dict com `forms`, `ajax`, `acoes` e `links`. Deliberadamente cru: a
    decisao de qual campo importa e humana, e o que isto faz e poupar a leitura
    de milhares de linhas de HTML.
    """
    corpo_limpo = sem_js(html or "")

    forms = []
    for m in re.finditer(r"<form\b([^>]*)>(.*?)</form>", corpo_limpo, re.S | re.I):
        cabeca, corpo = m.group(1), m.group(2)
        forms.append({
            "nome": atributo(cabeca, "name") or "(sem nome)",
            "action": absoluto(base, atributo(cabeca, "action") or ""),
            "method": (atributo(cabeca, "method") or "get").upper(),
            "campos": _campos_do_form(corpo),
        })

    # endpoints de ajax e valores de `Acao` — sairem do HTML INTEIRO e o ponto:
    # eles so existem dentro do <script>.
    ajax = sorted({absoluto(base, u) for u in re.findall(
        r"[\"']([^\"'\s]*ajax[^\"'\s]*\.php[^\"'\s]*)[\"']", html or "", re.I)})
    acoes = sorted({a for a in re.findall(
        r"Acao\s*[:=]\s*[\"']([A-Z_][A-Z0-9_]{3,})[\"']", html or "")})

    return {"forms": forms, "ajax": ajax, "acoes": acoes,
            "links": coletar_links(html, base)}


def classificar(info):
    """(molde, motivo) — que tipo de robo esta tela pede.

    `Acao` pesa mais que `<form>` de propriedade: a tela de Processar Retorno
    TEM forms (o de upload, o de filtro), e mesmo assim o trabalho todo dela
    passa pelo ajax. Achar `Acao` e sinal forte; achar so form e o caso comum.
    """
    if info.get("acoes"):
        return MOLDE_AJAX, (f"{len(info['acoes'])} valor(es) de `Acao` no JS — "
                            "a tela conversa por ajax, como o robo_retorno")
    if info.get("ajax"):
        return MOLDE_AJAX, ("ha endpoint de ajax, mas nenhum `Acao` legivel — "
                            "confira o HTML salvo antes de decidir")
    com_campos = [f for f in info.get("forms") or []
                  if any(c["nome"] for c in f["campos"])]
    if com_campos:
        nomes = ", ".join(f["nome"] for f in com_campos[:3])
        return MOLDE_FORM, (f"{len(com_campos)} form(s) com campos ({nomes}) — "
                            "posta formulario, como o robo_remessa")
    return MOLDE_INDEFINIDO, ("nem `Acao` nem form com campos: a tela pode viver "
                              "num <frame>/<iframe>, e a URL certa e a do frame")


def frames(html, base):
    """URLs de <frame>/<iframe>. O molde 'indefinido' quase sempre mora num."""
    achados = []
    for tag in re.findall(r"<(?:i?frame)\b[^>]*>", html or "", re.I):
        src = atributo(tag, "src")
        if src:
            achados.append(absoluto(base, src))
    return sorted(set(achados))


# Campos que sao BOTAO: nunca entram num POST montado por nos. O navegador so
# manda o botao que foi CLICADO, e nos nao clicamos em nada — mandar todos seria
# pedir ao PHP para executar a acao de cada um deles.
_BOTOES = ("submit", "button", "reset", "image")


def montar_filtro(form, valores=None, permitir=("pesquisar",)):
    """Corpo urlencoded que reproduz o SUBMIT DE BUSCA de um form lido da tela.

    Existe para um caso so: telas cuja grade so aparece depois do filtro, como a
    `pagtobmp`. Reproduz o que o navegador manda ao clicar em "Pesquisar" — nada
    alem disso.

    AS TRES TRAVAS, e nenhuma e decorativa:

    1. **Botao nenhum entra.** O navegador manda apenas o botao clicado; mandar
       todos seria pedir ao PHP a acao de cada um. Numa tela de PAGAMENTO, um
       desses botoes gera remessa.
    2. **So passa se houver um campo de `permitir`.** O form da `pagtobmp` traz
       `pesquisar=1` fixo; se um dia a tela mudar e esse campo sumir, e sinal de
       que o form nao e mais "so busca" — e ai isto levanta, em vez de postar as
       cegas num form que virou outra coisa.
    3. **Placeholder de template fica de fora** (`${...}`), a mesma licao do
       `gerar.py`.

    Args:
        form: um item de `analisar(...)["forms"]`.
        valores: overrides {nome: valor} (a conta, o status...).
        permitir: nomes de campo que marcam este form como "de busca".

    Returns:
        (corpo_urlencoded, campos_finais)

    Raises:
        ValueError: se nenhum campo de `permitir` estiver presente.
    """
    presentes = {c["nome"] for c in form.get("campos") or [] if c.get("nome")}
    if not (presentes & set(permitir)):
        raise ValueError(
            f"este form nao parece ser de busca: nenhum de {list(permitir)} "
            f"entre os campos ({sorted(presentes)}). Nao vou postar as cegas.")

    campos = {}
    for c in form.get("campos") or []:
        nome = c.get("nome") or ""
        if not nome or c.get("tipo") in _BOTOES:
            continue
        if "${" in nome:
            continue
        valor = str(c.get("valor") or "")
        if "${" in valor:
            valor = ""
        campos[nome] = valor
    campos.update({k: str(v) for k, v in (valores or {}).items()})
    return urllib.parse.urlencode(campos), campos


# --------------------------------------------------------------------------- #
# o arquivo gerado
# --------------------------------------------------------------------------- #
def _chave_pix_compativel(g100: bytes, chave: bytes) -> bool:
    """A chave cabe no dominio G100 declarado pelo segmento B."""
    if g100 == b"01":
        return re.fullmatch(rb"\+?\d{10,14}", chave) is not None
    if g100 == b"02":
        return re.fullmatch(rb"[^@\s]+@[^@\s]+", chave) is not None
    if g100 == b"03":
        return re.fullmatch(rb"(?:\d{11}|\d{14})", chave) is not None
    if g100 == b"04":
        return re.fullmatch(
            rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
            chave,
        ) is not None
    return False


def reparar_padding_info12_cnab240(dados: bytes) -> tuple[bytes, int]:
    """Recompoe somente o padding omitido da Informacao 12 do segmento B.

    O Smart produziu quatro segmentos B curtos em 01/09/2026 (152, 168, 177
    e 180 bytes). Nos quatro, as posicoes 1-127 estavam completas, a chave Pix
    estava inteira e os 14 caracteres finais tambem; faltavam apenas os espacos
    entre a chave e esse sufixo. Pelo manual DBS, a Informacao 12 ocupa as
    posicoes 128-226, ou 99 caracteres.

    O reparo e fail-closed: so aceita registro detalhe B, G100 de chave
    (01-04), chave valida para o tipo e sufixo numerico completo. Qualquer
    outra linha fica intacta para `inspecionar_arquivo()` continuar recusando.
    Preserva a quebra de linha original.

    Returns:
        Tupla com os bytes resultantes e a quantidade de segmentos reparados.
    """
    if not dados:
        return dados, 0

    resultado = []
    reparados = 0
    for linha in dados.splitlines(keepends=True):
        if linha.endswith(b"\r\n"):
            corpo, quebra = linha[:-2], b"\r\n"
        elif linha.endswith((b"\n", b"\r")):
            corpo, quebra = linha[:-1], linha[-1:]
        else:
            corpo, quebra = linha, b""

        if not 142 <= len(corpo) < 240:
            resultado.append(linha)
            continue
        if corpo[7:8] != b"3" or corpo[13:14] != b"B":
            resultado.append(linha)
            continue

        g100 = corpo[14:17].strip()
        sufixo = corpo[-14:]
        chave = corpo[127:-14].strip(b" ")
        if not sufixo.isdigit() or not _chave_pix_compativel(g100, chave):
            resultado.append(linha)
            continue

        reparado = corpo[:127] + chave.ljust(99, b" ") + sufixo
        if len(reparado) != 240:
            resultado.append(linha)
            continue

        resultado.append(reparado + quebra)
        reparados += 1

    return b"".join(resultado), reparados


def inspecionar_arquivo(dados):
    """O que veio no download: e CNAB mesmo, e de que layout?

    POR QUE ISTO E PURO E TEM TESTE
    -------------------------------
    E a trava que separa "arquivo" de "pagina de erro". O `robo_remessa` aprendeu
    isso na cobranca: quando a sessao cai no meio, o Smart devolve HTML com
    status 200, e sem esta checagem o robo grava a pagina de erro com nome de
    `.REM`. Fica um arquivo que parece existir, entra na pasta que o Financeiro
    olha, e so quebra la na frente — no banco.

    O LAYOUT NAO E CHUTADO. A cobranca e CNAB-400 (`01REMESSA`); pagamento
    costuma ser CNAB-240, mas "costuma" nao serve. Aqui o layout e DEDUZIDO do
    comprimento das linhas, e quem quiser exigir um valor especifico compara com
    `layout` — em vez de embutir a suposicao nesta funcao.

    Retorna dict: e_texto, e_html, linhas, comprimentos, layout, header, ok, motivo.
    """
    if not dados:
        return {"ok": False, "motivo": "resposta vazia", "e_texto": False,
                "e_html": False, "linhas": 0, "comprimentos": [], "layout": "?",
                "header": ""}

    cabeca = dados[:200].lstrip()
    e_html = cabeca[:1] in (b"<", b"{")
    if e_html:
        return {"ok": False,
                "motivo": "veio HTML/JSON (sessao caida ou id invalido?)",
                "e_texto": False, "e_html": True, "linhas": 0,
                "comprimentos": [], "layout": "?",
                "header": cabeca[:120].decode("latin-1", errors="replace")}

    try:
        texto = dados.decode("latin-1")
    except Exception as e:                                          # noqa: BLE001
        return {"ok": False, "motivo": f"nao decodificou: {e}", "e_texto": False,
                "e_html": False, "linhas": 0, "comprimentos": [], "layout": "?",
                "header": ""}

    linhas = [ln for ln in texto.splitlines() if ln.strip()]
    if not linhas:
        return {"ok": False, "motivo": "arquivo sem linhas", "e_texto": True,
                "e_html": False, "linhas": 0, "comprimentos": [], "layout": "?",
                "header": ""}

    comprimentos = sorted({len(ln) for ln in linhas})
    if comprimentos == [240]:
        layout = "CNAB-240"
    elif comprimentos == [400]:
        layout = "CNAB-400"
    else:
        layout = f"irregular ({comprimentos})"

    ok = len(comprimentos) == 1
    return {"ok": ok,
            "motivo": "ok" if ok else f"linhas de tamanhos diferentes: {comprimentos}",
            "e_texto": True, "e_html": False, "linhas": len(linhas),
            "comprimentos": comprimentos, "layout": layout,
            "header": linhas[0][:120]}


# --------------------------------------------------------------------------- #
# a grade e o POST de geracao
# --------------------------------------------------------------------------- #
def ler_grade(html, base):
    """O que a grade `multipagForm` traz: campos, titulos, botoes e arquivos.

    `titulos` sai na ORDEM DO DOM porque o `todosCheckeds` do JS e montado
    varrendo `form.elements` — ordem diferente muda o corpo do POST.

    `botoes` e a parte que vale ler: a tela oferece UMA acao, e qual e depende do
    STATUS que foi filtrado (medido em 21/08/2026, comparando os dois HTML):

        filtro P (Pendente) -> GerarMultipag(this, 1)  "Gerar ..."
        filtro G (Gerado)   -> GerarMultipag(this, 3)  "Cancelar ..."

    Mesmo form, mesmo endpoint, mesmos titulos. So muda o digito. Por isso o
    `montar_geracao` confere o botao antes de montar qualquer coisa.
    """
    corpo_form = _recortar_form(sem_js(html or ""), "multipagForm")

    campos = {}
    for tag in re.findall(r"<input\b[^>]*>", corpo_form, re.I):
        nome = atributo(tag, "name")
        tipo = (atributo(tag, "type") or "text").lower()
        if not nome or tipo in _BOTOES or tipo == "checkbox":
            continue
        campos[nome] = atributo(tag, "value") or ""

    titulos = []
    for tag in re.findall(r"<input\b[^>]*>", corpo_form, re.I):
        if (atributo(tag, "name") or "") != "ckTitulo":
            continue
        # `dataset.tipopix == 1` no JS: ausente ou "0" cai no ramo NAO-PIX
        titulos.append({"id": atributo(tag, "value") or "",
                        "pix": (atributo(tag, "data-tipopix") or "0") == "1"})

    botoes = []
    for m in re.finditer(r"GerarMultipag\(\s*this\s*,\s*(\d+)\s*\)", html or ""):
        trecho = (html or "")[m.end():m.end() + 800]
        rot = re.search(r"<span>([^<]{0,80})</span>", trecho)
        botoes.append({"acao": int(m.group(1)),
                       "rotulo": (rot.group(1).strip() if rot else "")})

    arquivos = []
    for m in re.finditer(
            r"mandarsispag\.php\?file=(\d+)[^>]*>\s*([^<]{0,60})", html or "", re.I):
        arquivos.append({"id": m.group(1), "nome": m.group(2).strip()})

    return {"campos": campos, "titulos": titulos, "botoes": botoes,
            "arquivos": arquivos}


def _recortar_form(pagina, nome):
    """So o trecho do <form name=nome>...</form> (a pagina tem mais de um)."""
    m = re.search(rf"<form\b[^>]*name\s*=\s*[\"\']?{nome}[\"\']?[^>]*>",
                  pagina, re.I)
    if not m:
        return pagina
    fim = pagina.lower().find("</form>", m.end())
    return pagina[m.end():fim if fim > 0 else len(pagina)]


def montar_geracao(grade, acao=1, somente_ids=None):
    """Corpo do POST que GERA a remessa. Copia fiel de `GerarMultipag(bt, acao)`.

    O JS, linha a linha:

        ckTitulo marcado e dataset.tipopix == 1  ->  checkedsPIX += valor + ','
        senao                                    ->  checkeds    += valor + ','
        sempre                                   ->  todosCheckeds += valor + ','
        temPIX = 1 se houve algum PIX
        form.acao.value = acao ; form.processar.value = "1" ; form.submit()

    A virgula no FIM de cada lista nao e descuido meu: e o que o `+=` do JS
    produz, e o PHP do outro lado espera exatamente isso.

    A separacao PIX/nao-PIX NAO e cosmetica — ela decide os LOTES do CNAB-240.
    Medido no `CP2108000001.REM`: lote 0001 forma 41 (TED) e lote 0002 forma 45
    (PIX). Mandar tudo em `checkeds` sairia como TED, errado e em silencio.

    Raises:
        ValueError: se a grade nao oferecer o botao da `acao` pedida. E a trava
            que impede gerar sobre uma grade filtrada por "Gerado" — onde o
            unico botao e CANCELAR, e o POST e identico exceto por um digito.
        ValueError: se nao houver titulo (o JS mostra "Selecione pelo menos um").
    """
    disponiveis = {b["acao"] for b in grade.get("botoes") or []}
    if acao not in disponiveis:
        rotulos = ", ".join(f"{b['acao']}={b['rotulo']!r}"
                            for b in grade.get("botoes") or []) or "(nenhum)"
        raise ValueError(
            f"esta grade nao oferece a acao {acao}. Botoes presentes: {rotulos}. "
            "Gerar exige a grade do filtro PENDENTE — na de 'Gerado' o unico "
            "botao e CANCELAR.")

    escolhidos = [t for t in grade.get("titulos") or []
                  if not somente_ids or t["id"] in set(somente_ids)]
    if not escolhidos:
        raise ValueError("nenhum titulo na grade (o JS diria 'Selecione pelo "
                         "menos um pagamento')")

    checkeds = "".join(f"{t['id']}," for t in escolhidos if not t["pix"])
    checkeds_pix = "".join(f"{t['id']}," for t in escolhidos if t["pix"])
    todos = "".join(f"{t['id']}," for t in escolhidos)

    campos = dict(grade.get("campos") or {})
    campos.update({
        "checkeds": checkeds,
        "checkedsPIX": checkeds_pix,
        "todosCheckeds": todos,
        "temPIX": "1" if checkeds_pix else "0",
        "acao": str(acao),
        "processar": "1",
    })
    campos = {k: v for k, v in campos.items() if "${" not in k}
    return urllib.parse.urlencode(campos), campos


def nome_do_arquivo(content_disposition, padrao="remessa.REM"):
    """Nome real do arquivo, tirado do header `content-disposition`.

    POR QUE O NOME IMPORTA
    ----------------------
    Nao e cosmetica: o nome CARREGA O SEQUENCIAL da remessa
    (`CP` + DDMM + 6 digitos). Medido em 21/08/2026, duas geracoes seguidas
    saem como `CP2108000001.REM` e `CP2108000003.REM` — e e por esse numero que
    se conversa com o banco e se acha o arquivo depois. Salvar como
    `gerado_<timestamp>.REM` joga fora a unica identidade que o arquivo tem.

    Aceita as duas formas que aparecem na pratica (com e sem aspas) e devolve
    so o basename: `filename` com caminho dentro seria escrita fora da pasta.
    """
    m = re.search(r"filename\*?=(?:UTF-8\'\')?\"?([^\";]+)",
                  content_disposition or "", re.I)
    if not m:
        return padrao
    # basename dos DOIS separadores: o header pode vir de um servidor Windows
    bruto = m.group(1).strip().replace("\\", "/").split("/")[-1]
    limpo = _INVALIDOS_NOME.sub("_", bruto).strip(" .")
    return limpo or padrao


_INVALIDOS_NOME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
