#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes do `scripts/sandbox/pagamento.py` — a Fase 0 rodando no host.

POR QUE ESTES TESTES EXISTEM
----------------------------
O sandbox existe para rodar um robo contra o Smart REAL antes de ele ir para o
cron. Mas o caminho ate o `trabalho()` tem duas armadilhas que nao aparecem em
leitura de codigo, e as duas foram MEDIDAS em 21/08/2026:

1. `pagamento_config` resolve os caminhos NO IMPORT, e o default e `/app/...`.
   No host isso e `PermissionError: '/app'`. Quem importar `descobrir` antes de
   publicar as envs `_PAG` quebra — e quebra tarde, ja com o Chrome de pe e um
   CapSolver gasto. O `publicar_env_do_host()` existe para isso, e a ORDEM e a
   parte que se erra.
2. Deslogado, o Smart responde **HTTP 200 com 93 bytes** de redirect para o
   `expira.php`. Medido ao vivo, do host, sem credencial:

       200      93 bytes  .../financeiro/remessaocorrencia.php
       <script>top.location.href='.../smart/php/expira.php';</script>

   E o corpo REAL que esta em `CORPO_EXPIRA` aqui embaixo. A descoberta tem de
   tratar isso como "nao estou logado", nunca como "a tela nao existe" — senao a
   Fase 0 conclui que a arvore de pagamento nao existe quando o que houve foi
   sessao morta ou falta de permissao.

O QUE ELES NAO FAZEM
--------------------
Nao falam com o Smart e nao logam. O `ctx` e um dublê que devolve o que o Smart
devolveria. Login de verdade custa CapSolver e uma sessao a mais da conta
compartilhada — isso e passo supervisionado, nao teste automatico.

AMBIENTE
--------
Precisa de `playwright` importavel (o `descobrir.py` o importa no topo), entao
roda sob `.venv-sandbox`:

    PYTHONPATH=$PWD .venv-sandbox/bin/pytest tests/unit/test_pagamento_sandbox.py

Sem playwright, o modulo inteiro e PULADO em vez de falhar.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

pytest.importorskip("playwright",
                    reason="descobrir.py importa playwright; rode sob .venv-sandbox")

RAIZ = Path(__file__).resolve().parents[2]
for caminho in (RAIZ, RAIZ / "src" / "processors" / "web" / "robo_pagamento"):
    if str(caminho) not in sys.path:
        sys.path.insert(0, str(caminho))

from scripts.sandbox import pagamento  # noqa: E402

SMART = "https://wvw.smartsecurities.com.br/smart"

# O corpo REAL do Smart deslogado, capturado do host em 21/08/2026. 93 bytes,
# HTTP 200, sem 'erro', sem 'expirou' — "expira", sem o U.
CORPO_EXPIRA = (
    "<script>top.location.href='https://wvw.smartsecurities.com.br"
    "/smart/php/expira.php';</script>"
)

PAGINA_COM_MENU = f"""
<html><body>
<a href="/smart/pagamento/gerarremessapagto.php">Gerar Remessa</a>
<a href="/smart/pagamento/consultapagto.php">Consulta de Pagamento</a>
<a href="/smart/financeiro/downloadremessa.php">Download Remessa</a>
</body></html>
"""

PAGINA_DA_TELA = """
<html><body><form name="Form" method="POST" action="confirmarpagto.php">
  <input type="hidden" name="form_submit" value="1">
  <select name="contaCorrente"><option value="291" selected>mp cast</option></select>
</form></body></html>
"""


class _Resposta:
    def __init__(self, corpo: str, status: int = 200):
        self.status = status
        self._corpo = corpo.encode("iso-8859-1", errors="replace")

    def body(self):
        return self._corpo


class _Request:
    def __init__(self, paginas: dict, padrao: str):
        self.paginas, self.padrao, self.vistas = paginas, padrao, []

    def get(self, url, timeout=None):
        self.vistas.append(url)
        return _Resposta(self.paginas.get(url, self.padrao))


