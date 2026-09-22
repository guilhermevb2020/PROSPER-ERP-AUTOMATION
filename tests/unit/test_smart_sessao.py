"""Regressoes da validacao de sessao: nenhum navegador ou servico real."""
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common.clients import smart_sessao


EXPIRA = b"<script>top.location.href='/smart/php/expira.php';</script>"
TELA = b"<form>Pagamento BMP Money Plus</form>"


def resposta(corpo=TELA, status=200):
    return SimpleNamespace(status=status, body=lambda: corpo)


def contexto(*respostas):
    return SimpleNamespace(
        request=SimpleNamespace(get=Mock(side_effect=respostas)), close=Mock()
    )


@pytest.fixture
def cfg():
    return SimpleNamespace(
        EMAIL="teste@example.invalid", SENHA="placeholder-de-teste",
        URL_PING="https://smart.invalid/pagamentos",
        URL_LOGIN="https://smart.invalid/login", DISPLAY=":94",
    )


@pytest.fixture
def capsolver(monkeypatch):
    modulo = ModuleType("src.processors.web.boletos._sessao")
    modulo.login_automatico_capsolver = Mock(return_value=True)
    monkeypatch.setitem(sys.modules, modulo.__name__, modulo)
    for chave in ("BOLETO_EMAIL", "BOLETO_SENHA", "URL_SESSAO", "URL_LOGIN"):
        monkeypatch.setenv(chave, "teste")
    monkeypatch.setattr(smart_sessao.time, "sleep", lambda _: None)
    return modulo.login_automatico_capsolver


def test_timeout_apos_login_repete_ping_sem_repetir_login(cfg, capsolver):
    # Incidente 07/09: CapSolver confirma login e o GET seguinte leva >20 s.
    ctx = contexto(resposta(EXPIRA), TimeoutError(), resposta())
    assert smart_sessao.login(ctx, cfg, log=lambda _: None) is True
    capsolver.assert_called_once_with(ctx, timeout_total_s=300)
    assert ctx.request.get.call_count == 3


def test_timeout_inicial_nao_dispara_login_em_sessao_valida(cfg, capsolver):
    ctx = contexto(TimeoutError(), resposta())
    assert smart_sessao.login(ctx, cfg, log=lambda _: None) is True
    capsolver.assert_not_called()


def test_smart_indisponivel_antes_do_login_nao_gasta_capsolver(cfg, capsolver):
    ctx = contexto(*[TimeoutError() for _ in range(3)])
    with pytest.raises(smart_sessao.SmartIndisponivel):
        smart_sessao.login(ctx, cfg, log=lambda _: None)
    capsolver.assert_not_called()


def test_smart_indisponivel_apos_login_nao_e_sessao_expirada(cfg, capsolver):
    ctx = contexto(resposta(EXPIRA), *[TimeoutError() for _ in range(3)])
    with pytest.raises(smart_sessao.SmartIndisponivel):
        smart_sessao.login(ctx, cfg, log=lambda _: None)
    capsolver.assert_called_once()


def test_expiracao_explicita_apos_login_continua_recusada(cfg, capsolver):
    ctx = contexto(resposta(EXPIRA), resposta(EXPIRA))
    assert smart_sessao.login(ctx, cfg, log=lambda _: None) is False
    capsolver.assert_called_once()


def test_capsolver_recusado_nao_libera_sessao(cfg, capsolver):
    capsolver.return_value = False
    ctx = contexto(resposta(EXPIRA))
    assert smart_sessao.login(ctx, cfg, log=lambda _: None) is False


@pytest.mark.parametrize("status", [401, 403, 429, 500, 502, 503])
def test_http_de_erro_nao_e_sessao_valida(cfg, capsolver, status):
    ctx = contexto(*[resposta(b"Service unavailable", status) for _ in range(3)])
    assert smart_sessao.sessao_viva(ctx, cfg, log=lambda _: None) is None


def test_http_temporario_repete_e_recupera(cfg, capsolver):
    ctx = contexto(resposta(b"Service unavailable", 503), resposta())
    assert smart_sessao.sessao_viva(ctx, cfg, log=lambda _: None) == "ok"


def test_resposta_vazia_nao_dispara_login(cfg, capsolver):
    ctx = contexto(*[resposta(b" \n") for _ in range(3)])
    with pytest.raises(smart_sessao.SmartIndisponivel):
        smart_sessao.login(ctx, cfg, log=lambda _: None)
    capsolver.assert_not_called()


def test_diagnostico_nao_imprime_detalhes_sensiveis_da_excecao(cfg, capsolver):
    logs = []
    ctx = contexto(*[TimeoutError("cookie=segredo-de-teste") for _ in range(3)])
    assert smart_sessao.sessao_viva(ctx, cfg, log=logs.append) is None
    assert any("TimeoutError" in linha for linha in logs)
    assert all("segredo-de-teste" not in linha for linha in logs)


@pytest.mark.parametrize("usar_cdp", [False, True])
def test_indisponibilidade_aborta_e_fecha_apenas_chrome_proprio(
    cfg, capsolver, monkeypatch, usar_cdp
):
    ctx = contexto(*[TimeoutError() for _ in range(3)])
    monkeypatch.setattr(smart_sessao, "abrir_chrome", lambda *_: ctx)
    monkeypatch.setattr(smart_sessao, "anexar", lambda *_: ctx)
    with pytest.raises(smart_sessao.SmartIndisponivel):
        with smart_sessao.sessao(None, cfg, usar_cdp=usar_cdp, log=lambda _: None):
            pytest.fail("sessao nao confirmada nao pode chegar ao trabalho")
    assert ctx.close.call_count == (0 if usar_cdp else 1)


@pytest.mark.parametrize("erro,codigo", [("SmartIndisponivel", 3), ("SemSessao", 2)])
def test_pagamento_aborta_com_codigo_correto_sem_gerar(monkeypatch, tmp_path, erro, codigo):
    import importlib
    from contextlib import contextmanager, nullcontext

    pytest.importorskip("playwright")
    raiz = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(raiz / "src/processors/web/remessa_pagamento"))
    monkeypatch.setenv("PAGAMENTO_ENV_FILE", "/dev/null")
    for chave in ("USER_DATA_DIR_PAG", "PASTA_SAIDA_PAG", "DEBUG_DIR_PAG"):
        monkeypatch.setenv(chave, str(tmp_path / chave))
    monkeypatch.setenv("ARQ_CONTROLE_PAG", str(tmp_path / "controle.csv"))
    import pagamento_config
    import gerar_remessa_pagamento
    importlib.reload(pagamento_config)
    rp = importlib.reload(gerar_remessa_pagamento)
    monkeypatch.setattr(sys, "argv", ["gerar_remessa_pagamento.py"])
    monkeypatch.setattr(rp, "sync_playwright", lambda: nullcontext(None))
    monkeypatch.setattr(rp.cfg, "exigir_tela", lambda: None)

    @contextmanager
    def falha_de_sessao(*_args, **_kwargs):
        raise getattr(smart_sessao, erro)("falha simulada")
        yield  # pragma: no cover

    monkeypatch.setattr(rp.smart_sessao, "sessao", falha_de_sessao)
    rodada = Mock(side_effect=AssertionError("nao pode gerar sem sessao validada"))
    monkeypatch.setattr(rp, "rodada", rodada)
    assert rp.main() == codigo
    rodada.assert_not_called()
