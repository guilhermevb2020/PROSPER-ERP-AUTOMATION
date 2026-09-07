from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.processors.web.boletos import healthcheck as h


@pytest.mark.parametrize('padrao', [
    'enviar_lote', 'emitir_lote', 'baixar_dia', '/robo_remessa/', '/robo_retorno/',
])
@pytest.mark.parametrize('chrome_ok', [True, False])
def test_robo_ativo_impede_login_e_reinicio_de_chrome(monkeypatch, padrao, chrome_ok):
    conn = Mock()
    monkeypatch.setattr(h._db, 'get_conn', lambda: conn)
    monkeypatch.setattr(h, 'estado_anterior', lambda c: 'healthy')
    monkeypatch.setattr(h, 'chrome_ok', lambda: chrome_ok)
    monkeypatch.setattr(h.subprocess, 'run', lambda args, **kw:
                        SimpleNamespace(returncode=0 if padrao in args[-1] else 1))
    register, restart, session, notify = Mock(), Mock(), Mock(), Mock()
    monkeypatch.setattr(h, 'registrar', register)
    monkeypatch.setattr(h, 'religar_chrome', restart)
    monkeypatch.setattr(h, 'sessao_logada', session)
    monkeypatch.setattr(h, 'notificar_humano', notify)
    h.main()
    assert register.call_args.kwargs['estado'] == 'busy'
    assert register.call_args.kwargs['logado'] is False
    assert register.call_args.kwargs['chrome_ok_'] is chrome_ok
    restart.assert_not_called()
    session.assert_not_called()
    notify.assert_not_called()
    conn.close.assert_called_once()


def test_falha_de_inspecao_nao_vira_ausencia_de_robo(monkeypatch):
    monkeypatch.setattr(h.subprocess, 'run', lambda *args, **kw: SimpleNamespace(returncode=2))
    with pytest.raises(RuntimeError, match='processos Smart'):
        h.robo_smart_ativo()
