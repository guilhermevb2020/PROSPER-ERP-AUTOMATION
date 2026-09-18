# -*- coding: utf-8 -*-
"""
exclusoes.py - o que NAO marcar na geracao da remessa CNAB 400: o que o banco recusaria.

Duas regras, as duas antes de o Smart gerar o arquivo:

A) LISTA do process-automation (`exclusoes.json`, ver remessa_config.ARQ_EXCLUSOES):
   titulos abertos de sacado cujo endereco sai sem numero do pagador — o MoneyPlus
   recusa o arquivo INTEIRO por UM desses (09 e 17/09/2026).
     1. le a lista e confere a validade (`gerado_em` + `validade_horas`, que viajam
        dentro dela) — lista velha e ignorada COM AVISO;
     2. casa cada linha da grade com a lista: documento exato E CNPJ do sacado (ou,
        onde a grade trouxer, nome do sacado, nosso numero ou id). ⚠️ A grade real
        (18/09/2026, 40 telas) mostra na coluna "Sacado" o CNPJ, NAO o nome, e nao
        mostra nosso numero nem id do titulo; o `value` do checkbox e o id da
        ocorrencia no Smart (897629), nao o do titulo (934235). A versao de 17/09
        casava por nome/nosso numero/id e nunca acharia uma linha real;
     3. desmarca os casados.

B) VENCIMENTO (so MoneyPlus, `numBanco` 274, so "Envio de cobranca"): entrada com
   vencimento no dia da geracao ou antes fica RETIDA na fila do Smart. O banco a
   recusa com 16 (vencimento invalido) e, no hibrido, 92 ("a data de vencimento deve
   ser maior que a data atual"): o MoneyPlus processa o arquivo no mesmo dia do envio
   (19:00). Medido em 15 dias (03-18/09/2026): vencimento no dia do envio = recusado;
   no dia seguinte = registrado. Caso que obrigou (18/09/2026): 13274-001 TECNOMIDIA,
   recusado por CEP em 19/08, voltou a fila hoje com o CEP corrigido e o vencimento de
   hoje — o arquivo saiu e a conferencia do envio avisou que o banco ia recusar.
   Retido, ele NAO vira "despachado" no Smart: continua na fila e sai na geracao
   seguinte a prorrogacao no ERP. O vencimento e lido da coluna "Vencimento" pelo
   cabecalho da grade; sem cabecalho legivel, nada e retido (a conferencia do envio,
   no process-automation, continua avisando).

Nada aqui levanta: lista ilegivel = geracao normal, avisada.
"""
import json
import os
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import remessa_config as cfg

#: O dia da geracao e o de Sao Paulo: o container roda em UTC, e as 21h em Sao Paulo ja
#: e o dia seguinte em UTC — o vencimento de amanha pareceria vencido.
TZ_SP = ZoneInfo("America/Sao_Paulo")

#: E do MoneyPlus a regra do vencimento (motivos 16 e 92 da ocorrencia 03).
BANCO_MONEYPLUS = "274"


