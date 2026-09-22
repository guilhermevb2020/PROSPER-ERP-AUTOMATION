"""Conferência do CNAB reconstruído pela API BB antes e depois do Smart.

Em 09/09/2026 o Smart retornou status OK e 'Ocorrência não encontrada' para
o comando 12, inclusive no registro original do banco. Status OK e igualdade
de valores não bastam. Este contrato é optativo do fluxo BB API e não muda
o processamento dos arquivos bancários ou de depósito existentes.
"""
import base64
import re
from collections import Counter
from datetime import datetime
from html import unescape

import portao

# Código do retorno -> ação na grade / contador de processamento.
OCORRENCIAS = {
    "02": ("entrada confirmada", "confirmacao_entrada"),
    "06": ("liquidado", "liquidacao"),
    "10": ("baixa", "baixa"),
    "12": ("abatimento concedido", "abatimento_concedido"),
    "14": ("prorrogado", "prorrogacao"),
}

# Uma linha do `varRetorno2` por titulo que o Smart NAO liquidou por ja estar liquidado.
JA_LIQUIDADO = re.compile(r"t[íi]tulo\s+(\S.*?)\s+j[áa] liquidado anteriormente\Z", re.IGNORECASE)
# O irmao do `refinan`: titulo que o Smart NAO liquidou porque ja estava quitado no PAGAMENTO
# de uma operacao. Contador `tituloPagtoOperacao`. 18/09/2026, entrega 43: tres liquidacoes,
# `refinan=2` + `tituloPagtoOperacao=1`, sem `liquidacao`, os tres nomeados; este contrato nao
# conhecia o contador, marcou inconclusivo e o robo saiu com exit 6.
PAGO_VIA_OPERACAO = re.compile(
    r"t[íi]tulo\s+(\S.*?)\s+j[áa] liquidado via pagamento da\s+op\.?\s*\S+\Z", re.IGNORECASE)
# Contador do Smart -> frase que NOMEIA cada titulo dele no `varRetorno2`.
JA_ENCERRADOS = (("refinan", JA_LIQUIDADO), ("tituloPagtoOperacao", PAGO_VIA_OPERACAO))


def _documento(texto):
    """Número do documento como a grade do Smart o mostra: espaços internos colapsados.

    14/09/2026: o arquivo BBAPI000002632A181A8EADBC493.RET levava `Q  19902/A` (dois
    espaços, como o ERP guarda o título) e `retorno.extrair_titulos` colapsa o HTML da
    grade em `Q 19902/A`. Comparar o campo cru recusou o arquivo inteiro: 100
    liquidações, 99 idênticas. Só a comparação colapsa; o arquivo enviado não muda.
    O validador do recibo no process-automation (`bb_recibo._documento_comparavel`)
    faz o mesmo, e os dois portões têm de continuar concordando.
    """
    return " ".join(str(texto or "").split())


