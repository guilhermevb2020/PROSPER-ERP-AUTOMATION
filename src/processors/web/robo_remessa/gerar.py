# -*- coding: utf-8 -*-
"""
gerar.py - geracao da remessa no Smart, por HTTP (sem clicar em tela).

Replica o que o navegador faz nas duas telas:

  1) FILTRO  -> POST financeiro/confirmardadosremessa.php
     (os campos sao os do form `Form` de remessaocorrencia.php:
      contaCorrente, NumCarteira, modalidadeS, filtroData, periodos, classes...)
     Resposta = a tela de confirmacao com a grade de titulos.

  2) GERAR    -> POST no MESMO endpoint, agora com o form `ConfirmarDadosConta`
     inteiro + os checkboxes dos titulos + submit_prazo=0.
     Resposta = redirect p/ gridremessagerada.php?resultado=<base64 do JSON
     {"idsSucesso": {"<tipo>": <id>}, "idsErro": []}>.

Por que reproduzir o form INTEIRO em vez de montar os campos na mao: a tela tem
campos que mudam por conta/banco (instrucao, qtdeInstrucoesBanco, ckNNI7/8/9,
qtdDias1/2/3...). Lendo tudo do HTML da resposta, o robo acompanha a tela sem
precisar de manutencao a cada variacao.

Validacoes espelhadas do ValidarGeraRemessa() (JS da tela), p/ nao mandar um
POST que o proprio Smart recusaria:
  - existeEntrada == 0 e instrucoes vazio  -> "Nao existe(m) titulo(s)"
  - NumSequencial vazio                     -> obrigatorio
  - nenhum titulo marcado e instrucoes ""   -> "Selecione os titulos"
  - instrucao derivada de ckNNI7/8/9 (protestar/devolucao/negativar)

SEGURANCA: `gerar()` so dispara o POST final se dry_run=False. Em dry_run ele
devolve exatamente o que MANDARIA, p/ conferencia.
"""
import base64
import html as _html
import re
import urllib.parse

import remessa_config as cfg
import login as autenticacao          # parece_deslogado (expira.php com status 200)

CLASSES_RISCO_PADRAO = ["P", "T", "E", "B", "BG", "CL", "CE", "I", "BA"]


# --------------------------------------------------------------------------- #
# passo 1: filtro -> tela de confirmacao
# --------------------------------------------------------------------------- #
def filtrar(ctx, conta, carteira, modalidade="G", periodo_ini="", periodo_fim="",
            classes=None, timeout=90_000):
    """POST do filtro. Retorna o HTML da tela de confirmacao (ou None)."""
    campos = {
        "form_submit": "1", "tipo": "remessa",
        "contaCorrente": str(conta), "NumCarteira": str(carteira),
        "modalidadeS": modalidade, "filtroData": "o.DataOcorrencia",
        "Periodo1": periodo_ini, "Periodo2": periodo_fim,
        "op1": "", "op2": "", "cTitulosResiduais": "",
        "coluna_ordem": "vencimento", "ordem": "asc",
    }
    corpo = urllib.parse.urlencode(campos) + "".join(
        f"&sClasseRisco%5B%5D={c}" for c in (classes or CLASSES_RISCO_PADRAO))
    r = ctx.request.post(
        cfg.SMART_BASE + "/financeiro/confirmardadosremessa.php", data=corpo,
        headers={"content-type": "application/x-www-form-urlencoded"},
        timeout=timeout)
    if r.status != 200:
        return None
    texto = r.body().decode("iso-8859-1", errors="replace")
    # sessao morta responde 200 com um redirect JS p/ expira.php -> nao e "tela
    # sem titulo", e "voce nao esta logado" (ver login.parece_deslogado)
    if autenticacao.parece_deslogado(texto):
        return None
    return texto


# --------------------------------------------------------------------------- #
# passo 2: ler o form da tela de confirmacao
# --------------------------------------------------------------------------- #
def _atr(tag, nome):
    m = re.search(rf'{nome}\s*=\s*"([^"]*)"', tag, re.I) or \
        re.search(rf"{nome}\s*=\s*'([^']*)'", tag, re.I) or \
        re.search(rf"{nome}\s*=\s*([^\s>]+)", tag, re.I)
    return _html.unescape(m.group(1)) if m else None