def _norm(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", texto).strip().upper()


def _digitos(texto):
    return re.sub(r"\D", "", str(texto or "")).lstrip("0")


def _doc(texto):
    """CPF/CNPJ comparavel: letras e digitos (CNPJ alfanumerico desde jul/2026), sem zeros a esquerda."""
    return re.sub(r"[^0-9A-Z]", "", str(texto or "").upper()).lstrip("0")


def hoje_sp():
    """O dia da geracao, em Sao Paulo."""
    return datetime.now(TZ_SP).date()


def _coluna(titulo, nome):
    """O texto da coluna `nome` (comparada sem acento e em maiusculas) na linha, ou None."""
    for cabecalho, texto in (titulo.get("colunas") or {}).items():
        if _norm(cabecalho) == nome:
            return texto
    return None


def vencimento_da_linha(titulo):
    """A data da coluna "Vencimento" da linha da grade, ou None se nao der para ler."""
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", (_coluna(titulo, "VENCIMENTO") or "").strip())
    if not m:
        return None
    try:
        return date(int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        return None


def carregar(caminho=None, agora=None, log=print):
    """A lista valida, ou None (ausente, ilegivel, velha) — sempre dizendo por que."""
    caminho = caminho or cfg.ARQ_EXCLUSOES
    if not os.path.exists(caminho):
        log(f"exclusoes: sem lista em {caminho} — geracao sem exclusao")
        return None
    try:
        with open(caminho, encoding="utf-8") as fh:
            lista = json.load(fh)
        gerado_em = datetime.fromisoformat(lista["gerado_em"])
        validade = timedelta(hours=int(lista.get("validade_horas", 30)))
        titulos = lista.get("titulos") or {}
        if not isinstance(titulos, dict):
            raise ValueError("titulos nao e um objeto")
    except (OSError, ValueError, KeyError, TypeError) as e:
        log(f"exclusoes: lista ilegivel em {caminho} ({type(e).__name__}: {e}) — geracao sem exclusao")
        return None
    agora = agora or datetime.now(gerado_em.tzinfo or timezone.utc)
    if gerado_em.tzinfo is None:
        agora = agora.replace(tzinfo=None)
    idade = agora - gerado_em
    if idade > validade:
        log(f"exclusoes: lista de {gerado_em:%d/%m %H:%M} tem {idade.total_seconds() / 3600:.0f} h "
            f"(validade {validade.total_seconds() / 3600:.0f} h) — IGNORADA, geracao sem exclusao")
        return None
    log(f"exclusoes: lista de {gerado_em:%d/%m %H:%M} com {len(titulos)} titulo(s) de "
        f"{len(lista.get('sacados') or {})} sacado(s)")
    return lista


def casar(titulo, lista):
    """O item da lista que esta linha da grade representa, ou None.

    Exige o documento numa celula EXATA e mais uma prova: o CNPJ do sacado (o que a
    grade real mostra) ou, onde houver, nome do sacado, nosso numero ou id — o mesmo
    numero de documento existe em cedentes diferentes.
    """
    celulas = [str(c).strip() for c in (titulo.get("celulas") or [])]
    if not celulas:
        return None
    celulas_norm = [_norm(c) for c in celulas]
    celulas_dig = [_digitos(c) for c in celulas]
    celulas_doc = {_doc(c) for c in celulas}
    valor = str(titulo.get("valor") or "").strip()
    for ident, item in lista.get("titulos", {}).items():
        doc = str(item.get("documento") or "").strip()
        if not doc or doc not in celulas:
            continue
        cnpj = _doc(item.get("sacado_cnpj"))
        sacado = _norm(item.get("sacado"))[:20]
        nosso = _digitos(item.get("nosso_numero"))
        if (cnpj and cnpj in celulas_doc) \
                or (sacado and any(c.startswith(sacado) for c in celulas_norm)) \
                or (nosso and nosso in celulas_dig) \
                or ident in celulas or ident == valor:
            return {"id": ident, **item}
    return None


def reter_vencidos(form, hoje, log=print):
    """Desmarca a ENTRADA do MoneyPlus com vencimento no dia `hoje` ou antes (regra B).

    Devolve os retidos. Outro banco, outra instrucao (quitacao, prorrogacao) e linha sem
    vencimento legivel ficam como estavam — esta ultima com um aviso.
    """
    resumo = form.get("resumo") or {}
    if str(resumo.get("numBanco") or "").strip() != BANCO_MONEYPLUS:
        return []
    retidos, ilegiveis = [], 0
    for t in form.get("titulos", []):
        if not t.get("marcado"):
            continue
        instrucao = _norm(_coluna(t, "INSTRUCAO"))
        if instrucao and not instrucao.startswith("ENVIO"):
            continue
        vencimento = vencimento_da_linha(t)
        if vencimento is None:
            ilegiveis += 1
            continue
        if vencimento > hoje:
            continue
        t["marcado"] = False
        documento = _coluna(t, "NO") or " ".join((t.get("celulas") or [])[:3])
        sacado = _coluna(t, "SACADO") or ""
        retidos.append({"regra": "vencimento", "documento": documento, "sacado_cnpj": sacado,
                        "vencimento": vencimento.isoformat(),
                        "motivo": "vencimento nao e posterior a geracao: o MoneyPlus recusa com 16 "
                                  "(e 92 no hibrido) — prorrogar no ERP"})
        log(f"    retido na fila: {documento} · sacado {sacado} · vence {vencimento:%d/%m/%Y} — "
            f"o MoneyPlus recusa entrada que nao vence depois de hoje (16/92): prorrogar no ERP")
    if ilegiveis:
        log(f"    atencao: {ilegiveis} titulo(s) sem vencimento legivel na grade — nenhum retido por "
            f"vencimento; a conferencia do envio avisa se o banco for recusar")
    return retidos


def aplicar(form, lista, log=print, hoje=None):
    """Desmarca na grade o que o banco recusaria. Devolve os afetados; o form muda no lugar.

    Cada afetado leva `regra`: "lista" (regra A, sacado sem numero) ou "vencimento"
    (regra B). A regra B vale mesmo sem lista.
    """
    afetados = []
    if lista:
        for t in form.get("titulos", []):
            if not t.get("marcado"):
                continue
            item = casar(t, lista)
            if item:
                t["marcado"] = False
                afetados.append({"regra": "lista", **item})
                log(f"    excluido da remessa: {item.get('documento')} · {item.get('sacado')} · "
                    f"{item.get('motivo', 'na lista de exclusao')}")
    afetados += reter_vencidos(form, hoje or hoje_sp(), log=log)
    resumo = form.get("resumo")
    if isinstance(resumo, dict):
        resumo["titulos_marcados"] = sum(1 for t in form.get("titulos", []) if t["marcado"])
        resumo["excluidos"] = sum(1 for a in afetados if a["regra"] == "lista")
        resumo["retidos"] = sum(1 for a in afetados if a["regra"] == "vencimento")
    return afetados