def avaliar_grade(linhas, detalhes, quantidade_upload):
    """Confere envelope, quantidade, ação e valores de cada registro enviado."""
    eventos = linhas[1:-1]
    veredito = portao.avaliar_grade(
        detalhes, exigir_status_ok=True, exigir_valor_arquivo=True,
        quantidade_esperada=quantidade_upload, quantidade_arquivo=len(eventos),
    )
    erros = veredito["erros_grade"]
    envelope = (
        len(linhas) >= 3 and all(len(linha) == 400 for linha in linhas)
        and linhas[0].startswith("02RETORNO01COBRANCA")
        and linhas[0][76:79] == "001" and linhas[-1].startswith("9201001")
    )
    esperados, observados, contadores = Counter(), Counter(), Counter()
    if not envelope:
        erros.append("envelope BB API inválido")
    else:
        convenio = linhas[0][149:156]
        if not re.fullmatch(r"[0-9]{7}", convenio) or not int(convenio):
            erros.append("convênio BB ausente")
        for numero, linha in enumerate(linhas, 1):
            if linha[394:400] != f"{numero:06d}":
                erros.append("sequencial de registros BB inválido")
        documentos = []
        for linha in eventos:
            codigo = linha[108:110]
            if (not linha.startswith("7") or linha[31:38] != convenio
                    or not re.fullmatch(r"[0-9]{17}", linha[63:80])
                    or not linha[63:80].startswith(convenio)
                    or not linha[38:63].strip("0 ") or not linha[116:126].strip()
                    or linha[17:31] != linhas[0][26:40]
                    or codigo not in OCORRENCIAS):
                erros.append("identidade ou ocorrência BB API inválida")
                continue
            try:
                data = datetime.strptime(linha[110:116], "%d%m%y").strftime("%d/%m/%Y")
                valor = int(linha[152:165]) / 100
                pago = int(linha[253:266].strip() or "0") / 100
                abatimento = int(linha[227:240].strip() or "0") / 100
            except ValueError:
                erros.append("data ou valor CNAB BB inválido")
                continue
            acao, contador = OCORRENCIAS[codigo]
            contadores[contador] += 1
            if contador == "liquidacao":
                documentos.append(_documento(linha[116:126]))
            esperados[(_documento(linha[116:126]), valor, pago, abatimento, data, acao)] += 1
    for linha in detalhes or []:
        if portao.e_linha_de_resumo(linha):
            continue
        observados[(_documento(linha.get("numero_titulo")), portao._num(linha.get("valor_titulo_arq")),
                    portao._num(linha.get("valor_pago")), portao._num(linha.get("abatimento")),
                    linha.get("data_ocorrencia"), portao._sem_acento(linha.get("acao_tomada")))] += 1
    if not esperados or esperados != observados:
        erros.append("grade BB diverge das ocorrências, documentos, datas ou valores enviados")
    veredito["contadores_esperados"] = dict(contadores)
    # Viaja no veredito, como os contadores: e o que `avaliar_resultado` precisa para
    # conferir, um a um, os titulos que o Smart disser ja liquidados. Persistido no
    # recibo, ele chega igual na reutilizacao feita por `bb_entrega._anterior`.
    veredito["documentos_liquidacao"] = sorted(documentos) if envelope else []
    veredito["liberado"] = not erros and not veredito["recusados"]
    if not veredito["liberado"]:
        veredito["sumario"] = "; ".join(erros + [r["motivo"] for r in veredito["recusados"]])
    return veredito


def _contador(valor):
    if valor is None or valor == "":
        return 0
    if type(valor) is int and valor >= 0:
        return valor
    if isinstance(valor, str) and re.fullmatch(r"[0-9]+", valor):
        return int(valor)
    return None


def documentos_ja_liquidados(bruto, padrao=JA_LIQUIDADO):
    """Documentos que o `varRetorno2` nomeia como ja liquidados ANTES desta entrega.

    `padrao` escolhe a frase: `JA_LIQUIDADO` (contador `refinan`) ou `PAGO_VIA_OPERACAO`
    (contador `tituloPagtoOperacao`). Cada contador so se prova pela frase DELE.

    O campo e HTML em base64 e latin-1, um `<div>` por titulo. So a frase exata
    conta: em 14/09/2026 a entrega 24 trouxe `ja liquidado via pagamento da Op.
    65432` em titulos de BAIXA que o Smart processou normalmente, SEM o contador —
    mensagem informativa, que nao reduz nada e nao pode ser lida como recusa.
    Formato que nao casar devolve lista vazia, e quem chama recusa por contagem.
    """
    if not isinstance(bruto, str) or not bruto:
        return []
    try:
        texto = base64.b64decode(bruto + "=" * (-len(bruto) % 4)).decode("latin-1")
    except ValueError:
        return []
    achados = []
    for bloco in re.split(r"</div>|<br\s*/?>", texto, flags=re.IGNORECASE):
        linha = " ".join(unescape(re.sub(r"<[^>]+>", " ", bloco)).split())
        casado = padrao.match(linha)
        if casado:
            achados.append(casado.group(1))
    return achados


