"""Entrega BB ao Smart com intenção durável e recibo antes de novos efeitos.

Uma tentativa iniciada nunca é repetida automaticamente. A resposta confirmada
é reutilizada; ausência de resposta ou resultado inconclusivo pede conciliação.
O CSV legado e a indicação por nome do Smart não substituem essa evidência.
"""

import fcntl
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import artefatos
try:
    from src.common.clients import execucao_job          # erp_005: intencao tambem no banco
except ImportError:                                      # fora do container/PYTHONPATH: so o recibo
    execucao_job = None
import bb_api
import retorno

SCHEMA = "prospere.retorno-bb-api.v1"


def _anterior(pasta, sha, conta):
    intencoes, resultados = {}, {}
    for caminho in sorted(pasta.rglob("*.json")):
        if caminho.is_symlink():
            raise ValueError("recibo BB não pode ser link simbólico")
        dado = json.loads(caminho.read_text(encoding="utf-8"))
        meta = dado.get("metadados", {})
        if (dado.get("schema") != SCHEMA or dado.get("sha256") != sha
                or meta.get("conta_bb_api") != conta
                or meta.get("etapa") not in ("intencao", "resultado")):
            raise ValueError("recibo BB diverge da identidade ou do contrato")
        tentativa = meta.get("tentativa")
        if not isinstance(tentativa, str) or str(UUID(tentativa)) != tentativa:
            raise ValueError("tentativa BB inválida")
        destino = intencoes if meta["etapa"] == "intencao" else resultados
        if tentativa in destino:
            raise ValueError("etapa BB repetida no controle")
        destino[tentativa] = dado
    if len(intencoes) > 1:
        raise ValueError("mais de uma intenção para o mesmo retorno BB")
    if any((r.get("processado") or r.get("passo_irreversivel_chamado")) and t not in intencoes
           for t, r in resultados.items()):
        raise ValueError("resultado BB sem intenção correspondente")
    if not intencoes:
        return None
    tentativa, intencao = next(iter(intencoes.items()))
    resposta = resultados.get(tentativa)
    if resposta and resposta.get("processado") is True:
        esperado = intencao.get("portao", {}).get("contadores_esperados", {})
        if (intencao.get("portao", {}).get("liberado") is not True
                or resposta.get("estado_final") != "processado_smart"
                or resposta.get("conta") != intencao.get("conta")
                or str(resposta.get("conta")) != str(conta)
                or resposta.get("portao") != intencao.get("portao")
                or not bb_api.avaliar_resultado(
                    resposta.get("resposta_processamento"), esperado,
                    intencao.get("portao", {}).get("documentos_liquidacao") or ())["comprovado"]):
            raise ValueError("recibo BB afirma sucesso sem prova correspondente")
        return {**resposta, "processado": False, "ja_processado": True,
                "passo_irreversivel_chamado": False, "estado_final": "ja_processado",
                "motivo": retorno.MOTIVO_JA_PROCESSADO, "reutilizado": True}
    return {**intencao, "processado": False, "ja_processado": False,
            "passo_irreversivel_chamado": True, "inconclusivo": True,
            "estado_final": "inconclusivo",
            "motivo": "tentativa BB já iniciada sem confirmação durável; não reenviar"}


def _registrar_intencao_no_banco(resultado, *, caminho, conta, tentativa, estrito):
    """A INTENCAO vai ao banco ANTES do recibo e do POST (`intencao_envio` do arquivo).

    Em modo real (estrito) vale a regra da casa: sem registro nao ha acao irreversivel —
    falha de banco levanta ErroDeRegistro, o recibo de intencao NAO e gravado e o POST
    nao acontece; a rodada marca o arquivo como pendente (exit 6) e a proxima tenta de
    novo, limpa. A ordem importa: recibo gravado + banco falhando deixaria o arquivo
    "inconclusivo para sempre" (o recibo e o que impede a repeticao). Em ensaio nao ha
    intencao (o retorno devolve antes). Fase 2 de docs/PLANO_CONTROLE_NO_BANCO.md,
    ligada em 22/09/2026 junto com CONTROLE_FONTE_RET=banco."""
    if execucao_job is None:
        if estrito:
            raise RuntimeError("cliente de execucao indisponivel: sem registro da intencao nao ha POST")
        return
    ex = execucao_job.atual()
    if ex is None:
        if estrito:
            raise execucao_job.ErroDeRegistro("sem execucao aberta: sem registro da intencao nao ha POST")
        return
    arq_id = execucao_job.registrar_arquivo(
        ex, "retorno_bb", "recebido", nome_arquivo=Path(caminho).name, caminho=str(caminho),
        qtd_registros=resultado.get("titulos"), conta_id=str(conta),
        detalhe={"md5": resultado.get("hash"), "nome_smart": resultado.get("nome_smart"),
                 "tentativa": tentativa})
    if not arq_id:
        if estrito:
            raise execucao_job.ErroDeRegistro("arquivo nao registrado no banco: sem intencao nao ha POST")
        return
    evento = execucao_job.registrar_evento_arquivo(
        ex, arq_id, "intencao_envio", estrito=estrito,
        detalhe={"tentativa": tentativa, "conta_bb_api": conta})
    if estrito and not evento:
        raise execucao_job.ErroDeRegistro("intencao_envio nao registrada: sem registro nao ha POST")


def processar(ctx, caminho, *, conta, pasta_recibos, dry_run=True):
    """Processa uma vez por SHA-256 e conta; a trava cobre leitura e gravação."""
    if type(conta) is not int or conta <= 0:
        raise ValueError("conta Smart BB inválida")
    arquivo = Path(caminho)
    if arquivo.is_symlink():
        raise ValueError("retorno BB não pode ser link simbólico")
    sha = hashlib.sha256(arquivo.read_bytes()).hexdigest()
    pasta = Path(pasta_recibos) / str(conta) / sha
    pasta.mkdir(parents=True, exist_ok=True)
    with (pasta / ".lock").open("a") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        anterior = _anterior(pasta, sha, conta)
        if anterior is not None:
            return anterior
        tentativa = str(uuid4())
        gravados = set()

        def registrar(etapa, resultado):
            if resultado.get("sha256") != sha:
                raise ValueError("arquivo BB mudou durante o processamento")
            if etapa == "intencao":
                # banco ANTES do recibo (ver _registrar_intencao_no_banco)
                _registrar_intencao_no_banco(resultado, caminho=arquivo, conta=conta,
                                             tentativa=tentativa, estrito=not dry_run)
            artefatos.gravar_recibo_atomico(
                pasta, resultado, schema=SCHEMA,
                metadados={"etapa": etapa, "tentativa": tentativa, "conta_bb_api": conta},
            )
            gravados.add(etapa)

        resultado = retorno.processar(ctx, caminho, dry_run=dry_run,
                                      conta_bb_api=conta, registrar_bb=registrar)
        if "resultado" not in gravados:
            registrar("resultado", resultado)
        return resultado
