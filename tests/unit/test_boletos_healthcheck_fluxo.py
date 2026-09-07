"""Estados do healthcheck sem reiniciar Chrome, autenticar ou notificar pessoas."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from src.processors.web.boletos import healthcheck as h


@pytest.mark.parametrize('cenario,estado',[
    ('chrome_down','chrome_down'),('chrome_down_repetido','chrome_down'),
    ('envio_ativo','busy'),('saudavel','healthy'),
    ('fora_janela','needs_login_fora_janela'),('relogin_ok','auto_relogado'),
    ('relogin_falhou','needs_login')])
def test_estados_e_efeitos_controlados(monkeypatch,cenario,estado):
    conn=Mock();registro=Mock();notificar=Mock();religar=Mock()
    monkeypatch.setattr(h._db,'get_conn',lambda:conn)
    monkeypatch.setattr(h,'estado_anterior',lambda c:'chrome_down' if cenario=='chrome_down_repetido' else 'healthy')
    monkeypatch.setattr(h,'registrar',registro)
    monkeypatch.setattr(h,'notificar_humano',notificar)
    monkeypatch.setattr(h,'religar_chrome',religar)
    monkeypatch.setattr(h,'AUTO_RELIGAR',True)
    monkeypatch.setattr(h,'chrome_ok',lambda:not cenario.startswith('chrome_down'))
    monkeypatch.setattr(h.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0 if cenario=='envio_ativo' else 1))
    sessao=Mock(return_value=cenario=='saudavel');monkeypatch.setattr(h,'sessao_logada',sessao)
    monkeypatch.setattr(h,'_dentro_janela_relogin',lambda:cenario!='fora_janela')
    import playwright.sync_api as pw
    from src.processors.web.boletos import _sessao as s
    login=Mock(return_value=cenario=='relogin_ok')
    monkeypatch.setattr(s,'login_automatico_capsolver',login)
    browser=SimpleNamespace(contexts=[object()])
    p=SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=Mock(return_value=browser)))
    monkeypatch.setattr(pw,'sync_playwright',lambda:nullcontext(p))
    h.main()
    assert registro.call_args.kwargs['estado']==estado
    conn.close.assert_called_once()
    assert notificar.call_count==int(cenario in ('chrome_down','relogin_falhou'))
    assert religar.call_count==int(cenario.startswith('chrome_down'))
    assert login.call_count==int(cenario.startswith('relogin_'))
    if cenario=='envio_ativo':sessao.assert_not_called()
