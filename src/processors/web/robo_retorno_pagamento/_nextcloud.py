# -*- coding: utf-8 -*-
"""Le e move o `.RET` de pagamento no Nextcloud (FINANCEIRO/Pagamentos-MoneyPlus/_RETORNOS).

WRAPPER FINO sobre o cliente COMPARTILHADO
(`src.common.clients.nextcloud_webdav.NextcloudWebDAV`) — mesmo cliente que
`robo_pagamento/_nextcloud.py` usa para subir o `.REM`. `baixar`/`mover` foram
adicionados a esse cliente para este robo (ele so tinha `enviar`/`listar_nomes`
ate 26/08/2026 — nenhum consumidor antes precisava LER do Nextcloud).
"""
import retorno_pagamento_config as cfg
from src.common.clients.nextcloud_webdav import NextcloudWebDAV

_NC = NextcloudWebDAV(dest_base=cfg.NC_DEST_BASE, cred_env=cfg.NC_ENV)


def disponivel() -> bool:
    return _NC.disponivel()


def listar_pendentes() -> list:
    """Nomes de `.RET`/`.ret` na raiz de `_RETORNOS` (fora das subpastas de saida)."""
    nomes = _NC.listar_nomes("")
    return sorted(n for n in nomes if n.lower().endswith(".ret"))


def baixar(nome_arquivo: str) -> bytes | None:
    """Baixa um `.RET` da raiz de `_RETORNOS`. None se nao existe ou deu erro."""
    return _NC.baixar("", nome_arquivo)


def mover_para(nome_arquivo: str, subpasta_destino: str) -> bool:
    """Move da raiz de `_RETORNOS` para uma das 3 subpastas de saida
    (`SUB_PROCESSADOS`/`SUB_REVISAR`/`SUB_ERRO` em `retorno_pagamento_config`)."""
    return _NC.mover("", nome_arquivo, subpasta_destino)