class CtxFalso:
    """Dublê do contexto do Playwright: so o `request.get` interessa aqui."""

    def __init__(self, paginas=None, padrao=""):
        self.request = _Request(paginas or {}, padrao)


class Args:
    """O Namespace que `descobrir.executar` espera."""

    def __init__(self, **kw):
        self.links = kw.get("links")
        self.url = kw.get("url")
        self.seguir = kw.get("seguir", False)
        self.semente = kw.get("semente", f"{SMART}/financeiro/remessaocorrencia.php")


@pytest.fixture(autouse=True)
def pastas_no_tmp(tmp_path, monkeypatch):
    """Redireciona as pastas do robo para o tmp — nada escreve em data/."""
    for chave, sub in (("USER_DATA_DIR_PAG", "perfil"), ("PASTA_SAIDA_PAG", "saida"),
                       ("ARQ_CONTROLE_PAG", "controle.csv"), ("DEBUG_DIR_PAG", "debug")):
        monkeypatch.setenv(chave, str(tmp_path / sub))
    monkeypatch.setenv("PAGAMENTO_ENV_FILE", "/dev/null")
    # os dois resolvem caminho no import — recarrega com o tmp ja publicado
    import pagamento_config
    importlib.reload(pagamento_config)
    import descobrir
    importlib.reload(descobrir)
    return tmp_path


# --------------------------------------------------------------------------- #
# 1. a ordem que evita o PermissionError: '/app'
# --------------------------------------------------------------------------- #
def test_publicar_env_aponta_tudo_para_o_host(monkeypatch):
    for chave in ("USER_DATA_DIR_PAG", "PASTA_SAIDA_PAG", "ARQ_CONTROLE_PAG",
                  "DEBUG_DIR_PAG"):
        monkeypatch.delenv(chave, raising=False)
    pagamento.publicar_env_do_host(log=lambda _m: None)
    import os
    for chave in ("USER_DATA_DIR_PAG", "PASTA_SAIDA_PAG", "ARQ_CONTROLE_PAG",
                  "DEBUG_DIR_PAG"):
        assert not os.environ[chave].startswith("/app"), chave
        assert "data/sandbox/robo_pagamento" in os.environ[chave]


def test_publicar_env_nao_sobrescreve_o_que_veio_de_fora(monkeypatch):
    """`docker exec -e` e o teste tem de continuar mandando."""
    monkeypatch.setenv("DEBUG_DIR_PAG", "/tmp/meu-debug")
    pagamento.publicar_env_do_host(log=lambda _m: None)
    import os
    assert os.environ["DEBUG_DIR_PAG"] == "/tmp/meu-debug"


def test_ensure_dirs_do_robo_funciona_depois_de_publicar(pastas_no_tmp):
    """A prova de que o redirecionamento resolve o PermissionError medido."""
    import pagamento_config
    pagamento_config.ensure_dirs()
    assert (pastas_no_tmp / "debug").is_dir()


# --------------------------------------------------------------------------- #
# 2. sessao morta nao pode virar "a tela nao existe"
# --------------------------------------------------------------------------- #
def test_corpo_do_expira_e_lido_como_deslogado():
    """O corpo REAL de 93 bytes, capturado do host sem credencial."""
    from src.common.clients.smart_sessao import parece_deslogado
    assert parece_deslogado(CORPO_EXPIRA) is True
    assert len(CORPO_EXPIRA.encode("iso-8859-1")) == 93


def test_sessao_morta_nao_vira_tela_inexistente(capsys):
    import descobrir
    ctx = CtxFalso(padrao=CORPO_EXPIRA)
    r = pagamento.trabalho(ctx, Args(links="pagamento"), log=print)
    assert r["ok"] is False and r["codigo"] == descobrir.SAIU_NADA_ACHADO
    saida = capsys.readouterr().out
    assert "DESLOGADO" in saida, saida
    # e o aviso de permissao tem de aparecer, que e a outra causa do vazio
    assert "acesso" in saida.lower()