def _recortar_form(pagina, nome):
    """Devolve so o trecho do <form name=nome> ... </form>.

    A tela tem DOIS forms: `ConfirmarDadosConta` (o que interessa) e `aux`
    (com um contaCorrente2 que NAO deve ir no POST). Sem o recorte, campos do
    form errado vazavam pro corpo da requisicao.
    """
    m = re.search(rf"<form\b[^>]*name\s*=\s*[\"']?{nome}[\"']?[^>]*>", pagina, re.I)
    if not m:
        return pagina
    fim = pagina.lower().find("</form>", m.end())
    return pagina[m.end():fim if fim > 0 else len(pagina)]


def ler_form(pagina, nome_form="ConfirmarDadosConta"):
    """Extrai do HTML da tela de confirmacao tudo que o POST de geracao precisa.

    Retorna dict:
      campos   -> {nome: valor} dos inputs simples (hidden/text/select)
      titulos  -> [{nome, valor, marcado, celulas}] dos checkboxes de titulo (id=prazo);
                  `celulas` sao os textos dos <td> da MESMA linha da grade — e por
                  eles que a lista de exclusao acha o titulo (exclusoes.casar),
                  porque o `value` do checkbox nao e o id do titulo do ERP
      opcoes   -> {nome: valor} dos checkboxes de instrucao (ckNNI7/8/9 etc.)
      resumo   -> {NumSequencial, existeEntrada, instrucoes, quant, ...}
    """
    # Tira <script>/<style>/comentarios ANTES de varrer. Sem isso entram no POST
    # "campos" que so existem dentro do JS - a tela tem um
    #   <input name="Mens0${quantidadeMensagensParaBancoAux.value}" ...>
    # dentro de um template literal, que nao e elemento nenhum no DOM real.
    pagina = re.sub(r"<script\b.*?</script>", " ", pagina, flags=re.S | re.I)
    pagina = re.sub(r"<style\b.*?</style>", " ", pagina, flags=re.S | re.I)
    pagina = re.sub(r"<!--.*?-->", " ", pagina, flags=re.S)
    # e so o form certo (a pagina tem outro form, `aux`)
    pagina = _recortar_form(pagina, nome_form)

    campos, titulos, opcoes = {}, [], {}
    # ckNNI7/8/9 (protestar/devolucao/negativar): o JS olha se o elemento EXISTE
    # na tela, nao so se esta marcado -> guardamos os dois estados.
    instrucoes_box = {}
    celulas_por_checkbox = _celulas_das_linhas(pagina)

    for tag in re.findall(r"<input\b[^>]*>", pagina, re.I):
        # Controles disabled não são enviados pelo navegador. No BB existem
        # dois qtdDias com o mesmo nome: o desabilitado não pode sobrescrever
        # o ativo nem virar qtdDias= (o servidor interpreta a presença).
        if re.search(r"\sdisabled(?:\s|=|/?>)", tag, re.I):
            continue
        nome = _atr(tag, "name")
        if not nome:
            continue
        tipo = (_atr(tag, "type") or "text").lower()
        valor = _atr(tag, "value") or ""
        ident = _atr(tag, "id") or ""
        marcado = re.search(r"\bchecked\b", tag, re.I) is not None
        if ident in ("ckNNI7", "ckNNI8", "ckNNI9"):
            instrucoes_box[ident] = marcado
        if tipo == "checkbox":
            if ident == "prazo" or nome.startswith("prazo"):
                titulos.append({"nome": nome, "valor": valor, "marcado": marcado,
                                "celulas": celulas_por_checkbox.get(nome, [])})
            elif marcado:
                opcoes[nome] = valor or "on"
        elif tipo == "radio":
            if marcado:
                campos[nome] = valor
        elif tipo in ("submit", "button", "reset", "image"):
            continue           # botao nao vai no POST
        else:
            campos[nome] = valor

    # selects: pega a option marcada (ou a primeira)
    for bloco in re.findall(r"<select\b.*?</select>", pagina, re.S | re.I):
        nome = _atr(bloco.split(">")[0], "name")
        if not nome:
            continue
        m = re.search(r"<option[^>]*\bselected\b[^>]*>", bloco, re.I) or \
            re.search(r"<option[^>]*>", bloco, re.I)
        if m:
            campos[nome] = _atr(m.group(0), "value") or ""

    # textarea (mensagens p/ o banco)
    for m in re.finditer(r"<textarea\b([^>]*)>(.*?)</textarea>", pagina, re.S | re.I):
        nome = _atr(m.group(1), "name")
        if nome:
            campos[nome] = _html.unescape(m.group(2)).strip()

    resumo = {k: campos.get(k, "") for k in
              ("NumSequencial", "existeEntrada", "instrucoes", "quant",
               "ocorrencias", "numBanco", "numConta", "carteira", "modalidadeS")}
    resumo["titulos_total"] = len(titulos)
    resumo["titulos_marcados"] = sum(1 for t in titulos if t["marcado"])
    return {"campos": campos, "titulos": titulos, "opcoes": opcoes,
            "instrucoes_box": instrucoes_box, "resumo": resumo}


