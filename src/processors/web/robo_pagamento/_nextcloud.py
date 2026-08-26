# -*- coding: utf-8 -*-
"""Sobe o .REM gerado para o Nextcloud (FINANCEIRO/Pagamentos-MoneyPlus/_A_ENVIAR).

WRAPPER FINO sobre o uploader COMPARTILHADO
(`src.common.clients.nextcloud_webdav.NextcloudWebDAV`) — mesmo cliente que
`robo_remessa/_nextcloud.py` ja usa para o CNAB 400.

Sem arvore de data/banco aqui, ao contrario do robo_remessa: la existem varios
cedentes e varios bancos misturados no mesmo acervo, entao a data e o banco
decidem a pasta. Pagamento e um pagador so, uma pasta so — o job
`enviar_pagamento` (process-automation) le tudo que estiver em
`_A_ENVIAR` direto, sem subpasta.
"""
import os

from src.common.clients.nextcloud_webdav import NextcloudWebDAV

_NC = NextcloudWebDAV(
    dest_base=os.getenv("PAGAMENTO_NC_DEST", "FINANCEIRO/Pagamentos-MoneyPlus/_A_ENVIAR"),
    cred_env=os.getenv("PAGAMENTO_NC_ENV", "/app/config/nextcloud.env"),
)

DEST_BASE = _NC.dest_base


def disponivel() -> bool:
    """So True se ha senha configurada — senao nem tenta e diz por que."""
    return _NC.disponivel()


def enviar(dados: bytes, nome_arquivo: str):
    """Sobe um .REM para a raiz de `_A_ENVIAR`. Retorna (ok, caminho_relativo, detalhe).

    NUNCA levanta: o chamador ja tem o arquivo no disco local, e uma falha de
    rede no Nextcloud nao pode derrubar a rodada de geracao.
    """
    if not disponivel():
        return False, "", "sem credencial do Nextcloud (config/nextcloud.env)"
    alvo = f"{DEST_BASE}/{nome_arquivo}"
    try:
        status = _NC.enviar(dados, "", nome_arquivo)
    except Exception as e:
        return False, alvo, f"erro no upload: {e}"
    if status in (200, 201, 204):
        return True, alvo, f"HTTP {status}"
    return False, alvo, f"HTTP {status}"