def _liquidados_antes(resposta, esperados, documentos, erros):
    """Quantos dos nossos titulos o Smart deixou de liquidar por ja estarem liquidados.

    O Smart devolve isso em `refinan`, com `msgLiquidados` e uma linha por titulo
    no `varRetorno2`. Medido em 14/09/2026: a entrega 27 mandou 44 liquidacoes e
    voltou `liquidacao=36`, `refinan=8` e exatamente 8 titulos nomeados, todos dos
    44 — a soma fecha e nenhuma baixa faltou. Antes disto a entrega ficava
    pendente para sempre, sem job que a fechasse (BUG-679).

    `tituloPagtoOperacao` e o mesmo desfecho por outro caminho (titulo ja quitado no
    pagamento de uma operacao). Medido em 18/09/2026: a entrega 43 mandou 3 liquidacoes
    e voltou `refinan=2` + `tituloPagtoOperacao=1`, sem `liquidacao`, os tres nomeados.

    A prova e titulo a titulo, nao o contador sozinho: o nome citado tem de ser um
    documento que NOS enviamos, a quantidade citada tem de ser a do contador, cada
    contador pela frase DELE (`JA_ENCERRADOS`), e o mesmo titulo nao vale para os dois.
    O validador do recibo no process-automation (`bb_recibo._liquidados_antes`) faz o
    mesmo, e os dois lados tem de continuar concordando.
    """
    nossos = Counter(_documento(d) for d in documentos or ())
    total, ja_citados = 0, Counter()
    for campo, padrao in JA_ENCERRADOS:
        quantos = _contador(resposta.get(campo))
        if quantos is None:  # ilegivel: nada e absorvido, e o laco final de `avaliar_resultado` o aponta
            return 0
        if not quantos:
            continue
        if campo == "refinan" and resposta.get("msgLiquidados") is not True:
            erros.append("refinan sem a mensagem dos titulos ja liquidados")
            return 0
        if _contador(esperados.get("liquidacao")) < total + quantos:
            erros.append(f"{campo} maior que as liquidacoes enviadas")
            return 0
        citados = Counter(_documento(d) for d in documentos_ja_liquidados(resposta.get("varRetorno2"), padrao))
        if sum(citados.values()) != quantos or (citados + ja_citados) - nossos:
            erros.append("titulos ja liquidados nao conferem com os enviados")
            return 0
        ja_citados += citados
        total += quantos
    return total


def avaliar_resultado(resposta, esperados, documentos=()):
    """Exige resposta explícita e exatamente os eventos liberados na prévia.

    `documentos` sao os numeros de documento das LIQUIDACOES enviadas, como
    `avaliar_grade` os deixou no veredito. Sem eles, `refinan` nunca e absorvido.
    """
    erros = []
    if not isinstance(resposta, dict):
        erros.append("resposta BB do Smart não é objeto JSON")
    else:
        if resposta.get("message") != "OK":
            erros.append("Smart não confirmou message=OK")
        if not esperados or any(type(n) is not int or n <= 0 for n in esperados.values()):
            erros.append("quantidades esperadas ausentes ou inválidas")
        anteriores = _liquidados_antes(resposta, esperados, documentos, erros)
        for campo, esperado in esperados.items():
            alvo = esperado - anteriores if campo == "liquidacao" else esperado
            if _contador(resposta.get(campo)) != alvo:
                erros.append(f"{campo} diverge da quantidade esperada")
        if _contador(resposta.get("DifSistema")) != 0:
            erros.append("DifSistema diferente de zero")
        for campo, valor in resposta.items():
            if campo in {*esperados, "message", "DifSistema", "varRetorno2", "dateMsgRetorno"}:
                continue
            if anteriores and campo in ("refinan", "msgLiquidados", "tituloPagtoOperacao"):
                continue
            if _contador(valor) != 0:
                erros.append(f"resultado adicional ou ilegível: {campo}")
    return {"comprovado": not erros, "erros": erros,
            "sumario": "; ".join(erros) if erros else "eventos BB comprovados pelo Smart"}
