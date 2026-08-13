"""
Phase 0 WP2: structured LLM result.

``brain.chat_result`` must return usage, attempts, latency and the provider
request id as a structure, keep ``chat`` working as a text wrapper, classify
failures (4xx / 429 / 5xx / transport), retry only what is retryable, and
never put credentials into serialized records.
"""

import json
import os

import httpx
import pytest

os.environ["SOE_LLM_KEY"] = "sk-test-secret-key"

from webapp.ai import brain  # noqa: E402

_ORIGINAL_CLIENT = httpx.Client


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    import time as _time

    class _FakeTime:
        sleep = staticmethod(lambda s: None)
        perf_counter = staticmethod(_time.perf_counter)

    monkeypatch.setattr(brain, "time", _FakeTime())


def _mock_client(responses, calls):
    def handler(request):
        calls.append(request)
        status, payload = responses[min(len(calls) - 1, len(responses) - 1)]
        return httpx.Response(status, json=payload)

    return _ORIGINAL_CLIENT(transport=httpx.MockTransport(handler))


def _install(monkeypatch, client_factory):
    def factory(timeout=120, **kwargs):
        return client_factory()

    monkeypatch.setattr(brain.httpx, "Client", factory)


_ok_payload = {
    "id": "gen-req-123",
    "choices": [{"message": {"content": "--- ORDERS ---\nTax.\n"}}],
    "usage": {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
        "cost": 0.0012,
    },
}


def test_chat_result_parses_full_usage(monkeypatch):
    calls = []
    _install(monkeypatch, lambda: _mock_client([(200, _ok_payload)], calls))
    result = brain.chat_result(
        model="provider/model", messages=[{"role": "user", "content": "hi"}]
    )
    assert result.text == "--- ORDERS ---\nTax.\n"
    assert result.model == "provider/model"
    assert result.attempts == 1
    assert result.latency_ms >= 0
    assert result.usage == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
        "cost": 0.0012,
    }
    assert result.provider_request_id == "gen-req-123"
    assert len(calls) == 1


def test_chat_result_without_usage_or_request_id(monkeypatch):
    payload = {"choices": [{"message": {"content": "ok"}}]}
    calls = []
    _install(monkeypatch, lambda: _mock_client([(200, payload)], calls))
    result = brain.chat_result(model="m", messages=[{"role": "user", "content": "x"}])
    assert result.usage == {}
    assert result.provider_request_id == ""


def test_chat_is_text_wrapper(monkeypatch):
    calls = []
    _install(monkeypatch, lambda: _mock_client([(200, _ok_payload)], calls))
    text = brain.chat(model="m", messages=[{"role": "user", "content": "x"}])
    assert text == "--- ORDERS ---\nTax.\n"


def test_retry_on_429_then_success_counts_attempts(monkeypatch):
    calls = []
    responses = [(429, {"error": {"message": "rate limited"}}), (200, _ok_payload)]
    _install(monkeypatch, lambda: _mock_client(responses, calls))
    result = brain.chat_result(model="m", messages=[{"role": "user", "content": "x"}])
    assert result.attempts == 2
    assert result.provider_request_id == "gen-req-123"


def test_exhausted_retries_raise_with_attempts(monkeypatch):
    calls = []
    responses = [
        (500, {"error": {"message": "boom"}}),
        (503, {"error": {"message": "still down"}}),
        (500, {"error": {"message": "still down"}}),
    ]
    _install(monkeypatch, lambda: _mock_client(responses, calls))
    with pytest.raises(brain.LLMError) as exc:
        brain.chat_result(model="m", messages=[{"role": "user", "content": "x"}])
    assert "after 3 attempts" in str(exc.value)
    assert len(calls) == 3


def test_4xx_is_not_retried(monkeypatch):
    calls = []
    responses = [(400, {"error": {"message": "bad request"}})]
    _install(monkeypatch, lambda: _mock_client(responses, calls))
    with pytest.raises(brain.LLMError) as exc:
        brain.chat_result(model="m", messages=[{"role": "user", "content": "x"}])
    assert "HTTP 400" in str(exc.value)
    assert len(calls) == 1


def test_transport_error_is_retried_then_raised(monkeypatch):
    calls = []

    class _Flaky:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, headers=None, json=None):
            calls.append(url)
            if len(calls) < 3:
                raise httpx.ConnectError("connection refused")
            return httpx.Response(200, json=_ok_payload)

    _install(monkeypatch, lambda: _Flaky())
    result = brain.chat_result(model="m", messages=[{"role": "user", "content": "x"}])
    assert result.attempts == 3


def test_no_credentials_in_serialized_records(monkeypatch):
    calls = []
    _install(monkeypatch, lambda: _mock_client([(200, _ok_payload)], calls))
    result = brain.chat_result(model="m", messages=[{"role": "user", "content": "x"}])
    serialized = json.dumps(result.as_dict())
    assert "sk-test-secret-key" not in serialized
    assert "Authorization" not in serialized
    headers = {k.lower(): v for k, v in calls[0].headers.items()}
    assert headers.get("authorization", "").startswith("Bearer sk-test-secret-key")


def test_provider_error_message_is_bounded(monkeypatch):
    calls = []
    long_message = {"error": {"message": "x" * 5000}}
    _install(monkeypatch, lambda: _mock_client([(400, long_message)], calls))
    with pytest.raises(brain.LLMError) as exc:
        brain.chat_result(model="m", messages=[{"role": "user", "content": "x"}])
    assert len(str(exc.value)) < 400
