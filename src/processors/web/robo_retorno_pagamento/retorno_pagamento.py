# -*- coding: utf-8 -*-
"""
retorno_pagamento.py - as DUAS etapas de `retornopagtobmp.php`: upload e confirmação.

O robô INSERE — não julga o resultado. Ninguém revisa fila nenhuma depois: o
único critério que decide se um arquivo pode ser tentado de novo é se a
requisição chegou a sair (rede/sessão), não o que o Smart respondeu. Isso é
mecânico, não é "confiar no resultado".

⚠️ **A tela é em DUAS etapas, medido em 26/08/2026 (primeira submissão real
desta automação).** O upload (`enviar`) não efetiva nada — só faz o Smart
PARSEAR o `.RET`, casar com os títulos que reconhecer e devolver uma PRÉVIA:
um form SEM arquivo, com um campo oculto `target` (o caminho do arquivo que o
Smart deixou staged no servidor) e um botão "Continuar" que resubmete o MESMO
form só com `target`+`origem`. É esse segundo POST (`confirmar`) que de fato
dá baixa — sem ele, o upload sozinho não faz nada além de mostrar a prévia.
"""
from __future__ import annotations

import re
import urllib.parse

_RE_TARGET = re.compile(r'name="target"\s+value="([^"]*)"')


def montar_multipart(nome_arquivo: str, dados: bytes) -> dict:
    """O corpo EXATO do form `retornoSispag` — medido em 26/08/2026.

    `origem` vai vazio de propósito: não existe JS nesta tela que o preencha
    antes do `form.submit()` (só `ValidarForm` checa se há arquivo escolhido).
    Um humano clicando "Processar" manda exatamente isto.
    """
    return {
        "MAX_FILE_SIZE": "15728640",
        "form_submit": "1",
        "origem": "",
        "avatar_file": {
            "name": nome_arquivo,
            "mimeType": "application/octet-stream",
            "buffer": dados,
        },
    }


def enviar(ctx, url: str, nome_arquivo: str, dados: bytes, timeout: int = 120_000) -> dict:
    """POST multipart em `url`. Devolve dict cru: `ok_rede`, `status`, `html`, `erro_rede`.

    Nunca levanta por erro de rede: devolve `erro_rede` preenchido, e quem
    decide (deixar na entrada para tentar de novo) é `robo_retorno_pagamento.py`.
    """
    multipart = montar_multipart(nome_arquivo, dados)
    try:
        r = ctx.request.post(url, multipart=multipart, timeout=timeout)
    except Exception as e:                                              # noqa: BLE001
        return {"ok_rede": False, "erro_rede": str(e), "status": None, "html": None}

    try:
        corpo = r.body().decode("iso-8859-1", errors="replace")
    except Exception as e:                                              # noqa: BLE001
        return {"ok_rede": False, "erro_rede": f"corpo ilegível: {e}",
                "status": r.status, "html": None}

    return {"ok_rede": True, "erro_rede": None, "status": r.status, "html": corpo}


def extrair_target(html: str) -> str | None:
    """Acha o `target` que a etapa 1 devolveu. `None` quando a resposta não é
    a prévia esperada (a tela mudou, ou algo saiu diferente do medido)."""
    m = _RE_TARGET.search(html)
    return m.group(1) if m else None


def confirmar(ctx, url: str, target: str, timeout: int = 120_000) -> dict:
    """Etapa 2 — a que de fato efetiva. Sem arquivo, form comum (a tela de
    confirmação não tem `enctype=multipart`, só a de upload tem) — mesmo
    padrão de POST urlencoded que `descobrir.py`/`smart_session.py` já usam
    neste repo (nunca usar o `form=` do Playwright: não há precedente dele
    aqui, e o urlencode manual + header explícito já é o caminho provado)."""
    corpo = urllib.parse.urlencode({"origem": "", "target": target})
    try:
        r = ctx.request.post(
            url, data=corpo,
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=timeout)
    except Exception as e:                                              # noqa: BLE001
        return {"ok_rede": False, "erro_rede": str(e), "status": None, "html": None}

    try:
        corpo = r.body().decode("iso-8859-1", errors="replace")
    except Exception as e:                                              # noqa: BLE001
        return {"ok_rede": False, "erro_rede": f"corpo ilegível: {e}",
                "status": r.status, "html": None}

    return {"ok_rede": True, "erro_rede": None, "status": r.status, "html": corpo}
