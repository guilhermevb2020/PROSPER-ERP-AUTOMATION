# -*- coding: utf-8 -*-
"""
test_remessa_registro_banco.py - o que a remessa de cobranca passa a registrar (erp_005).

Tres fatos que so existiam em JSON no disco: a remessa DESCARTADA (o .REM existe, o Smart
o gerou) vira `arquivo` + evento `descartado`; a remessa PERDIDA (download falhou, sem
conteudo) vai como anotacao da execucao; o CANCELAMENTO vira evento `cancelado` — achando
o arquivo pelo id do Smart, ou pelo .REM no disco quando a remessa e anterior ao registro,
ou anotando quando nao ha nenhum dos dois. O cliente e um duble que captura as chamadas.

AMBIENTE: importa `gerar_remessa_cobranca` de verdade (playwright, `.venv-sandbox`); os
caminhos de `remessa_config` apontam para uma pasta temporaria via ambiente.
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="remessa_registro_"))
for var, sub in (("ARQ_CONTROLE", "controle.csv"), ("PASTA_REMESSAS", "remessas"),
                 ("USER_DATA_DIR_REM", "perfil"), ("DEBUG_DIR_REM", "debug"),
                 ("ARQ_EXCLUSOES_REM", "exclusoes.json"), ("PASTA_FALHAS_REM", "falhas"),
                 ("ARQ_REMESSAS_GERADAS_REM", "remessas_geradas.json")):
    os.environ.setdefault(var, str(_TMP / sub))

RAIZ = Path(__file__).resolve().parents[2]
ROBO = RAIZ / "src/processors/web/remessa_cobranca"

#: Modulos de nome curto que existem em MAIS de um job (remessa_cobranca e
#: remessa_pagamento tem `gerar`, `_nextcloud`, `_sessao`, `login`...). Importar o robo
#: aqui e deixa-los em sys.modules faria `test_gerar_remessa_pagamento` recarregar os
#: errados (medido em 22/09/2026: 11 falhas so pela ordem de coleta). O import e isolado:
#: o que havia volta, o que este modulo trouxe sai — o robo guarda suas referencias.
_COLIDEM = ("gerar", "_nextcloud", "_sessao", "login", "cancelar", "falhas", "exclusoes", "analise")


def _importar_isolado():
    import importlib
    havia = {k: sys.modules.pop(k) for k in _COLIDEM if k in sys.modules}
    sys.path.insert(0, str(ROBO))
    try:
        return importlib.import_module("gerar_remessa_cobranca")
    finally:
        sys.path.remove(str(ROBO))
        for k in _COLIDEM:
            sys.modules.pop(k, None)
        sys.modules.update(havia)


robo = _importar_isolado()


class _Cliente:
    """Duble do execucao_job: guarda cada chamada; `existe` e o que buscar_arquivo acha."""
    def __init__(self, existe=None):
        self.chamadas = []
        self.existe = existe
        self.proximo = 500

    def registrar_arquivo(self, ex, tipo, sentido, **kw):
        self.chamadas.append(("arquivo", tipo, sentido, kw)); self.proximo += 1; return self.proximo

    def registrar_evento_arquivo(self, ex, arq_id, tipo, **kw):
        self.chamadas.append(("evento", arq_id, tipo, kw)); return 900

    def buscar_arquivo(self, ex, tipo, **kw):
        self.chamadas.append(("busca", tipo, kw)); return self.existe

    def anotar(self, ex, chave, valor):
        self.chamadas.append(("anotar", chave, valor))


@pytest.fixture
def cliente(monkeypatch):
    c = _Cliente()
    monkeypatch.setattr(robo, "execucao_job", c)
    return c


def test_descarte_vira_arquivo_gerado_com_evento_descartado(cliente):
    dados = b"0" * 400 + b"\r\n" + b"1" * 401 + b"\r\n"
    reg = {"culpados": [{"documento": "7021-001", "bytes": 401, "motivo": "linha com 401 bytes"}]}
    arq = robo._registrar_descarte("EX", 26381, {"conta": 404, "titulos_grade": []}, "mp prospere",
                                   "CB2209000010.REM", dados, "linha com 401 bytes", reg, lambda m: None)
    assert arq == 501
    (_, tipo, sentido, kw), (_, arq_id, evento, ekw) = cliente.chamadas
    assert (tipo, sentido) == ("remessa_cobranca_cnab_400", "gerado")
    assert kw["nome_arquivo"] == "CB2209000010.REM" and kw["conteudo"] == dados
    assert kw["conta_id"] == "404" and kw["conta_label"] == "mp prospere"
    assert kw["detalhe"]["md5"] == hashlib.md5(dados).hexdigest()
    assert kw["detalhe"]["id_no_smart"] == 26381
    assert kw["detalhe"]["culpados"] == reg["culpados"]
    assert (arq_id, evento, ekw["resultado"]) == (501, "descartado", "linha com 401 bytes")


def test_sem_execucao_o_descarte_nao_registra_nada(cliente):
    assert robo._registrar_descarte(None, 1, {}, "x", "a.REM", b"", "m", None, lambda m: None) is None
    assert cliente.chamadas == []


def test_cancelamento_de_remessa_registrada_vira_evento_cancelado(cliente):
    cliente.existe = 77
    assert robo._registrar_cancelamento("EX", 26381, "CB2209000010.REM", 404, "sumiu da grade", lambda m: None) == 900
    (_, tipo, bkw), (_, arq_id, evento, ekw) = cliente.chamadas
    assert (tipo, bkw["id_no_smart"]) == ("remessa_cobranca_cnab_400", "26381")
    assert (arq_id, evento, ekw["resultado"], ekw["detalhe"]) == (77, "cancelado", "sumiu da grade", {"conta": 404})


def test_cancelamento_de_remessa_anterior_registra_pelo_rem_no_disco(cliente, monkeypatch, tmp_path):
    monkeypatch.setattr(robo.cfg, "PASTA_REMESSAS", str(tmp_path))
    dados = b"2" * 400 + b"\r\n"
    (tmp_path / "CB2109000001.REM").write_bytes(dados)
    assert robo._registrar_cancelamento("EX", 26300, "CB2109000001.REM", 291, "sumiu da grade", lambda m: None) == 900
    tipos = [c[0] for c in cliente.chamadas]
    assert tipos == ["busca", "arquivo", "evento"]
    kw = cliente.chamadas[1][3]
    assert kw["conteudo"] == dados and kw["detalhe"]["id_no_smart"] == "26300"
    assert "anterior ao registro" in kw["detalhe"]["origem"]
    assert cliente.chamadas[2][1] == 501 and cliente.chamadas[2][2] == "cancelado"


def test_cancelamento_sem_arquivo_em_lugar_nenhum_e_anotado(cliente, monkeypatch, tmp_path):
    monkeypatch.setattr(robo.cfg, "PASTA_REMESSAS", str(tmp_path))
    assert robo._registrar_cancelamento("EX", 26200, "CB2008000001.REM", 291, "sumiu da grade", lambda m: None) is None
    assert cliente.chamadas[-1] == ("anotar", "cancelamentos_sem_arquivo",
                                    {"id": 26200, "arquivo": "CB2008000001.REM", "conta": 291, "como": "sumiu da grade"})


def test_remessa_perdida_e_anotada_na_execucao(cliente, monkeypatch, tmp_path):
    """`processar()` com o download falhando: falhas/<id>.json continua (vigia) e a
    execucao ganha a anotacao `remessas_perdidas` — sem conteudo nao ha `arquivo`."""
    # outro teste da suite recarrega remessa_config sem o ambiente: a pasta volta a /app
    monkeypatch.setattr(robo.cfg, "PASTA_REMESSAS", str(tmp_path))
    monkeypatch.setattr(robo, "ler_controle", lambda: {})
    monkeypatch.setattr(robo, "baixar_id", lambda ctx, fid: (None, None))
    registros = []
    monkeypatch.setattr(robo.falhas, "registrar", lambda *a, **k: registros.append((a, k)) or {})
    itens = [{"id": 26381, "rotulo": "mp prospere", "conta": 404, "titulos_grade": [{"documento": "1"}] * 60}]
    robo.processar("CTX", itens, execucao="EX")
    assert len(registros) == 1, "o JSON de falhas continua sendo escrito"
    assert ("anotar", "remessas_perdidas", {"id": 26381, "conta": 404, "rotulo": "mp prospere",
                                             "motivo": "download do Smart falhou", "qtd_titulos": 60}) in cliente.chamadas
