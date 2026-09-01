"""Artefatos auditaveis da baixa por deposito, sem dependencias de navegador."""

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCHEMA_RECIBO = "prospere.baixa-deposito.v1"
CATEGORIAS = frozenset({"_PROCESSADOS", "_REJEITADOS", "_INCONCLUSIVOS"})
TZ_SP = ZoneInfo("America/Sao_Paulo")


def _sha256_arquivo(caminho):
    digest = hashlib.sha256()
    with open(caminho, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def categoria_do_resultado(resultado):
    """Destino seguro do arquivo, ou ``None`` quando deve ficar para retry."""
    if resultado.get("processado") and resultado.get("estado_final") == "processado_smart":
        return "_PROCESSADOS"
    if resultado.get("estado_final") == "ja_processado":
        return "_PROCESSADOS"
    if resultado.get("portao", {}).get("liberado") is False:
        return "_REJEITADOS"
    if resultado.get("passo_irreversivel_chamado"):
        return "_INCONCLUSIVOS"
    return None


def mover_sem_sobrescrever(caminho, pasta_raiz, categoria):
    """Move individualmente preservando qualquer arquivo homonimo existente."""
    if categoria not in CATEGORIAS:
        raise ValueError(f"categoria invalida: {categoria!r}")
    origem = Path(caminho)
    if not origem.is_file():
        raise FileNotFoundError(origem)

    destino_dir = Path(pasta_raiz) / categoria / datetime.now(TZ_SP).strftime("%Y-%m")
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / origem.name
    if destino.exists():
        digest = _sha256_arquivo(origem)[:16]
        instante = datetime.now(TZ_SP).strftime("%Y%m%dT%H%M%S%f")
        destino = destino_dir / f"{origem.stem}_{digest}_{instante}{origem.suffix}"

    # Hard-link + unlink: publicacao atomica e sem a semantica de sobrescrita
    # de `shutil.move`/`os.replace`. Origem e destino ficam no mesmo volume.
    os.link(origem, destino)
    origem.unlink()
    return str(destino)


def _conteudo_recibo(resultado):
    campos = (
        "arquivo", "nome_smart", "hash", "sha256", "conta", "titulos",
        "valor_total", "arquivo_deposito", "detalhes", "acoes", "fora_ok",
        "portao", "passo_irreversivel_chamado", "resposta_processamento",
        "confirmacao_smart", "ocorrencias", "criticas", "divergencias",
        "processado", "inconclusivo", "motivo", "estado_final",
        "destino_relativo",
    )
    recibo = {chave: resultado.get(chave) for chave in campos}
    recibo["schema"] = SCHEMA_RECIBO
    recibo["quando"] = datetime.now(TZ_SP).isoformat(timespec="seconds")
    return recibo


def gravar_recibo_atomico(pasta_resultados, resultado):
    """Grava um JSON por tentativa, completo ou invisivel; nunca sobrescreve."""
    destino_dir = Path(pasta_resultados) / datetime.now(TZ_SP).strftime("%Y-%m-%d")
    destino_dir.mkdir(parents=True, exist_ok=True)
    sha = str(resultado.get("sha256") or "semhash")[:16]
    base = Path(str(resultado.get("arquivo") or "arquivo")).stem
    instante = datetime.now(TZ_SP).strftime("%Y%m%dT%H%M%S%f")
    destino = destino_dir / f"{base}_{sha}_{instante}.json"
    dados = json.dumps(
        _conteudo_recibo(resultado), ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n"

    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{base}.", suffix=".tmp",
            dir=destino_dir, delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
            arquivo.write(dados)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.link(temporario, destino)
        temporario.unlink()
        temporario = None
        descritor = os.open(destino_dir, os.O_RDONLY)
        try:
            os.fsync(descritor)
        finally:
            os.close(descritor)
        return str(destino)
    finally:
        if temporario is not None:
            temporario.unlink(missing_ok=True)
