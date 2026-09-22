# -*- coding: utf-8 -*-
"""
carregar_remessas_historicas.py - carga historica das remessas de cobranca no banco.

POR QUE EXISTE (Fase 2 de docs/PLANO_CONTROLE_NO_BANCO.md, passo 4): o cancelamento olha
45 dias para tras e o banco so conhece as remessas registradas desde 22/09/2026. Para a
remessa de cobranca e o cancelamento lerem o controle do banco (CONTROLE_FONTE_REM=banco),
o que esta no controle_remessas.csv precisa existir em erp_automation.arquivo — com a
DATA de entao (registrado_em = baixado_em), senao a janela do cancelamento erra.

DE ONDE VEM O CONTEUDO: os .REM nao ficam no disco local; estao na arvore do Nextcloud
montada no container (/app/data/cnab_nextcloud/Remessas/<ano>/<MM-Mes>/<DD>/<Banco>/
<Empresa> - <arquivo>). O md5 do CSV e o do conteudo cru — confere-se antes de registrar.

O QUE FAZ, por linha do CSV dentro da janela: acha o arquivo pelo sufixo " - <arquivo>";
confere o md5; se o sha256 ja esta no banco, pula (idempotente); senao registra `arquivo`
(sentido gerado, conta_label = tipo, id_no_smart, md5, nome_no_disco, origem = carga
historica) com registrado_em = baixado_em, e os eventos `gerado` e `enviado` (resultado =
caminho no Nextcloud) com ocorrido_em = baixado_em. Em ENSAIO (padrao) so relata.

Uso:  python carregar_remessas_historicas.py [--dias 45] [--csv ...] [--arvore ...] [--pra-valer]
Exit: 0 tudo carregado (ou ja estava); 3 faltou arquivo ou md5 divergiu (lista no stdout);
1 sem banco em modo real.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

from src.common.clients import execucao_job  # noqa: E402

SAIU_OK = 0
SAIU_ERRO = 1
SAIU_INCOMPLETO = 3
TZ = ZoneInfo("America/Sao_Paulo")
JOB = "carregar_remessas_historicas"
CSV_PADRAO = "/app/data/robo_remessa/controle_remessas.csv"
ARVORE_PADRAO = "/app/data/cnab_nextcloud/Remessas"


@dataclass
class Resultado:
    registradas: list = field(default_factory=list)   # ids
    ja_estavam: list = field(default_factory=list)
    sem_arquivo: list = field(default_factory=list)   # (id, arquivo)
    md5_diverge: list = field(default_factory=list)   # (id, arquivo)
    ensaio: bool = True

    @property
    def completa(self) -> bool:
        return not self.sem_arquivo and not self.md5_diverge


def ler_csv(caminho: str, desde: str) -> list[dict]:
    """Linhas do controle com baixado_em >= desde (AAAA-MM-DD), na ordem do arquivo."""
    if not os.path.exists(caminho):
        return []
    with open(caminho, encoding="utf-8", newline="") as fh:
        return [l for l in csv.DictReader(fh)
                if (l.get("baixado_em") or "") >= desde and (l.get("id") or "").strip()]


def indexar_arvore(arvore: str) -> dict[str, list[str]]:
    """{'<arquivo>.REM': [caminhos]} para todo .REM da arvore, pelo sufixo ' - <arquivo>'
    (ou o nome inteiro). Uma varredura so: ~800 arquivos."""
    indice: dict[str, list[str]] = {}
    for raiz, _, nomes in os.walk(arvore):
        for nome in nomes:
            if not nome.upper().endswith(".REM"):
                continue
            chave = nome.split(" - ", 1)[1] if " - " in nome else nome
            indice.setdefault(chave, []).append(os.path.join(raiz, nome))
    return indice


def quando(texto: str) -> datetime:
    """'2026-09-21 18:05:33' (hora local) -> datetime com fuso da casa."""
    return datetime.strptime(texto.strip()[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)


#: Nome local com sufixo `_dupHHMMSS`: mesmo nome do Smart, outro conteudo (outra conta).
#: No Nextcloud o arquivo sobe com o nome do SMART (ver remessa_cobranca/_nextcloud.py),
#: entao a busca e pelo nome sem o sufixo e o md5 escolhe entre os candidatos. Medido no
#: ensaio de 22/09/2026: 2 de 671 nao eram achadas so por isso.
_SUFIXO_DUP = re.compile(r"_dup\d{6}(?=\.REM$)", re.I)


def nome_do_smart(arquivo: str) -> str:
    return _SUFIXO_DUP.sub("", arquivo)


def carregar(linhas: list[dict], indice: dict, execucao, *, ensaio: bool, log=print) -> Resultado:
    r = Resultado(ensaio=ensaio)
    for l in linhas:
        fid, arquivo, md5_csv = l["id"].strip(), (l.get("arquivo") or "").strip(), (l.get("md5") or "").strip().lower()
        candidatos = indice.get(nome_do_smart(arquivo)) or []
        dados, caminho = None, None
        for c in candidatos:
            with open(c, "rb") as fh:
                d = fh.read()
            if hashlib.md5(d).hexdigest() == md5_csv:
                dados, caminho = d, c
                break
        if dados is None:
            if candidatos:
                r.md5_diverge.append((fid, arquivo))
                log(f"  id={fid} {arquivo}: {len(candidatos)} candidato(s), nenhum com o md5 do CSV")
            else:
                r.sem_arquivo.append((fid, arquivo))
                log(f"  id={fid} {arquivo}: NAO ACHADO na arvore")
            continue
        sha = hashlib.sha256(dados).hexdigest()
        if execucao_job.buscar_arquivo(execucao, "remessa_cobranca_cnab_400", sha256=sha, log=log):
            r.ja_estavam.append(fid)
            continue
        if ensaio:
            r.registradas.append(fid)
            log(f"  id={fid} {arquivo}: registraria (baixado_em {l.get('baixado_em')}, tipo {l.get('tipo')!r})")
            continue
        quando_ = quando(l.get("baixado_em") or "")
        arq = execucao_job.registrar_arquivo(
            execucao, "remessa_cobranca_cnab_400", "gerado", nome_arquivo=nome_do_smart(arquivo), conteudo=dados,
            qtd_registros=int(l["titulos"]) if (l.get("titulos") or "").strip().isdigit() else None,
            conta_label=l.get("tipo") or None, destino_caminho=caminho,
            detalhe={"md5": md5_csv, "id_no_smart": fid, "nome_no_disco": arquivo,
                     "origem": "carga historica de controle_remessas.csv (22/09/2026)"},
            registrado_em=quando_, log=log)
        if arq:
            execucao_job.registrar_evento_arquivo(execucao, arq, "gerado", ocorrido_em=quando_, log=log)
            execucao_job.registrar_evento_arquivo(execucao, arq, "enviado", resultado=caminho,
                                                  ocorrido_em=quando_, log=log)
            r.registradas.append(fid)
        else:
            r.sem_arquivo.append((fid, arquivo))
            log(f"  id={fid} {arquivo}: o banco nao registrou (veja os avisos da execucao)")
    return r


def montar_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Carga historica das remessas de cobranca em erp_automation.arquivo.")
    ap.add_argument("--dias", type=int, default=45, help="janela para tras a partir de hoje (padrao 45)")
    ap.add_argument("--csv", default=os.environ.get("ARQ_CONTROLE") or CSV_PADRAO)
    ap.add_argument("--arvore", default=os.environ.get("REMESSA_NC_ARVORE") or ARVORE_PADRAO)
    ap.add_argument("--pra-valer", action="store_true", help="registra de verdade (padrao: so relata)")
    return ap


def main(argv=None) -> int:
    args = montar_parser().parse_args(argv)
    ensaio = not args.pra_valer
    desde = (datetime.now(TZ) - timedelta(days=args.dias)).strftime("%Y-%m-%d")
    execucao = execucao_job.abrir_execucao("controle", JOB, flag_ensaio=ensaio, obrigatoria=not ensaio,
                                           detalhe={"csv": args.csv, "arvore": args.arvore, "desde": desde})
    codigo = SAIU_ERRO
    try:
        linhas = ler_csv(args.csv, desde)
        indice = indexar_arvore(args.arvore)
        print(f"CARGA HISTORICA DE REMESSAS — {'ENSAIO' if ensaio else '*** PRA VALER ***'} | "
              f"{len(linhas)} linha(s) do CSV desde {desde} | {sum(len(v) for v in indice.values())} .REM na arvore")
        r = carregar(linhas, indice, execucao, ensaio=ensaio)
        print(f"RESUMO: {'registraria' if ensaio else 'registradas'}={len(r.registradas)} | "
              f"ja no banco={len(r.ja_estavam)} | sem arquivo={len(r.sem_arquivo)} | md5 diverge={len(r.md5_diverge)}")
        codigo = SAIU_OK if r.completa else SAIU_INCOMPLETO
        return codigo
    finally:
        execucao_job.fechar_execucao(execucao, "sucesso" if codigo == SAIU_OK else "falha",
                                     codigo_saida=codigo)


if __name__ == "__main__":
    sys.exit(main())