def test_corpo_vazio_tambem_e_deslogado(capsys):
    """Regra 3 do COMO_CRIAR_AUTOMACAO: 200 com 0 bytes = sessao caida."""
    ctx = CtxFalso(padrao="")
    r = pagamento.trabalho(ctx, Args(links="pagamento"), log=print)
    assert r["ok"] is False
    assert "DESLOGADO" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# 3. o caminho feliz — e o que ele NAO visita
# --------------------------------------------------------------------------- #
def test_lista_os_links_de_pagamento_sem_visitar_nenhum(capsys):
    semente = f"{SMART}/financeiro/remessaocorrencia.php"
    ctx = CtxFalso({semente: PAGINA_COM_MENU}, padrao=CORPO_EXPIRA)
    r = pagamento.trabalho(ctx, Args(links="pagamento", semente=semente), log=print)
    assert r["ok"] is True
    # visitou SO a semente: `--seguir` e opt-in (regra 4)
    assert ctx.request.vistas == [semente], ctx.request.vistas
    saida = capsys.readouterr().out
    assert "gerarremessapagto.php" in saida and "consultapagto.php" in saida
    assert "downloadremessa" not in saida       # nao casa com o termo


def test_seguir_visita_os_que_casaram(capsys):
    semente = f"{SMART}/financeiro/remessaocorrencia.php"
    tela = f"{SMART}/pagamento/gerarremessapagto.php"
    ctx = CtxFalso({semente: PAGINA_COM_MENU, tela: PAGINA_DA_TELA},
                   padrao=PAGINA_DA_TELA)
    r = pagamento.trabalho(ctx, Args(links="pagamento", seguir=True,
                                     semente=semente), log=print)
    assert r["ok"] is True and tela in ctx.request.vistas
    assert "MOLDE: FORM" in capsys.readouterr().out


def test_url_direta_relata_o_molde_e_salva_o_html(pastas_no_tmp, capsys):
    tela = f"{SMART}/pagamento/gerarremessapagto.php"
    ctx = CtxFalso({tela: PAGINA_DA_TELA}, padrao=CORPO_EXPIRA)
    r = pagamento.trabalho(ctx, Args(url=tela), log=print)
    assert r["ok"] is True
    saida = capsys.readouterr().out
    assert "MOLDE: FORM" in saida and "contaCorrente" in saida
    salvos = list((pastas_no_tmp / "debug").glob("*.html"))
    assert len(salvos) == 1, "o HTML cru e a evidencia da Fase 0"
    assert "confirmarpagto.php" in salvos[0].read_text(encoding="utf-8")


def test_url_direta_lista_os_vizinhos(capsys):
    """A tela analisada tem de mostrar os links DELA.

    Medido em 21/08/2026: a arvore de pagamento nao se chama "pagamento" — e
    `financeiro/pagtobmp/`. Sem os vizinhos no relatorio, achar a proxima tela
    custa um run inteiro, e cada run custa um CapSolver (a sessao do Smart nao
    sobrevive ao fechamento do Chrome).
    """
    tela = f"{SMART}/financeiro/pagtobmp/pagtobmppesquisa.php"
    pagina = (PAGINA_DA_TELA
              + '<a href="gerarremessapagtobmp.php">Gerar Remessa</a>')
    ctx = CtxFalso({tela: pagina}, padrao=CORPO_EXPIRA)
    r = pagamento.trabalho(ctx, Args(url=tela), log=print)
    assert r["ok"] is True
    saida = capsys.readouterr().out
    assert "LINKS nesta tela" in saida
    assert "gerarremessapagtobmp.php" in saida
    assert "Gerar Remessa" in saida
    # nao visitou o vizinho: relatar e ler, nao navegar
    assert ctx.request.vistas == [tela], ctx.request.vistas
