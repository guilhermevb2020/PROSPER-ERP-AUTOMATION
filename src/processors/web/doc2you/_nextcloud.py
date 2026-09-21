# -*- coding: utf-8 -*-
"""Upload dos PDFs do Doc2You pro Nextcloud via WebDAV.

WRAPPER FINO sobre o uploader COMPARTILHADO
(`src.common.clients.nextcloud_webdav.NextcloudWebDAV`) — a logica vive la (dedup
com o robo_credito e demais jobs). Preserva a interface de modulo
(`enviar`/`disponivel`/`garantir_pasta`/`DEST_BASE`) usada pelo `baixar_dia.py`.
"""
import os

from src.common.clients.nextcloud_webdav import NextcloudWebDAV

_NC = NextcloudWebDAV(
    dest_base=os.getenv("DOC2YOU_NC_DEST",
                        "CADASTRO/LASTRO DAS OPERACOES/DOCUMENTOS ASSINADOS"),
    cred_env=os.getenv("DOC2YOU_NC_ENV", "/app/config/nextcloud.env"),
)

# Nomes de modulo preservados (compatibilidade com quem importa este modulo).
DEST_BASE = _NC.dest_base
NC_URL = _NC.url
NC_USER = _NC.user
NC_PASS = _NC.password


def disponivel() -> bool:
    return _NC.disponivel()


def garantir_pasta(rel_dir: str) -> None:
    _NC.garantir_pasta(rel_dir)


def enviar(conteudo: bytes, subpasta: str, nome_arquivo: str) -> int:
    return _NC.enviar(conteudo, subpasta, nome_arquivo)
