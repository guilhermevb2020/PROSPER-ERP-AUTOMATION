"""Origem durável das remessas novas do BB, antes de qualquer envio bancário.

Usa o gerador e o download existentes. A pasta é uma caixa de saída privada,
compartilhada com process-automation, não uma varredura do acervo de remessas.
Só publica pronta.json depois de guardar a resposta da própria geração, os
bytes originais e a entrega ao Nextcloud. Cada evidência é imutável.

Sem resposta da geração, uma nova rodada para nessa intenção: a listagem de
arquivos antigos não comprova que foram gerados por esta chamada. Com resposta
salva, retoma apenas o download/upload dos IDs recebidos, sem gerar novamente.
O consumidor ainda precisa validar/traduzir o CNAB integral e reservar no banco.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs
from uuid import uuid4
from zoneinfo import ZoneInfo


class OrigemBBInconclusiva(RuntimeError):
    """Evidência ausente ou divergente; não gerar nem enviar automaticamente."""


def _publicar(path: Path, dados: bytes) -> None:
    """Publica evidência completa, fsync e sem sobrescrever outra versão."""
    fd, temporario = tempfile.mkstemp(prefix=".gravando-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as arquivo:
            arquivo.write(dados)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        try:
            os.link(temporario, path)
        except FileExistsError:
            if path.read_bytes() != dados:
                raise OrigemBBInconclusiva(f"evidência divergente: {path.name}") from None
        diretorio = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(diretorio)
        finally:
            os.close(diretorio)
    finally:
        os.unlink(temporario)


def _json(path: Path, dados: dict) -> None:
    _publicar(path, json.dumps(dados, ensure_ascii=False, sort_keys=True,
                              indent=2).encode("utf-8"))


def _ler(path: Path) -> dict:
    dados = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(dados, dict):
        raise OrigemBBInconclusiva(f"evidência inválida: {path.name}")
    return dados


def _ids(resultado: dict) -> list[tuple[str, int]]:
    pares = resultado.get("ids")
    if resultado.get("ok") is not True or resultado.get("enviado") is not True or not pares:
        raise OrigemBBInconclusiva("geração sem confirmação dos IDs; conferir no Smart")
    vistos = set()
    for tipo, fid in pares:
        if not isinstance(tipo, str) or type(fid) is not int or fid <= 0 or fid in vistos:
            raise OrigemBBInconclusiva("IDs da geração inválidos ou repetidos")
        vistos.add(fid)
    return pares


def _entregar(robo, ctx, pasta: Path, intencao: dict) -> dict:
    resposta = pasta / "resultado.json"
    if not resposta.exists():
        raise OrigemBBInconclusiva("intenção sem resposta salva; não repetir a geração")
    resultado = _ler(resposta)
    pares = (_ids(resultado) if resultado.get("ids") else
             _download_direto(robo, ctx, pasta, intencao, resultado))
    arquivos = []
    # Um erro parcial continua visível. Os IDs confirmados podem ser baixados,
    # mas não liberamos o lote para envio até esclarecer o resultado completo.
    for tipo, fid in pares:
        metadados = pasta / f"{fid}.json"
        local = pasta / f"{fid}.REM"
        if metadados.exists():
            meta = _ler(metadados)
            dados = local.read_bytes()
            if hashlib.sha256(dados).hexdigest() != meta["sha256"]:
                raise OrigemBBInconclusiva("arquivo local mudou após o download")
            nome = meta["nome"]
        else:
            nome, dados = robo.baixar_id(ctx, fid)
            if dados is None:
                raise OrigemBBInconclusiva(f"download pendente do ID {fid}")
            if not nome or Path(nome).name != nome or not nome.upper().endswith(".REM"):
                raise OrigemBBInconclusiva("nome inválido no download Smart")
            valido, motivo, quantidade = robo.validar_cnab(dados)
            if not valido or quantidade <= 0:
                raise OrigemBBInconclusiva(f"download recusado: {motivo}")
            header = dados[:400].decode("latin-1")
            if header[76:79] != "001" or header[129:136] != intencao["convenio"]:
                raise OrigemBBInconclusiva("download não pertence ao banco/convênio solicitado")
            # Não supõe que arquivos de tipos diferentes tenham o mesmo
            # sequencial. O parser integral do consumidor validará cada arquivo.
            meta = {"id": fid, "tipo": tipo, "nome": nome,
                    "sha256": hashlib.sha256(dados).hexdigest(),
                    "bytes": len(dados), "titulos": quantidade}
            _publicar(local, dados)
            _json(metadados, meta)
        enviado, destino, detalhe = robo.nuvem.enviar(dados, nome)
        if not enviado:
            raise OrigemBBInconclusiva(f"entrega Nextcloud pendente: {detalhe}")
        arquivos.append({**meta, "local": local.name, "nextcloud": destino})
    if resultado.get("erros"):
        raise OrigemBBInconclusiva("Smart reportou erros parciais; arquivos preservados")
    manifesto = {"versao": 1, "origem": "geracao_smart_bb",
                 "intencao": intencao, "arquivos": arquivos}
    _json(pasta / "pronta.json", manifesto)
    return {"estado": "pronta", "geracao": pasta.name,
            "ids": [item["id"] for item in arquivos], "arquivos": len(arquivos)}


def _conferir_direto(robo, intencao, resultado, item, dados, *, legado):
    """Confere o download contra a resposta, o formulário e a listagem Smart."""
    if (resultado.get("enviado") is not True or resultado.get("ok") is not False
            or resultado.get("ids") != [] or resultado.get("erros") != []
            or resultado.get("corpo") != intencao["corpo"]):
        raise OrigemBBInconclusiva("resposta não comprova POST de download direto")
    if legado:
        prefixo = resultado.get("html", "").encode("latin-1")
        if ("resposta_http" in resultado or len(prefixo) != 1500
                or resultado.get("motivo") != "POST foi (status=200) mas nao li o resultado"
                or not dados.startswith(prefixo)):
            raise OrigemBBInconclusiva("prefixo legado não corresponde ao download")
    else:
        http = resultado.get("resposta_http", {})
        original = base64.b64decode(http.get("body_base64", ""), validate=True)
        if http.get("status") != 200 or original != dados:
            raise OrigemBBInconclusiva("download difere da resposta integral do POST")
    valido, motivo, quantidade = robo.validar_cnab(dados)
    if not valido or quantidade <= 0:
        raise OrigemBBInconclusiva(f"download direto inválido: {motivo}")
    linhas = dados.decode("latin-1").splitlines()
    iniciada = datetime.fromisoformat(intencao["iniciada_em"])
    data_lista = datetime.strptime(item["data"], "%d/%m/%Y %H:%M").replace(tzinfo=iniciada.tzinfo)
    if (iniciada.tzinfo is None or item.get("cc") != intencao["conta_smart"]
            or not iniciada.replace(second=0, microsecond=0) <= data_lista <= iniciada + timedelta(minutes=5)
            or linhas[0][94:100] != iniciada.strftime("%d%m%y")
            or linhas[0][76:79] != "001" or linhas[0][129:136] != intencao["convenio"]):
        raise OrigemBBInconclusiva("download fora da conta/data/convênio da geração")
    campos = parse_qs(intencao["corpo"])
    selecionados = sorted(v for k, vs in campos.items() if k.startswith("titulo") for v in vs)
    controles = sorted(str(int(l[48:63])) for l in linhas if l.startswith("7"))
    if legado and (not selecionados or intencao["resumo"].get("instrucoes")):
        raise OrigemBBInconclusiva("recuperação legada exige seleção explícita de todos os títulos")
    if selecionados and (selecionados != controles
                         or len(selecionados) != intencao["resumo"]["titulos_marcados"]):
        raise OrigemBBInconclusiva("download não contém exatamente os títulos selecionados")
    return quantidade


def _download_direto(robo, ctx, pasta, intencao, resultado, *, id_legado=None):
    """Relaciona bytes integrais a um único ID; prefixo exige recuperação explícita."""
    prova_path = pasta / "download_direto.json"
    if prova_path.exists():
        prova = _ler(prova_path)
        item = prova["listagem"]
        dados = (pasta / f"{item['id']}.REM").read_bytes()
        if (prova.get("versao") != 1 or prova.get("metodo") not in ("integral", "legado_conferido")
                or prova["sha256"] != hashlib.sha256(dados).hexdigest()):
            raise OrigemBBInconclusiva("prova de download direto divergente")
        _conferir_direto(robo, intencao, resultado, item, dados,
                        legado=prova["metodo"] == "legado_conferido")
        return [("download_direto", item["id"])]
    http = resultado.get("resposta_http", {})
    original = base64.b64decode(http.get("body_base64", ""), validate=True)
    if id_legado is None and (http.get("status") != 200 or not original.startswith(b"01REMESSA")):
        raise OrigemBBInconclusiva("geração sem confirmação dos IDs; conferir no Smart")
    if id_legado is not None and (type(id_legado) is not int or id_legado <= 0):
        raise OrigemBBInconclusiva("ID explícito inválido")
    dia = datetime.fromisoformat(intencao["iniciada_em"]).date().isoformat()
    candidatos = robo.listar_remessas(ctx, intencao["conta_smart"], dia, dia)
    encontrados = []
    for item in candidatos:
        if item.get("cc") != intencao["conta_smart"] or (id_legado is not None and item["id"] != id_legado):
            continue
        nome, dados = robo.baixar_id(ctx, item["id"])
        if dados is None:
            raise OrigemBBInconclusiva("download pendente ao relacionar resposta integral")
        if id_legado is None and dados != original:
            continue
        if nome != item["arquivo"] or Path(nome).name != nome or not nome.upper().endswith(".REM"):
            raise OrigemBBInconclusiva("nome do download diverge da listagem")
        quantidade = _conferir_direto(robo, intencao, resultado, item, dados, legado=id_legado is not None)
        encontrados.append((item, dados, quantidade))
    if len(encontrados) != 1:
        raise OrigemBBInconclusiva("resposta direta sem um único arquivo correspondente no Smart")
    item, dados, quantidade = encontrados[0]
    fid = item["id"]
    meta = {"id": fid, "tipo": "download_direto", "nome": item["arquivo"],
            "sha256": hashlib.sha256(dados).hexdigest(), "bytes": len(dados), "titulos": quantidade}
    _publicar(pasta / f"{fid}.REM", dados)
    _json(pasta / f"{fid}.json", meta)
    _json(prova_path, {"versao": 1, "metodo": "legado_conferido" if id_legado is not None else "integral",
                      "listagem": item, "sha256": meta["sha256"]})
    return [("download_direto", fid)]


def recuperar_download_direto(robo, ctx, *, pasta: Path, smart_id: int) -> dict:
    """Retoma um POST legado pelo ID conferido, sob a trava financeira do chamador.

    Não gera remessa. Preserva resultado.json original e registra a conferência
    em download_direto.json antes da entrega normal. Exige prefixo de 1500 bytes,
    mesma conta/data e o conjunto integral de títulos do formulário original.
    """
    with (pasta.parent / ".lock").open("a") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        intencao, resultado = _ler(pasta / "intencao.json"), _ler(pasta / "resultado.json")
        _download_direto(robo, ctx, pasta, intencao, resultado, id_legado=smart_id)
        return _entregar(robo, ctx, pasta, intencao)


def executar(robo, ctx, *, conta: str, carteira: str, convenio: str,
             ambiente: str, pasta: str, dry_run: bool = True) -> dict:
    """Gera e entrega uma remessa nova, ou retoma a intenção ainda não concluída.

    Args:
        robo: Processador robo_remessa existente (gerador, download e Nextcloud).
        ctx: Contexto Smart autenticado, sob a trava financeira comum.
        conta: ID exato da conta no Smart; nomes parciais não são aceitos.
        carteira: Carteira exata, sem fallback para outra carteira.
        convenio: Convênio BB autorizado com sete posições.
        ambiente: Ambiente bancário de destino; não altera o Smart autenticado.
        pasta: Caixa de saída persistente compartilhada com o consumidor.
        dry_run: Consulta o filtro sem criar intenção, gerar ou entregar arquivo.
    """
    if ambiente not in ("producao", "homologacao"):
        raise ValueError("ambiente BB inválido")
    for valor in (conta, carteira, convenio):
        if not valor.isascii() or not valor.isdigit() or int(valor) <= 0:
            raise ValueError("conta/carteira/convênio devem ser números positivos")
    if len(convenio) != 7:
        raise ValueError("convênio BB deve ter sete posições")
    escopo = {"ambiente": ambiente, "conta_smart": conta,
              "carteira": carteira, "convenio": convenio}
    raiz = Path(pasta).resolve() / ambiente / convenio / conta
    if dry_run:
        return _gerar(robo, ctx, raiz, escopo, True)
    raiz.mkdir(parents=True, exist_ok=True)
    # Trava a conta inteira: carteiras diferentes também não ultrapassam uma
    # geração inconclusiva. A trava financeira do wrapper protege a sessão.
    with (raiz / ".lock").open("a") as trava:
        fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for anterior in sorted(raiz.iterdir()):
            if not anterior.is_dir():
                continue
            if not (anterior / "intencao.json").exists():
                # Pasta criada, mas sem intenção, não executou HTTP. Não pode
                # conter uma resposta ou arquivo vindo de outra origem.
                if any(not p.name.startswith(".gravando-") for p in anterior.iterdir()):
                    raise OrigemBBInconclusiva("pasta de geração sem intenção")
                continue
            if not (anterior / "pronta.json").exists():
                intencao = _ler(anterior / "intencao.json")
                if any(intencao.get(k) != v for k, v in escopo.items()):
                    raise OrigemBBInconclusiva("geração anterior pendente em outro escopo")
                return _entregar(robo, ctx, anterior, intencao)
        return _gerar(robo, ctx, raiz, escopo, False)


def _gerar(robo, ctx, raiz: Path, escopo: dict, dry_run: bool) -> dict:
    pagina = robo.ger.filtrar(ctx, escopo["conta_smart"], escopo["carteira"])
    if pagina is None:
        raise OrigemBBInconclusiva("filtro Smart sem resposta útil")
    form = robo.ger.ler_form(pagina)
    resumo = form["resumo"]
    if (resumo.get("numBanco"), resumo.get("numConta"), resumo.get("carteira"),
        resumo.get("modalidadeS")) != ("001", escopo["conta_smart"], escopo["carteira"], "G"):
        raise OrigemBBInconclusiva("filtro Smart retornou outra conta/banco/carteira/modalidade")
    valido, motivo = robo.ger.validar(form)
    if not valido:
        return {"estado": "sem_remessa", "motivo": motivo, "resumo": resumo}
    if dry_run:
        return {"estado": "simulado", "resumo": resumo}
    geracao = str(uuid4())
    destino = raiz / geracao
    destino.mkdir()
    intencao = {**escopo, "geracao": geracao,
                "iniciada_em": datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(),
                "corpo": robo.ger.montar_post(form), "resumo": resumo}
    # Publicação e fsync da intenção precedem o único POST de geração.
    _json(destino / "intencao.json", intencao)
    # A raiz de conta/convênio também pode ter acabado de nascer. Persistir
    # apenas o arquivo não basta se o diretório pai sumir numa queda de energia.
    for pai in (raiz, *raiz.parents):
        diretorio = os.open(pai, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(diretorio)
        finally:
            os.close(diretorio)
    resultado = robo.ger.gerar(ctx, form, dry_run=False)
    _json(destino / "resultado.json", resultado)
    return _entregar(robo, ctx, destino, intencao)
