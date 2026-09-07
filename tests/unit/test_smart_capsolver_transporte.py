from unittest.mock import Mock

import pytest
import requests

from src.processors.web.boletos import _sessao as sessao


def response(status=200, body=None):
    return Mock(status_code=status, json=Mock(return_value=body))


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(sessao.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(sessao.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    monkeypatch.setenv("CAPSOLVER_API_KEY", "secret-test-key")
    return now


def test_eof_no_create_e_502_no_poll_recuperam_mesma_task(monkeypatch, clock, capsys):
    post = Mock(side_effect=[
        requests.ConnectionError("secret-test-key"),
        response(body={"errorId": 0, "taskId": "test-task"}),
        response(502),
        response(body={"errorId": 0, "status": "ready", "solution": {"gRecaptchaResponse": "token"}}),
    ])
    monkeypatch.setattr(requests, "post", post)
    assert sessao._resolver_recaptcha_sync("https://example.invalid", "site") == "token"
    assert [c.args[0].rsplit("/", 1)[-1] for c in post.call_args_list] == [
        "createTask", "createTask", "getTaskResult", "getTaskResult"]
    assert post.call_args_list[-1].kwargs["json"]["taskId"] == "test-task"
    output = capsys.readouterr().out
    assert "HTTP 502" in output and "ConnectionError" in output
    assert "secret-test-key" not in output


@pytest.mark.parametrize("bad", [response(503), response(429), response(body={}),
                                       response(body=[]), Mock(status_code=200, json=Mock(side_effect=ValueError))])
def test_create_tem_limite_de_tres_tentativas(monkeypatch, clock, bad):
    post = Mock(return_value=bad)
    monkeypatch.setattr(requests, "post", post)
    assert sessao._resolver_recaptcha_sync("https://example.invalid", "site") is None
    assert post.call_count == 3


@pytest.mark.parametrize("poll", [False, True])
def test_erro_de_credencial_nao_e_retentado(monkeypatch, clock, capsys, poll):
    responses = [response(body={"errorId": 1, "errorCode": "ERROR_KEY_DENIED_ACCESS",
                                "errorDescription": "secret-test-key"})]
    if poll:
        responses.insert(0, response(body={"errorId": 0, "taskId": "test-task"}))
    post = Mock(side_effect=responses)
    monkeypatch.setattr(requests, "post", post)
    assert sessao._resolver_recaptcha_sync("https://example.invalid", "site") is None
    assert post.call_count == len(responses)
    assert "secret-test-key" not in capsys.readouterr().out


def test_http_permanente_no_poll_encerra(monkeypatch, clock):
    post = Mock(side_effect=[response(body={"errorId": 0, "taskId": "task"}), response(401)])
    monkeypatch.setattr(requests, "post", post)
    assert sessao._resolver_recaptcha_sync("https://example.invalid", "site") is None
    assert post.call_count == 2


def test_poll_respeita_prazo_mesmo_com_falhas(monkeypatch, clock):
    post = Mock(side_effect=lambda url, **kwargs:
                response(body={"errorId": 0, "taskId": "task"}) if url.endswith("createTask") else response(502))
    monkeypatch.setattr(requests, "post", post)
    assert sessao._resolver_recaptcha_sync("https://example.invalid", "site", timeout=5) is None
    assert clock[0] == 5
    assert post.call_count == 3
    assert post.call_args_list[-1].kwargs["timeout"] == 1
