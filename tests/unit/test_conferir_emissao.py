#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes do conferidor de boletos emitidos.

A FIXTURE E UM BOLETO REAL. O texto abaixo saiu do PDF que motivou toda a
investigacao de 21/08/2026: Banco do Brasil, carteira 17 (carteira que so
existe nas contas BB), impresso em nome do CEDENTE — MOREIRA METALURGICA —
quando conta BB e grupo `convencional` e a regra manda SECURITIZADORA.

E por isso que o teste `test_o_caso_moreira_e_marcado_como_divergente` vale
mais que os outros: ele prova que, quando a emissao gravar os PDFs, um caso
como esse aparece sozinho no relatorio em vez de esperar um sacado reclamar.

Rodam no HOST, sem container e sem `pdftotext`: a extracao de texto e a unica
parte que chama processo externo, e os testes atacam as funcoes puras.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

from conferir_emissao import (  # noqa: E402
    avaliar,
    conferir_pasta,
    eh_securitizadora,
    extrair_campos,
)

# Texto real do boleto do caso MOREIRA (recortado no que importa).
BOLETO_MOREIRA = """001-9 Recibo do Pagador
Beneficiário
Vencimento Agência/Código do Beneficiário Espécie Moeda Quantidade Moeda
Valor documento (-) Desconto (+) Mora / Multa / Juros
(=) Valor cobrado Nosso número Número do documento
Pagador
Autenticação mecânica
MOREIRA METALURGICA INDUSTRIA E COMERCIO LTDA - 51.737.963/0001-03
Rua Martinho Vaz de Barros 47, Jd Pirajussara. São Paulo/SP
21/08/2026 0386-7/00091665-X R$
3.175,90
34527370000513133 15652-001
PLANTEC DISTRIBUIDORA DE PRODUTOS DE CNPJ: 09.262.527/0003-20
"""

# O mesmo boleto, como DEVERIA ter saido numa conta convencional.
BOLETO_SECURITIZADORA = BOLETO_MOREIRA.replace(
    "MOREIRA METALURGICA INDUSTRIA E COMERCIO LTDA - 51.737.963/0001-03",
    "PROSPER FIDC MULTISSETORIAL - 11.222.333/0001-44",
)


# --------------------------------------------------------------------------- #
# extracao
# --------------------------------------------------------------------------- #
def test_extrai_beneficiario_e_pagador_do_boleto_real():
    c = extrair_campos(BOLETO_MOREIRA)
    assert c["beneficiario"] == "MOREIRA METALURGICA INDUSTRIA E COMERCIO LTDA"
    assert c["beneficiario_cnpj"] == "51.737.963/0001-03"
    assert c["pagador"] == "PLANTEC DISTRIBUIDORA DE PRODUTOS DE"
    assert c["pagador_cnpj"] == "09.262.527/0003-20"
    assert c["nosso_numero"] == "34527370000513133"
    assert c["valor"] == "3.175,90"


def test_texto_vazio_nao_explode():
    c = extrair_campos("")
    assert c["beneficiario"] is None and c["pagador"] is None
    assert extrair_campos(None)["beneficiario"] is None


def test_nao_confunde_pagador_com_beneficiario():
    """O pagador traz 'CNPJ:'; o beneficiario, um dash antes do numero."""
    c = extrair_campos(BOLETO_MOREIRA)
    assert "PLANTEC" not in (c["beneficiario"] or "")


# --------------------------------------------------------------------------- #
# veredito
# --------------------------------------------------------------------------- #
def test_o_caso_moreira_e_marcado_como_divergente():
    """Conta BB (convencional) impressa em nome do cedente -> divergente."""
    beneficiario = extrair_campos(BOLETO_MOREIRA)["beneficiario"]
    situacao, motivo = avaliar(beneficiario, "convencional")
    assert situacao == "divergente"
    assert "MOREIRA" in motivo


def test_convencional_com_securitizadora_e_ok():
    beneficiario = extrair_campos(BOLETO_SECURITIZADORA)["beneficiario"]
    assert avaliar(beneficiario, "convencional")[0] == "ok"


def test_oculto_com_cedente_e_ok():
    """Numa conta 'mp ' o cedente no papel e o comportamento correto."""
    beneficiario = extrair_campos(BOLETO_MOREIRA)["beneficiario"]
    assert avaliar(beneficiario, "oculto")[0] == "ok"


def test_oculto_com_securitizadora_e_divergente():
    """O inverso tambem e defeito: operacao oculta nao pode expor a Prosper."""
    beneficiario = extrair_campos(BOLETO_SECURITIZADORA)["beneficiario"]
    situacao, _ = avaliar(beneficiario, "oculto")
    assert situacao == "divergente"


def test_sem_beneficiario_e_indeterminado_nao_ok():
    """Na duvida, nunca 'ok' — indeterminado pede olho humano."""
    assert avaliar(None, "convencional")[0] == "indeterminado"
    assert avaliar("", "oculto")[0] == "indeterminado"


def test_marcador_da_securitizadora_e_configuravel():
    assert eh_securitizadora("PROSPER FIDC MULTISSETORIAL") is True
    assert eh_securitizadora("MOREIRA METALURGICA") is False
    assert eh_securitizadora("FUNDO XPTO", marcadores=("XPTO",)) is True


# --------------------------------------------------------------------------- #
# a pasta inteira
# --------------------------------------------------------------------------- #
def _gravar(pasta: Path, base: str, manifesto: dict, pdf: bool = True):
    pasta.mkdir(parents=True, exist_ok=True)
    if pdf:
        (pasta / f"{base}.pdf").write_bytes(b"%PDF-1.4\n")
        manifesto["arquivo"] = str(pasta / f"{base}.pdf")
    (pasta / f"{base}.json").write_text(json.dumps(manifesto), encoding="utf-8")


def test_resposta_que_nao_era_pdf_vira_indeterminado(tmp_path):
    """HTML de erro com HTTP 200 nao pode passar por boleto conferido."""
    _gravar(tmp_path, "093105_290_convencional", {
        "conta_label": "Banco do Brasil", "grupo": "convencional",
        "radio_em_nome": "f", "ids_titulos": ["1"], "resposta_eh_pdf": False,
    }, pdf=False)
    linhas = conferir_pasta(str(tmp_path))
    assert len(linhas) == 1
    assert linhas[0]["situacao"] == "indeterminado"


def test_pasta_inexistente_devolve_vazio(tmp_path):
    assert conferir_pasta(str(tmp_path / "nao-existe")) == []


def test_manifesto_corrompido_e_ignorado_sem_derrubar(tmp_path):
    (tmp_path / "quebrado.json").write_text("{isto nao e json", encoding="utf-8")
    assert conferir_pasta(str(tmp_path)) == []
