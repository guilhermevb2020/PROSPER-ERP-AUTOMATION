# -*- coding: utf-8 -*-
"""
Constantes especificas do robo de EMISSAO (gera/imprime boletos no Smart).

Diferenca chave do envio:
- Endpoint Via=1 (boleto) em vez de Via=2 (cobranca/email).
- Grupos:
  * CONVENCIONAL = bancos nomeados (BB, BB Ativos, etc.) — em nome da
    SECURITIZADORA (ImprimirBoletoEmNome=f), classes P (Padrao) e T (Tranche).
  * OCULTO = contas comecando com 'mp ' — em nome do CEDENTE
    (ImprimirBoletoEmNome=c), classes P, T, E, B, BG, CL, I.
- modalidadeS=G (Todas) — emissao varre tudo. O envio filtra C (Convencional).
- POST de print com boleto=1, carne=0, NumEmail=0, imprimirMultiplos=0.

URLs base + credenciais reaproveitam _config.py.
"""

from __future__ import annotations

import os
from urllib.parse import urljoin

from src.processors.web.boletos import _config as cfg


# --------------------------------------------------------------------------- #
# URLs (diferente do envio — emissao usa Via=1)
# --------------------------------------------------------------------------- #
URL_FORM_HTTP = "https://wvw.smartsecurities.com.br/smart/financeiro/impriboleto.php?Via=1"
URL_LISTA_HTTP = "https://wvw.smartsecurities.com.br/smart/financeiro/listatitulosboletos.php"
URL_PRINT_HTTP = "https://wvw.smartsecurities.com.br/smart/financeiro/cobranca/printcobrancapdf.php"

# --------------------------------------------------------------------------- #
# Grupos de emissao
# --------------------------------------------------------------------------- #
GRUPO_CONVENCIONAL = "convencional"
GRUPO_OCULTO = "oculto"

# CONVENCIONAL = SECURITIZADORA (em nome da Prosper), classes Padrao + Tranche
# OCULTO       = CEDENTE (em nome do cedente), classes especiais
CONFIG_GRUPO: dict[str, dict] = {
    GRUPO_CONVENCIONAL: {
        "radio": "f",                       # ImprimirBoletoEmNome=f (Securitizadora)
        # P=Padrao, T=Tranche, CL=Op.Clean. CL incluida 2026-07-23: o ENVIO convencional
        # ja lista CL (CLASSES_PADRAO=P;T;CL em _config.py), entao um titulo CL em conta
        # convencional era ENVIAVEL mas nunca EMITIDO (assimetria). Alinha emissao<->envio.
        "classes": ["P", "T", "CL"],
    },
    GRUPO_OCULTO: {
        "radio": "c",                       # ImprimirBoletoEmNome=c (Cedente)
        "classes": ["P", "T", "E", "B", "BG", "CL", "I"],
        # E=Boleto especial, B=Esp.+Tranche, BG=Boleto garantido,
        # CL=Op.Clean, I=Intercompany
        # P=Padrao, T=Tranche incluidas 2026-07-31, MESMA assimetria do CL acima:
        # o ENVIO oculto ja lista P e T (CLASSES_MP=P;T;E;B;I;BG;CL em _config.py),
        # entao um titulo P numa conta 'mp ' era ENVIAVEL mas nunca EMITIDO. Medido
        # no dia: 21 titulos P + 2 CE em aberto sem `nosso_numero`, 13 deles em 6
        # contas onde a emissao RODOU no mesmo dia e emitiu os E ao lado.
        # Quem manda no nome do boleto e a CONTA (radio=c, cedente), nao a classe —
        # a classe so decide elegibilidade. Confirmado com a Gerencia em 31/07/2026.
        # CUIDADO: comissaria (C) fica de FORA de proposito — nao emite boleto nem
        # entra em remessa.
    },
}

# Conta cujo label comeca com 'mp ' (case-insensitive) eh OCULTA
PREFIXO_OCULTO = "mp "

# Modalidade no POST de listagem: G = Todas (emissao precisa varrer tudo)
MODALIDADE_EMISSAO = "G"

# Campos especificos do POST de print (impressao de boleto)
POST_PRINT_OVERRIDES = {
    "boleto": "1",
    "carne": "0",
    "NumEmail": "0",
    "imprimirMultiplos": "0",
}

# --------------------------------------------------------------------------- #
# Flags de seguranca (defaults SEGUROS)
# --------------------------------------------------------------------------- #
# DRY_RUN: True = lista pendentes e PARA antes do POST de print.
DRY_RUN: bool = os.environ.get("DRY_RUN_EMISSAO", "true").strip().lower() in ("1", "true", "sim")
# SCAN:   alias mais explicito; sempre True nao emite (read-only).
SCAN: bool = os.environ.get("SCAN_EMISSAO", "true").strip().lower() in ("1", "true", "sim")

# --------------------------------------------------------------------------- #
# Pacing / robustez
# --------------------------------------------------------------------------- #
# Numero de passadas por conta. Padrao = 2 (1a emite, 2a verifica se sumiu).
PASSADAS: int = int(os.environ.get("PASSADAS", "2"))
# Pausa entre contas (s) — anti-rate-limit do Smart.
DELAY_ENTRE_CONTAS: int = int(os.environ.get("DELAY_ENTRE_CONTAS_EMISSAO", "3"))
# Pausa entre passadas da mesma conta (s).
DELAY_ENTRE_PASSADAS: int = int(os.environ.get("DELAY_ENTRE_PASSADAS", "2"))
# Trava de seguranca — aborta se mais que TETO_CONTAS contas seriam emitidas.
TETO_CONTAS: int = int(os.environ.get("TETO_CONTAS_EMISSAO", "70"))

# --------------------------------------------------------------------------- #
# Filtros operacionais
# --------------------------------------------------------------------------- #
# Restringe a 1 conta especifica (value do dropdown)
SO_CONTA_ID: str = os.environ.get("SO_CONTA_ID", "").strip()
# Restringe ao grupo: 'convencional' | 'oculto' | '' (todos)
SO_GRUPO: str = os.environ.get("SO_GRUPO", "").strip().lower()
# Pula contas com este label exato (CSV)
CONTAS_IGNORAR: list[str] = [
    c.strip().lower() for c in os.environ.get("CONTAS_IGNORAR_EMISSAO", "").split(";") if c.strip()
]

# Reaproveita placeholders do envio (ignorar 'Selecione a conta' e 'Titulos sem conta')
CONTAS_PLACEHOLDER = cfg.CONTAS_PLACEHOLDER

# --------------------------------------------------------------------------- #
# Header padrao do POST
# --------------------------------------------------------------------------- #
HDR_FORM = {
    "Content-Type": "application/x-www-form-urlencoded",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": URL_FORM_HTTP,
}


def classificar_conta(nome_conta: str) -> str:
    """Retorna 'oculto' se label comeca com 'mp ', caso contrario 'convencional'."""
    return GRUPO_OCULTO if nome_conta.strip().lower().startswith(PREFIXO_OCULTO) else GRUPO_CONVENCIONAL
