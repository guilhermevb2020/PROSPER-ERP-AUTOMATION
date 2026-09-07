from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.processors.web.boletos import _sessao


@pytest.mark.parametrize('visible,enabled', [(True, False), (False, True)])
def test_modal_indisponivel_nao_finge_clique(visible, enabled, capsys):
    button = Mock(is_visible=Mock(return_value=visible), is_enabled=Mock(return_value=enabled))
    locator = SimpleNamespace(count=lambda: 1, first=button)
    frame = Mock(locator=Mock(return_value=locator))
    page = SimpleNamespace(is_closed=lambda: False, frames=[frame])
    assert _sessao._dispensar_seguranca(page) is False
    button.click.assert_not_called()
    frame.evaluate.assert_not_called()
    assert 'PROSSEGUIR' not in capsys.readouterr().out


def test_modal_habilitado_clica_uma_vez():
    button = Mock(is_visible=Mock(return_value=True), is_enabled=Mock(return_value=True))
    frame = Mock(locator=Mock(return_value=SimpleNamespace(count=lambda: 1, first=button)))
    page = SimpleNamespace(is_closed=lambda: False, frames=[frame])
    assert _sessao._dispensar_seguranca(page) is True
    button.click.assert_called_once()
