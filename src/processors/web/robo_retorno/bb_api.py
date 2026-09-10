"""Conferência do CNAB reconstruído pela API BB antes e depois do Smart.

Em 09/09/2026 o Smart retornou status OK e 'Ocorrência não encontrada' para
o comando 12, inclusive no registro original do banco. Status OK e igualdade
de valores não bastam. Este contrato é optativo do fluxo BB API e não muda
o processamento dos arquivos bancários ou de depósito existentes.
"""
import re
from collections import Counter
from datetime import datetime

import portao

# Código do retorno -> ação na grade / contador de processamento.
OCORRENCIAS = {
    "02": ("entrada confirmada", "confirmacao_entrada"),
    "06": ("liquidado", "liquidacao"),
    "10": ("baixa", "baixa"),
    "12": ("abatimento concedido", "abatimento_concedido"),
    "14": ("prorrogado", "prorrogacao"),
}


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
            esperados[(linha[116:126].strip(), valor, pago, abatimento, data, acao)] += 1
    for linha in detalhes or []:
        if portao.e_linha_de_resumo(linha):
            continue
        observados[(linha.get("numero_titulo", "").strip(), portao._num(linha.get("valor_titulo_arq")),
                    portao._num(linha.get("valor_pago")), portao._num(linha.get("abatimento")),
                    linha.get("data_ocorrencia"), portao._sem_acento(linha.get("acao_tomada")))] += 1
    if not esperados or esperados != observados:
        erros.append("grade BB diverge das ocorrências, documentos, datas ou valores enviados")
    veredito["contadores_esperados"] = dict(contadores)
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


def avaliar_resultado(resposta, esperados):
    """Exige resposta explícita e exatamente os eventos liberados na prévia."""
    erros = []
    if not isinstance(resposta, dict):
        erros.append("resposta BB do Smart não é objeto JSON")
    else:
        if resposta.get("message") != "OK":
            erros.append("Smart não confirmou message=OK")
        if not esperados or any(type(n) is not int or n <= 0 for n in esperados.values()):
            erros.append("quantidades esperadas ausentes ou inválidas")
        for campo, esperado in esperados.items():
            if _contador(resposta.get(campo)) != esperado:
                erros.append(f"{campo} diverge da quantidade esperada")
        if _contador(resposta.get("DifSistema")) != 0:
            erros.append("DifSistema diferente de zero")
        for campo, valor in resposta.items():
            if campo in {*esperados, "message", "DifSistema", "varRetorno2", "dateMsgRetorno"}:
                continue
            if _contador(valor) != 0:
                erros.append(f"resultado adicional ou ilegível: {campo}")
    return {"comprovado": not erros, "erros": erros,
            "sumario": "; ".join(erros) if erros else "eventos BB comprovados pelo Smart"}
