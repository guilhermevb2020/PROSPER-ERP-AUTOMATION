# -*- coding: utf-8 -*-
"""Uploader Nextcloud via WebDAV — COMPARTILHADO (doc2you, robo_credito, ...).

Extraido do `_nextcloud.py` do doc2you (logica identica) p/ eliminar duplicacao.
Sobe como o usuario `automacao` (acesso de escrita no groupfolder CADASTRO). O
Nextcloud indexa uploads WebDAV automaticamente (sem `occ scan`), sem montar pasta
no container nem reiniciar nada.

Uso:
    from src.common.clients.nextcloud_webdav import NextcloudWebDAV
    nc = NextcloudWebDAV(dest_base="CADASTRO/LASTRO DAS OPERACOES/...")
    if nc.disponivel():
        nc.enviar(pdf_bytes, "subpasta", "arquivo.pdf")   # -> 201/204

Cada job passa seu proprio `dest_base` (e opcionalmente `cred_env`). As credenciais
sao lidas do ambiente ou de um arquivo montado (default /app/config/nextcloud.env).
"""
import os
import re
from urllib.parse import quote, unquote

import requests
from dotenv import load_dotenv


class NextcloudWebDAV:
    def __init__(self, dest_base: str, cred_env: str = "/app/config/nextcloud.env",
                 url: str = None, user: str = None, password: str = None):
        # Carrega creds de um arquivo montado (config/) se ainda nao estiverem no env.
        if cred_env and os.path.exists(cred_env):
            load_dotenv(cred_env)
        self.url = (url or os.getenv("NEXTCLOUD_URL", "http://nextcloud")).rstrip("/")
        self.user = user or os.getenv("NEXTCLOUD_USER", "automacao@prospereinvest.com.br")
        self.password = password or os.getenv("NEXTCLOUD_PASSWORD", "")
        self.dest_base = dest_base.rstrip("/")

    def _dav(self, path: str) -> str:
        return f"{self.url}/remote.php/dav/files/{self.user}/{quote(path, safe='/')}"

    def disponivel(self) -> bool:
        """True so se ha senha configurada (senao nao da p/ subir)."""
        return bool(self.password)

    def garantir_pasta(self, rel_dir: str) -> None:
        """MKCOL recursivo (idempotente) - cria cada nivel da pasta se faltar."""
        cur = ""
        for parte in rel_dir.split("/"):
            if not parte:
                continue
            cur = f"{cur}/{parte}" if cur else parte
            try:
                requests.request("MKCOL", self._dav(cur),
                                 auth=(self.user, self.password), timeout=30)
            except Exception:
                pass  # 405 (ja existe) etc. - segue

    def enviar(self, conteudo: bytes, subpasta: str, nome_arquivo: str) -> int:
        """Sobe um arquivo em dest_base/<subpasta>/<nome_arquivo>. Retorna o HTTP
        status (201=criado, 204=sobrescrito)."""
        rel_dir = f"{self.dest_base}/{subpasta}".rstrip("/")
        self.garantir_pasta(rel_dir)
        url = self._dav(f"{rel_dir}/{nome_arquivo}")
        r = requests.put(url, data=conteudo, auth=(self.user, self.password), timeout=180)
        return r.status_code

    def baixar(self, subpasta: str, nome_arquivo: str) -> bytes | None:
        """GET de dest_base/<subpasta>/<nome_arquivo>. None se nao existe ou deu erro."""
        rel_dir = f"{self.dest_base}/{subpasta}".rstrip("/")
        url = self._dav(f"{rel_dir}/{nome_arquivo}")
        try:
            r = requests.get(url, auth=(self.user, self.password), timeout=180)
        except Exception:
            return None
        if r.status_code != 200:
            return None
        return r.content

    def mover(self, subpasta_origem: str, nome_arquivo: str, subpasta_destino: str) -> bool:
        """WebDAV MOVE de dest_base/<origem>/<nome> para dest_base/<destino>/<nome>.

        Cria a pasta de destino se faltar (mesmo tratamento do `enviar`).
        Sobrescreve no destino (`Overwrite: T`) para o chamador nunca travar por
        um arquivo homonimo deixado por uma rodada anterior."""
        destino_dir = f"{self.dest_base}/{subpasta_destino}".rstrip("/")
        self.garantir_pasta(destino_dir)
        origem_rel = f"{self.dest_base}/{subpasta_origem}".rstrip("/")
        origem_url = self._dav(f"{origem_rel}/{nome_arquivo}")
        destino_url = self._dav(f"{destino_dir}/{nome_arquivo}")
        try:
            r = requests.request(
                "MOVE", origem_url, auth=(self.user, self.password),
                headers={"Destination": destino_url, "Overwrite": "T"}, timeout=60)
        except Exception:
            return False
        return r.status_code in (201, 204)

    def listar_nomes(self, subpasta: str) -> set:
        """PROPFIND (Depth 1): nomes dos ARQUIVOS em dest_base/<subpasta>.

        Usado p/ skip-existing (não re-subir o que já está lá). Pasta inexistente,
        vazia ou qualquer erro -> set() (o chamador entende como 'precisa baixar')."""
        rel_dir = f"{self.dest_base}/{subpasta}".rstrip("/")
        try:
            r = requests.request("PROPFIND", self._dav(rel_dir),
                                 auth=(self.user, self.password),
                                 headers={"Depth": "1"}, timeout=60)
        except Exception:
            return set()
        if r.status_code >= 400:
            return set()
        nomes = set()
        for m in re.finditer(r"<[dD]:href>([^<]*)</[dD]:href>", r.text):
            href = m.group(1)
            if not href or href.endswith("/"):   # coleção (a própria pasta) — pula
                continue
            nomes.add(unquote(href.rsplit("/", 1)[-1]))
        return nomes