def _celulas_das_linhas(pagina):
    """{nome do checkbox: [texto de cada <td> da linha]} — a grade, linha a linha.

    Generico de proposito: nao sabe qual coluna e o documento ou o sacado; devolve
    todas e quem casa decide. Linha sem checkbox de titulo e ignorada.
    """
    saida = {}
    for linha in re.findall(r"<tr\b.*?</tr>", pagina, re.S | re.I):
        nomes = [m for m in re.findall(r"<input\b[^>]*>", linha, re.I)
                 if (_atr(m, "type") or "").lower() == "checkbox"
                 and ((_atr(m, "id") or "") == "prazo" or (_atr(m, "name") or "").startswith("prazo"))]
        if not nomes:
            continue
        celulas = [_html.unescape(re.sub(r"<[^>]+>", " ", td)).strip()
                   for td in re.findall(r"<td\b[^>]*>(.*?)</td>", linha, re.S | re.I)]
        celulas = [re.sub(r"\s+", " ", c) for c in celulas if c.strip()]
        for tag in nomes:
            nome = _atr(tag, "name")
            if nome and nome not in saida:
                saida[nome] = celulas
    return saida


def validar(form):
    """Espelha ValidarGeraRemessa(): retorna (ok, motivo)."""
    c, r = form["campos"], form["resumo"]
    if str(r.get("existeEntrada") or "0") == "0" and not (r.get("instrucoes") or ""):
        return False, "nao existe(m) titulo(s) para gerar remessa"
    if not (c.get("NumSequencial") or "").strip():
        return False, "NumSequencial vazio (obrigatorio)"
    if r["titulos_marcados"] == 0 and not (r.get("instrucoes") or ""):
        return False, "nenhum titulo selecionado"
    return True, "ok"


def _instrucao(form):
    """Copia fiel do fim do ValidarGeraRemessa():

        if (protestar && devolucao) {
            protestar.checked ? "1" : devolucao.checked ? "-1" : ""
        } else if (protestar && protestar.checked)  "1"
          else if (devolucao && devolucao.checked)  "-1"
          else if (negativar)                       "1"     <- EXISTE, nao "checked"
          else                                      ""

    Detalhe que parece bobo mas nao e: nos dois primeiros ramos vale o `checked`,
    no ramo do negativar vale a EXISTENCIA do elemento. Errar isso muda a
    instrucao de protesto gravada no CNAB.
    """
    box = form.get("instrucoes_box", {})
    tem_prot, tem_dev, tem_neg = ("ckNNI7" in box, "ckNNI8" in box, "ckNNI9" in box)
    if tem_prot and tem_dev:
        if box["ckNNI7"]:
            return "1"
        if box["ckNNI8"]:
            return "-1"
        return ""
    if tem_prot and box["ckNNI7"]:
        return "1"
    if tem_dev and box["ckNNI8"]:
        return "-1"
    if tem_neg:
        return "1"
    return ""


def montar_post(form, somente_marcados=True):
    """Monta o corpo do POST de GERACAO a partir do form lido."""
    campos = dict(form["campos"])
    campos["submit_prazo"] = "0"          # o JS zera isso antes do submit
    campos["instrucao"] = _instrucao(form)
    campos.pop("bGerarArquivo", None)
    campos.pop("Cancelar", None)

    # cinto de seguranca: nada de placeholder de template ("${...}") no POST
    campos = {k: v for k, v in campos.items() if "${" not in k and "${" not in str(v)}
    pares = [(k, v) for k, v in campos.items()]
    pares += [(k, v) for k, v in form["opcoes"].items()]
    for t in form["titulos"]:
        if t["marcado"] or not somente_marcados:
            pares.append((t["nome"], t["valor"]))
    return urllib.parse.urlencode(pares)


