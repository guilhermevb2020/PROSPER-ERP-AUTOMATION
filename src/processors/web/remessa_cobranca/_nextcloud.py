# -*- coding: utf-8 -*-
"""Sobe os .REM baixados para o Nextcloud (FINANCEIRO/CNAB/Remessas).

WRAPPER FINO sobre o uploader COMPARTILHADO
(`src.common.clients.nextcloud_webdav.NextcloudWebDAV`) — toda a mecanica de
WebDAV vive la (dedup com doc2you e robo_credito). O que e PROPRIO deste modulo e
a CONVENCAO DE CAMINHO, e ela nao foi inventada aqui: espelha, campo a campo, a
que o `organizar_remessas` (process-automation) ja usa em
`FINANCEIRO/CNAB/Retornos` desde 13/08/2026:

    <base>/<ano>/<MM-Mes>/<DD>/<Banco>/<Empresa> - <arquivo>

    FINANCEIRO/CNAB/Remessas/2026/08-Agosto/17/MoneyPlus/TIGRAO COMERCIO DE MAT - CB17080001098.REM

O eixo e a DATA e nao o banco — a pergunta que se faz abrindo a pasta e "saiu
tudo hoje?", e com o banco no primeiro nivel seria preciso abrir cada um para
responder. Foi a mesma decisao tomada la, em 13/08.

PORQUE OS CAMPOS SAO LIDOS DO PROPRIO ARQUIVO
---------------------------------------------
`.REM` e `.RET` compartilham o header do CNAB-400. Medido em 17/08/2026, num
arquivo de cada, as posicoes batem:

    47-76   empresa/cedente   python h[46:76]   'TIGRAO COMERCIO DE MATERIAL E '
    77-79   banco (COMPE)     python h[76:79]   '274'
    95-100  data de geracao   python h[94:100]  '170826' (DDMMAA)

A data sai do ARQUIVO, nunca do relogio: remessa rebaixada dias depois cai na
pasta do dia em que foi GERADA, e nao na de hoje — senao o mesmo arquivo teria
dois lugares possiveis conforme a hora do download.

⚠️ Falha de upload NAO perde arquivo: quem chama grava no disco primeiro e so
depois sobe. O `.REM` local e o `controle_remessas.csv` continuam sendo a fonte
de verdade da idempotencia.
"""
import os
import re
from datetime import date

from src.common.clients.nextcloud_webdav import NextcloudWebDAV

_NC = NextcloudWebDAV(
    dest_base=os.getenv("REMESSA_NC_DEST", "FINANCEIRO/CNAB/Remessas"),
    cred_env=os.getenv("REMESSA_NC_ENV", "/app/config/nextcloud.env"),
)

DEST_BASE = _NC.dest_base

# COMPE -> nome de pasta. Mesma tabela do `organizar_remessas` (config.yaml
# `bancos_nomes`); COMPE desconhecido vira "Banco <compe>" em vez de derrubar a
# subida — arquivo em pasta com nome feio e recuperavel, arquivo nao enviado nao.
BANCOS = {
    "001": "Banco do Brasil",
    "274": "MoneyPlus",
    "237": "Bradesco",
    "756": "Sicoob",
}

_MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

# Tudo que nao pode ir para nome de arquivo/pasta (inclui os que o WebDAV e o
# Windows recusam). Mesma lista do classificador de la.
_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def disponivel() -> bool:
    """So True se ha senha configurada — senao nem tenta e diz por que."""
    return _NC.disponivel()


def _sanitizar(nome: str, maxlen: int = 60) -> str:
    limpo = _INVALIDOS.sub(" ", (nome or "").strip())
    limpo = re.sub(r"\s+", " ", limpo).strip(" .")
    return limpo[:maxlen].strip(" .") or "SEM_NOME"


def _pasta_mes(d: date) -> str:
    return f"{d.month:02d}-{_MESES[d.month - 1]}"


def _data_ddmmaa(bruto: str):
    """'170826' -> date(2026, 8, 17). None se ilegivel."""
    bruto = (bruto or "").strip()
    if len(bruto) != 6 or not bruto.isdigit():
        return None
    try:
        return date(2000 + int(bruto[4:6]), int(bruto[2:4]), int(bruto[0:2]))
    except ValueError:
        return None


def ler_cabecalho(dados: bytes) -> dict:
    """Empresa, banco e data de geracao do header do .REM.

    Devolve sempre um dict (nunca levanta): arquivo estranho vira 'SEM-DATA' e
    'Banco <compe>', que e visivel na pasta e pede olho humano, em vez de
    impedir o envio.
    """
    try:
        h = dados[:400].decode("latin-1", errors="replace")
    except Exception:
        h = ""
    return {
        "empresa": h[46:76].strip(),
        "compe": h[76:79].strip(),
        "data": _data_ddmmaa(h[94:100]),
    }


def caminho(dados: bytes, nome_arquivo: str):
    """(subpasta, nome_final) para este .REM, pela convencao de `CNAB/Retornos`."""
    cab = ler_cabecalho(dados)
    d = cab["data"]
    ano = f"{d:%Y}" if d else "SEM-DATA"
    mes = _pasta_mes(d) if d else "SEM-DATA"
    dia = f"{d:%d}" if d else "SEM-DATA"
    banco = BANCOS.get(cab["compe"], f"Banco {cab['compe'] or '???'}")
    empresa = _sanitizar(cab["empresa"])
    return f"{ano}/{mes}/{dia}/{banco}", f"{empresa} - {nome_arquivo}"


def enviar(dados: bytes, nome_arquivo: str):
    """Sobe um .REM. Retorna (ok, caminho_relativo, detalhe).

    NUNCA levanta: o chamador ja tem o arquivo no disco, e uma falha de rede no
    Nextcloud nao pode derrubar a rodada de geracao.
    """
    if not disponivel():
        return False, "", "sem credencial do Nextcloud (config/nextcloud.env)"
    subpasta, nome_final = caminho(dados, nome_arquivo)
    alvo = f"{DEST_BASE}/{subpasta}/{nome_final}"
    try:
        status = _NC.enviar(dados, subpasta, nome_final)
    except Exception as e:
        return False, alvo, f"erro no upload: {e}"
    if status in (200, 201, 204):
        return True, alvo, f"HTTP {status}"
    return False, alvo, f"HTTP {status}"
