# -*- coding: utf-8 -*-
"""
exclusoes.py - o que NAO marcar na geracao da remessa CNAB 400.

O process-automation escreve `exclusoes.json` (ver remessa_config.ARQ_EXCLUSOES) com
os titulos abertos de sacado cujo endereco sai sem numero do pagador — o MoneyPlus
recusa o arquivo inteiro por UM desses (09 e 17/09/2026). Aqui o robo:

  1. le a lista e confere a validade (`gerado_em` + `validade_horas`, que viajam
     dentro dela) — lista velha e ignorada COM AVISO: gerar como sempre e melhor
     do que gerar com a lista de anteontem;
  2. casa cada titulo da grade de confirmacao com a lista pela LINHA da grade
     (`celulas`, lidas em gerar.ler_form): documento exato E (sacado ou nosso
     numero ou id). ⚠️ O valor do checkbox NAO e o id do titulo do ERP (17/09/2026:
     911243 no controle do participante contra 948707 no titulo), por isso o casamento
     e pela linha, nao pelo value;
  3. desmarca os casados e recalcula o resumo. O que nao casou fica como estava —
     e o log diz quantos da lista ficaram sem par, para alguem olhar a grade.

Nada aqui levanta: lista ilegivel = geracao normal, avisada.
"""
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone

import remessa_config as cfg


def _norm(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", texto).strip().upper()


def _digitos(texto):
    return re.sub(r"\D", "", str(texto or "")).lstrip("0")


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

    Exige o documento numa celula EXATA e mais uma prova (sacado, nosso numero ou id):
    o mesmo numero de documento existe em cedentes diferentes.
    """
    celulas = [str(c).strip() for c in (titulo.get("celulas") or [])]
    if not celulas:
        return None
    celulas_norm = [_norm(c) for c in celulas]
    celulas_dig = [_digitos(c) for c in celulas]
    valor = str(titulo.get("valor") or "").strip()
    for ident, item in lista.get("titulos", {}).items():
        doc = str(item.get("documento") or "").strip()
        if not doc or doc not in celulas:
            continue
        sacado = _norm(item.get("sacado"))[:20]
        nosso = _digitos(item.get("nosso_numero"))
        if (sacado and any(c.startswith(sacado) for c in celulas_norm)) \
                or (nosso and nosso in celulas_dig) \
                or ident in celulas or ident == valor:
            return {"id": ident, **item}
    return None


def aplicar(form, lista, log=print):
    """Desmarca na grade os titulos da lista. Devolve os casados; o form muda no lugar."""
    if not lista:
        return []
    casados = []
    for t in form.get("titulos", []):
        if not t.get("marcado"):
            continue
        item = casar(t, lista)
        if item:
            t["marcado"] = False
            casados.append(item)
            log(f"    excluido da remessa: {item.get('documento')} · {item.get('sacado')} · "
                f"{item.get('motivo', 'na lista de exclusao')}")
    resumo = form.get("resumo")
    if isinstance(resumo, dict):
        resumo["titulos_marcados"] = sum(1 for t in form.get("titulos", []) if t["marcado"])
        resumo["excluidos"] = len(casados)
    return casados