# --------------------------------------------------------------------------- #
# passo 3: disparar a geracao
# --------------------------------------------------------------------------- #
def _ids_do_resultado(url_ou_html):
    """Acha o param `resultado` (base64 do JSON) e devolve [(tipo, id)]."""
    import base64
    import json
    m = re.search(r"gridremessagerada\.php\?resultado=([A-Za-z0-9+/=%_-]+)", url_ou_html)
    if not m:
        return [], None
    bruto = urllib.parse.unquote(m.group(1))
    try:
        pad = bruto + "=" * (-len(bruto) % 4)
        dados = json.loads(base64.b64decode(pad).decode("utf-8", errors="replace"))
    except Exception:
        return [], None
    pares = [(str(t), int(i)) for t, i in (dados.get("idsSucesso") or {}).items()]
    return pares, dados.get("idsErro") or []


def gerar(ctx, form, dry_run=True, timeout=180_000):
    """Dispara (ou simula) o POST de geracao.

    Retorna dict: {ok, motivo, corpo, ids, erros}
      - dry_run=True  -> ok=None e `corpo` com o que SERIA enviado.
    """
    valido, motivo = validar(form)
    corpo = montar_post(form)
    if not valido:
        return {"ok": False, "motivo": motivo, "corpo": corpo, "ids": [],
                "erros": [], "enviado": False}
    if dry_run:
        return {"ok": None, "motivo": "DRY_RUN (nada enviado)", "corpo": corpo,
                "ids": [], "erros": [], "enviado": False}

    try:
        r = ctx.request.post(
            cfg.SMART_BASE + "/financeiro/confirmardadosremessa.php", data=corpo,
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=timeout)
    except Exception as e:                                          # noqa: BLE001
        # PERIGO, e e o PIOR caso: timeout ou conexao cortada NAO dizem se o
        # Smart processou o POST. Vale a MESMA regra do bloco de baixo —
        # `enviado=True`, para quem chamou RECUPERAR pela tela de listagem, que e
        # a unica leitura confiavel do que existe la. Tratar como falha deixaria
        # a remessa ORFA: sequencial consumido, titulos fora da fila, arquivo
        # nunca baixado, e a proxima rodada diria "nada a fazer".
        # Medido em 11/09/2026: `read ETIMEDOUT` na mp gfer e `Timeout 90000ms`
        # na mp giga escaparam por aqui como excecao; as duas contas foram
        # puladas em silencio e a rodada ainda terminou com exit 0.
        return {"ok": False, "enviado": True,
                "motivo": f"POST nao respondeu ({type(e).__name__}: {e}) - PODE ter sido gerado",
                "corpo": corpo, "ids": [], "erros": []}
    dados = r.body()
    texto = dados.decode("iso-8859-1", errors="replace")
    # O BB também responde com o próprio CNAB. Guardar os bytes completos
    # permite relacionar o download ao POST sem repetir a geração. Cabeçalhos
    # de sessão (Set-Cookie etc.) nunca entram nessa evidência.
    evidencia = {}
    if form["resumo"].get("numBanco") == "001":
        headers = getattr(r, "headers", {})
        evidencia["resposta_http"] = {
            "status": r.status, "url": r.url,
            "content_type": headers.get("content-type", ""),
            "content_disposition": headers.get("content-disposition", ""),
            "body_base64": base64.b64encode(dados).decode("ascii"),
        }

    # o resultado pode vir na URL final (redirect seguido) ou no corpo
    ids, erros = _ids_do_resultado(r.url or "")
    if not ids:
        ids, erros = _ids_do_resultado(texto)
    if not ids:
        # PERIGO: o POST FOI (status 200) -> a remessa provavelmente EXISTE no
        # Smart (sequencial consumido, titulos fora da fila), mas nao sei os ids.
        # `enviado=True` avisa quem chamou p/ RECUPERAR pela tela de listagem em
        # vez de tratar como falha - senao vira remessa orfa, nunca baixada, e a
        # proxima tentativa dira "nada a fazer" porque os titulos ja sairam.
        return {"ok": False, "enviado": True,
                "motivo": f"POST foi (status={r.status}) mas nao li o resultado",
                "corpo": corpo, "ids": [], "erros": [], "html": texto[:1500], **evidencia}
    return {"ok": True, "enviado": True, "motivo": "gerado", "corpo": corpo,
            "ids": ids, "erros": erros or [], **evidencia}
