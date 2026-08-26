# -*- coding: utf-8 -*-
"""
retorno_pagamento.py - monta e envia o upload para `retornopagtobmp.php`.

O robô INSERE — não julga o resultado. Ninguém revisa fila nenhuma depois: o
único critério que decide se um arquivo pode ser tentado de novo é se a
requisição chegou a sair (rede/sessão), não o que o Smart respondeu. Isso é
mecânico, não é "confiar no resultado".
"""
from __future__ import annotations


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
