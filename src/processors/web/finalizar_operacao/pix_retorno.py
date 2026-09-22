# -*- coding: utf-8 -*-
"""
pix_retorno.py - os PIX que o banco ja devolveu HOJE, lidos dos retornos CNAB-240 de
pagamento no Nextcloud (FINANCEIRO/Pagamentos-MoneyPlus/_RETORNOS e _PROCESSADOS).

E a prova de que o PIX saiu. O segmento A traz favorecido, "seu numero" (o id do titulo
no Smart, nao o numero da operacao), data, valor e a ocorrencia; o segmento B traz o
CPF/CNPJ do favorecido. Ocorrencia "00" = credito efetivado. Medido em 22/09/2026 sobre
412 retornos: 795 pagamentos "00" e 33 recusados (55 = chave PIX errada; AL, AN, AP) -
nenhum codigo intermediario, entao "nao e 00" e problema de verdade. O retorno chega uns
10 min depois da remessa (65879: finalizada 15:46, retorno gravado 15:56).

Os nomes comecam por CP + DDMM do dia (CP2209000505.RET). So LEITURA: quem importa o
retorno no Smart e move o arquivo para _PROCESSADOS e o retorno_pagamento.
"""
import re
from datetime import date

OCORRENCIA_EFETIVADO = "00"
SUB_PROCESSADOS = "_PROCESSADOS"

# o que os codigos de recusa querem dizer, quando se sabe (reportar_pagamento, 27/08/2026)
SIGNIFICADO = {"55": "chave PIX cadastrada errada"}


def so_digitos(texto):
    return re.sub(r"\D", "", str(texto or ""))


def documento_normalizado(texto):
    """CPF com 11 digitos ou CNPJ com 14, sem pontuacao; '' se nao houver digito."""
    d = so_digitos(texto)
    if not d:
        return ""
    return d.zfill(11) if len(d) <= 11 else d[-14:].zfill(14)


def _data_iso(ddmmaaaa):
    try:
        return date(int(ddmmaaaa[4:8]), int(ddmmaaaa[2:4]), int(ddmmaaaa[0:2])).isoformat()
    except (ValueError, IndexError):
        return None


def ler_pagamentos(conteudo):
    """Os pagamentos de UM retorno CNAB-240: [{seu_numero, favorecido, data (ISO), valor,
    ocorrencias, documento}]. Linha curta ou fora do padrao e ignorada."""
    texto = conteudo.decode("latin-1") if isinstance(conteudo, (bytes, bytearray)) else str(conteudo)
    pagamentos, atual = [], None
    for linha in texto.splitlines():
        if len(linha) < 240 or linha[7] != "3":
            continue
        if linha[13] == "A":
            try:
                valor = int(linha[119:134]) / 100
            except ValueError:
                atual = None
                continue
            atual = {"seu_numero": linha[73:93].strip(), "favorecido": linha[43:73].strip(),
                     "data": _data_iso(linha[93:101]), "valor": valor,
                     "ocorrencias": linha[230:240].strip(), "documento": ""}
            pagamentos.append(atual)
        elif linha[13] == "B" and atual is not None:
            d = so_digitos(linha[18:32])
            if d:
                atual["documento"] = d[-11:] if linha[17] == "1" else d[-14:].zfill(14)
            atual = None
    return pagamentos


def efetivado(pagamento):
    return (pagamento.get("ocorrencias") or "")[:2] == OCORRENCIA_EFETIVADO


def codigo(pagamento):
    return (pagamento.get("ocorrencias") or "")[:2]


def retornos_do_dia(nuvem, hoje, ja_lidos=None, log=print):
    """{nome: [pagamentos]} dos retornos de HOJE, na raiz e em _PROCESSADOS.
    `ja_lidos` (nome -> pagamentos) evita baixar de novo o que ja foi lido."""
    lidos = dict(ja_lidos or {})
    prefixo = f"CP{hoje:%d%m}"
    for sub in ("", SUB_PROCESSADOS):
        try:
            nomes = nuvem.listar_nomes(sub)
        except Exception as e:  # noqa: BLE001
            log(f"  [pix] nao listei {sub or 'a raiz'} dos retornos: {str(e)[:90]}")
            continue
        for nome in sorted(nomes or ()):
            if nome in lidos or not nome.upper().startswith(prefixo) \
                    or not nome.lower().endswith(".ret"):
                continue
            try:
                dados = nuvem.baixar(sub, nome)
            except Exception as e:  # noqa: BLE001
                log(f"  [pix] nao baixei {nome}: {str(e)[:90]}")
                continue
            if dados:        # sumiu entre listar e baixar (foi movido): a proxima rodada acha
                lidos[nome] = ler_pagamentos(dados)
    return lidos
