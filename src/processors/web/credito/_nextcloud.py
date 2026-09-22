# -*- coding: utf-8 -*-
"""Upload dos PDFs do robo de analise de credito pro Nextcloud via WebDAV.

WRAPPER FINO sobre o uploader COMPARTILHADO
(`src.common.clients.nextcloud_webdav.NextcloudWebDAV`) — a logica vive la (dedup
com o doc2you). Preserva a interface de modulo (`enviar`/`disponivel`/
`garantir_pasta`/`DEST_BASE`) usada pelo `subfluxos.py`.

Destinos (dentro do DEST_BASE = CADASTRO/LASTRO DAS OPERACOES):
  nf operacao/NFE<op>.pdf · resumo da operacao/resumo<op>.pdf
  documentos complementares operacoes/<op>/<docs>
"""
import os

from src.common.clients.nextcloud_webdav import NextcloudWebDAV

_NC = NextcloudWebDAV(
    dest_base=os.getenv("ROBO_CREDITO_NC_DEST", "CADASTRO/LASTRO DAS OPERACOES"),
    cred_env=os.getenv("ROBO_CREDITO_NC_ENV", "/app/config/nextcloud.env"),
)

DEST_BASE = _NC.dest_base


def disponivel() -> bool:
    return _NC.disponivel()


def garantir_pasta(rel_dir: str) -> None:
    _NC.garantir_pasta(rel_dir)


def enviar(conteudo: bytes, subpasta: str, nome_arquivo: str) -> int:
    return _NC.enviar(conteudo, subpasta, nome_arquivo)
