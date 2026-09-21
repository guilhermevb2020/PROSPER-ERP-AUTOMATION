# -*- coding: utf-8 -*-
"""Dias uteis / feriados (Sao Paulo) — o robo baixa sempre o ULTIMO DIA UTIL.

Portado do standalone. Feriados: nacionais + estaduais SP (lib 'holidays') +
Carnaval/Corpus Christi + aniversario de SP (25/01). Sem a lib, cai para
sabado/domingo apenas. Ajustes finos por env (DOC2YOU_FERIADOS_EXTRA / _IGNORAR).
"""
import os
from datetime import date, timedelta

_cache = {}


def _datas_env(nome: str) -> set:
    out = set()
    for parte in (os.getenv(nome, "") or "").replace(";", ",").split(","):
        parte = parte.strip()
        if not parte:
            continue
        try:
            a, m, d = (int(x) for x in parte.split("-"))
            out.add(date(a, m, d))
        except Exception:
            pass
    return out


_INCLUIR_CARNAVAL_CORPUS = os.getenv("DOC2YOU_INCLUIR_CARNAVAL_CORPUS", "1") not in ("0", "false", "False")
_ANIVERSARIO_SP = os.getenv("DOC2YOU_ANIVERSARIO_SP", "1") not in ("0", "false", "False")


def _anos(centro: date):
    return list(range(centro.year - 1, centro.year + 2))


def feriados_set(centro: date = None) -> set:
    centro = centro or date.today()
    if centro.year in _cache:
        return _cache[centro.year]
    anos = _anos(centro)
    fs = set()
    try:
        import holidays
        fs |= set(holidays.Brazil(subdiv="SP", categories=("public",), years=anos).keys())
        if _INCLUIR_CARNAVAL_CORPUS:
            try:
                opt = holidays.Brazil(subdiv="SP", categories=("optional",), years=anos)
                for d, nome in opt.items():
                    n = nome.lower()
                    if "carnaval" in n or "corpus" in n:
                        fs.add(d)
            except Exception:
                pass
    except Exception:
        print("[dias_uteis] lib 'holidays' ausente — usando so sabado/domingo + env.")
    if _ANIVERSARIO_SP:
        for a in anos:
            fs.add(date(a, 1, 25))
    fs |= _datas_env("DOC2YOU_FERIADOS_EXTRA")
    fs -= _datas_env("DOC2YOU_FERIADOS_IGNORAR")
    _cache[centro.year] = fs
    return fs


def eh_dia_util(d: date, fs: set = None) -> bool:
    fs = feriados_set(d) if fs is None else fs
    return d.weekday() < 5 and d not in fs


def dia_util_anterior(hoje: date = None) -> date:
    """Ultimo dia util ANTES de 'hoje' (default = hoje real)."""
    hoje = hoje or date.today()
    fs = feriados_set(hoje)
    d = hoje - timedelta(days=1)
    for _ in range(60):
        if eh_dia_util(d, fs):
            return d
        d -= timedelta(days=1)
    return d


def dia_alvo_download(hoje: date = None) -> date:
    """Documento-alvo do robô: 2 dias úteis pra trás = o dia útil ANTERIOR ao último
    dia útil. Ex.: roda numa terça → baixa a sexta anterior (pula fim de semana).
    Dá tempo dos documentos do dia anterior ficarem todos assinados."""
    hoje = hoje or date.today()
    return dia_util_anterior(dia_util_anterior(hoje))


def dias_uteis_entre(dini: date, dfim: date) -> list:
    out, d = [], dini
    while d <= dfim:
        if eh_dia_util(d):
            out.append(d)
        d += timedelta(days=1)
    return out
