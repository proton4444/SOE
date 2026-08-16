"""
Talking to Anthropic, which does not speak chat-completions.

``api.anthropic.com`` was on the base-URL allowlist long before anything
could use it: the brain posted ``/chat/completions`` with a bearer token, and
Anthropic answers that with a 404. The host being allowed made the failure
read as a key problem. These tests hold the translation — system prompt
lifted out of the messages, ``x-api-key``, ``/messages`` — and the two things
that follow from Anthropic billing in tokens rather than dollars.

No network: every call goes through an httpx MockTransport.
"""

import os
import tempfile
import uuid
from pathlib import Path

import httpx
import pytest

# Importing the webapp binds its data and game directories once, per process.
# Left unset they are the checkout's own `games/`, and this module is
# collected first, so every later test in the run would inherit the repo as
# its scratch space -- and delete recorded games out of it.
os.environ.setdefault(
    "SOE_DATA_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_anthropic_{uuid.uuid4().hex[:8]}"),
)
os.environ.setdefault(
    "SOE_GAMES_DIR",
    str(Path(tempfile.gettempdir()) / f"soe_anthropic_games_{uuid.uuid4().hex[:8]}"),
)
ANTHROPIC_KEY = "sk-ant-test-secret-key"
os.environ.setdefault("SOE_LLM_KEY", ANTHROPIC_KEY)

from scripts.arena import SpendBudget  # noqa: E402
from webapp.ai import anthropic_chat, brain  # noqa: E402

ANTHROPIC_BASE = "https://api.anthropic.com/v1"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

_ORIGINAL_CLIENT = httpx.Client


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    import time as _time

    class _FakeTime:
        sleep = staticmethod(lambda s: None)
        perf_counter = staticmethod(_time.perf_counter)

    monkeypatch.setattr(brain, "time", _FakeTime())


@pytest.fixture
def anthropic_base(monkeypatch):
    """Point the brain at Anthropic, with a key of this module's own.

    Both are set here rather than at import: other test modules set
    ``SOE_LLM_KEY`` at import time too, and whichever imports last wins.
    """
    monkeypatch.setenv("SOE_LLM_BASE", ANTHROPIC_BASE)
    monkeypatch.setenv("SOE_LLM_KEY", ANTHROPIC_KEY)


def _install(monkeypatch, responses, calls):
    """Serve ``responses`` in order, holding on the last one."""

    def handler(request):
        calls.append(request)
        status, payload = responses[min(len(calls) - 1, len(responses) - 1)]
        return httpx.Response(status, json=payload)

    def factory(timeout=120, **kwargs):
        return _ORIGINAL_CLIENT(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(brain.httpx, "Client", factory)


def _reply(text="--- ORDERS ---\nTax.\n", usage=None):
    return {
        "id": "msg_01ABC",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": usage or {"input_tokens": 1000, "output_tokens": 200},
    }


# ---------------------------------------------------------------------------
# which wire format
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base,expected",
    [
        ("https://api.anthropic.com/v1", True),
        ("https://api.anthropic.com", True),
        ("api.anthropic.com/v1", True),
        ("https://openrouter.ai/api/v1", False),
        ("https://api.openai.com/v1", False),
        # A host that merely ends in the same letters is not the same host.
        ("https://notapi.anthropic.com.evil.test/v1", False),
    ],
)
def test_the_base_url_picks_the_wire_format(base, expected):
    assert anthropic_chat.is_anthropic_base(base) is expected


def test_claude_through_openrouter_stays_an_ordinary_call(monkeypatch):
    """The model name never decides the format; only the host does.

    OpenRouter serves Claude under its own slug over chat-completions, and
    that route needs no translation at all.
    """
    monkeypatch.setenv("SOE_LLM_BASE", OPENROUTER_BASE)
    calls = []
    _install(
        monkeypatch,
        [(200, {"id": "gen-1", "choices": [{"message": {"content": "ok"}}]})],
        calls,
    )
    brain.chat(
        model="anthropic/claude-haiku-4.5",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert calls[0].url.path.endswith("/chat/completions")
    assert "authorization" in {k.lower() for k in calls[0].headers}


# ---------------------------------------------------------------------------
# the request
# ---------------------------------------------------------------------------


def test_the_system_prompt_leaves_the_message_list():
    """Anthropic rejects a ``system`` role inside ``messages``."""
    _, _, payload = anthropic_chat.build_request(
        model="claude-haiku-4-5",
        messages=[
            {"role": "system", "content": "You are a strategic game AI."},
            {"role": "user", "content": "Orders?"},
        ],
        temperature=0.0,
        max_tokens=1500,
        api_key="sk-ant-x",
    )
    assert payload["system"] == "You are a strategic game AI."
    assert [m["role"] for m in payload["messages"]] == ["user"]


def test_several_system_turns_join_in_order():
    _, _, payload = anthropic_chat.build_request(
        model="claude-haiku-4-5",
        messages=[
            {"role": "system", "content": "First."},
            {"role": "system", "content": "Second."},
            {"role": "user", "content": "Orders?"},
        ],
        temperature=0.0,
        max_tokens=100,
        api_key="sk-ant-x",
    )
    assert payload["system"] == "First.\n\nSecond."


def test_no_system_turn_sends_no_system_field():
    _, _, payload = anthropic_chat.build_request(
        model="claude-haiku-4-5",
        messages=[{"role": "user", "content": "Orders?"}],
        temperature=0.0,
        max_tokens=100,
        api_key="sk-ant-x",
    )
    assert "system" not in payload


def test_the_key_travels_in_the_anthropic_header():
    _, headers, _ = anthropic_chat.build_request(
        model="claude-haiku-4-5",
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.0,
        max_tokens=100,
        api_key="sk-ant-x",
    )
    assert headers["x-api-key"] == "sk-ant-x"
    assert headers["anthropic-version"] == anthropic_chat.API_VERSION
    assert "Authorization" not in headers


def test_a_conversation_of_nothing_but_system_is_refused():
    with pytest.raises(ValueError):
        anthropic_chat.build_request(
            model="claude-haiku-4-5",
            messages=[{"role": "system", "content": "Only this."}],
            temperature=0.0,
            max_tokens=100,
            api_key="sk-ant-x",
        )


def test_a_temperature_anthropic_cannot_take_is_refused_not_clamped():
    """The regulation hash records the temperature a season froze with.

    Clamping 1.4 to 1.0 would run a different regulation than the one the
    hash attests to, and nothing downstream would say so.
    """
    with pytest.raises(ValueError, match="temperature"):
        anthropic_chat.build_request(
            model="claude-haiku-4-5",
            messages=[{"role": "user", "content": "hi"}],
            temperature=1.4,
            max_tokens=100,
            api_key="sk-ant-x",
        )


def test_a_bad_temperature_never_reaches_the_network(monkeypatch, anthropic_base):
    calls = []
    _install(monkeypatch, [(200, _reply())], calls)
    with pytest.raises(brain.LLMError):
        brain.chat(
            model="claude-haiku-4-5",
            messages=[{"role": "user", "content": "hi"}],
            temperature=1.4,
        )
    assert calls == [], "a request the provider would reject was still sent"


# ---------------------------------------------------------------------------
# images
# ---------------------------------------------------------------------------


def test_a_data_uri_becomes_a_base64_image_block():
    _, _, payload = anthropic_chat.build_request(
        model="claude-haiku-4-5",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is on the board?"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,QUJD"},
                    },
                ],
            }
        ],
        temperature=0.0,
        max_tokens=100,
        api_key="sk-ant-x",
    )
    blocks = payload["messages"][0]["content"]
    assert blocks[0] == {"type": "text", "text": "What is on the board?"}
    assert blocks[1] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "QUJD"},
    }


def test_a_plain_url_image_is_passed_as_a_url_source():
    _, _, payload = anthropic_chat.build_request(
        model="claude-haiku-4-5",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.test/board.png"},
                    },
                ],
            }
        ],
        temperature=0.0,
        max_tokens=100,
        api_key="sk-ant-x",
    )
    assert payload["messages"][0]["content"][1]["source"] == {
        "type": "url",
        "url": "https://example.test/board.png",
    }


def test_an_unencoded_data_uri_is_refused():
    with pytest.raises(ValueError):
        anthropic_chat._image_block("data:image/png,rawbytes")


def test_a_plain_string_message_stays_a_string():
    """No point wrapping every ordinary turn in a one-element block list."""
    _, _, payload = anthropic_chat.build_request(
        model="claude-haiku-4-5",
        messages=[{"role": "user", "content": "Orders?"}],
        temperature=0.0,
        max_tokens=100,
        api_key="sk-ant-x",
    )
    assert payload["messages"][0]["content"] == "Orders?"


# ---------------------------------------------------------------------------
# the response
# ---------------------------------------------------------------------------


def test_text_blocks_are_joined_and_others_dropped():
    """A thinking block is not prose, and the orders parser reads prose."""
    data = {
        "id": "msg_1",
        "content": [
            {"type": "thinking", "thinking": "weighing the options"},
            {"type": "text", "text": "--- ORDERS ---\n"},
            {"type": "text", "text": "Tax.\n"},
        ],
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    text, _, request_id = anthropic_chat.parse_response("claude-haiku-4-5", data)
    assert text == "--- ORDERS ---\nTax.\n"
    assert request_id == "msg_1"


def test_a_malformed_payload_is_a_value_error():
    with pytest.raises(ValueError):
        anthropic_chat.parse_response("claude-haiku-4-5", {"id": "msg_1"})


def test_an_answer_of_only_thinking_reads_as_an_empty_completion(
    monkeypatch, anthropic_base
):
    calls = []
    reply = _reply()
    reply["content"] = [{"type": "thinking", "thinking": "..."}]
    _install(monkeypatch, [(200, reply)], calls)
    with pytest.raises(brain.LLMError, match="empty"):
        brain.chat(
            model="claude-haiku-4-5", messages=[{"role": "user", "content": "hi"}]
        )


# ---------------------------------------------------------------------------
# cost: Anthropic bills tokens, and declares no dollars
# ---------------------------------------------------------------------------


def test_the_estimate_is_list_price_arithmetic():
    """Haiku 4.5 is $1.00 in / $5.00 out per million tokens."""
    usage = {"input_tokens": 1_000_000, "output_tokens": 200_000}
    assert anthropic_chat.estimate_cost_usd("claude-haiku-4-5", usage) == pytest.approx(
        1.00 + 1.00
    )


def test_a_dated_pin_is_the_same_model_at_the_same_price():
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    assert anthropic_chat.estimate_cost_usd(
        "claude-haiku-4-5-20251001", usage
    ) == pytest.approx(1.00)


def test_an_unpriced_model_gets_no_estimate():
    """A wrong price is worse than no price: say nothing instead of guessing."""
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    assert anthropic_chat.estimate_cost_usd("claude-something-new", usage) is None


def test_cache_tokens_are_priced_off_the_input_rate():
    """Nothing sends cache_control today; this keeps the arithmetic honest if
    something does."""
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000,
    }
    assert anthropic_chat.estimate_cost_usd("claude-haiku-4-5", usage) == pytest.approx(
        1.00 * 1.25 + 1.00 * 0.1
    )


def test_the_estimate_never_impersonates_a_declared_cost(monkeypatch, anthropic_base):
    """``usage["cost"]`` is what the official record reads, and Anthropic
    stated no cost. The estimate travels under a name that says what it is."""
    calls = []
    _install(monkeypatch, [(200, _reply())], calls)
    result = brain.chat_result(
        model="claude-haiku-4-5", messages=[{"role": "user", "content": "hi"}]
    )
    assert "cost" not in result.usage
    assert result.usage["cost_estimated_usd"] == pytest.approx(
        (1000 * 1.00 + 200 * 5.00) / 1_000_000
    )
    assert result.usage["input_tokens"] == 1000


# ---------------------------------------------------------------------------
# end to end through the brain
# ---------------------------------------------------------------------------


def test_a_completion_comes_back_through_the_ordinary_interface(
    monkeypatch, anthropic_base
):
    calls = []
    _install(monkeypatch, [(200, _reply())], calls)
    result = brain.chat_result(
        model="claude-haiku-4-5",
        messages=[
            {"role": "system", "content": "You are a strategic game AI."},
            {"role": "user", "content": "Orders?"},
        ],
    )
    assert result.text == "--- ORDERS ---\nTax.\n"
    assert result.model == "claude-haiku-4-5"
    assert result.provider_request_id == "msg_01ABC"
    assert calls[0].url.path == "/v1/messages"
    assert calls[0].headers["x-api-key"] == ANTHROPIC_KEY


def test_a_rate_limit_is_retried_on_this_transport_too(monkeypatch, anthropic_base):
    """Both providers share one error policy; that is the point of keeping it
    in the brain."""
    calls = []
    _install(monkeypatch, [(429, {}), (200, _reply())], calls)
    result = brain.chat_result(
        model="claude-haiku-4-5", messages=[{"role": "user", "content": "hi"}]
    )
    assert result.attempts == 2


def test_a_refusal_is_not_retried(monkeypatch, anthropic_base):
    calls = []
    _install(
        monkeypatch,
        [
            (
                400,
                {
                    "type": "error",
                    "error": {"type": "invalid_request_error", "message": "bad model"},
                },
            )
        ],
        calls,
    )
    with pytest.raises(brain.LLMError, match="bad model"):
        brain.chat(
            model="claude-haiku-4-5", messages=[{"role": "user", "content": "hi"}]
        )
    assert len(calls) == 1


def test_a_reasoning_setting_is_ignored_rather_than_sent(monkeypatch, anthropic_base):
    """``reasoning`` is an OpenRouter field; the Messages API would reject it.

    Anthropic's own thinking controls differ by model family, and the alpha
    uses none of them, so the knob is logged and dropped.
    """
    monkeypatch.setenv("SOE_LLM_REASONING", "high")
    calls = []
    _install(monkeypatch, [(200, _reply())], calls)
    brain.chat(model="claude-haiku-4-5", messages=[{"role": "user", "content": "hi"}])
    import json

    assert "reasoning" not in json.loads(calls[0].content.decode())


# ---------------------------------------------------------------------------
# the spend ceiling
# ---------------------------------------------------------------------------


def test_an_estimate_keeps_the_ceiling_working():
    """Before this, one Anthropic call ended the run.

    ``charge`` stopped the moment a provider omitted ``cost``, which is every
    Anthropic call, so a paid run would halt after its first turn.
    """
    budget = SpendBudget(limit_usd=1.00)
    budget.charge(None, estimate=0.40)
    assert not budget.exhausted
    assert budget.spent_usd == pytest.approx(0.40)
    assert budget.cost_known is False, "an estimate is not a declared cost"
    assert budget.estimated is True


def test_an_estimated_ceiling_still_stops_the_run():
    budget = SpendBudget(limit_usd=1.00)
    budget.charge(None, estimate=0.60)
    budget.charge(None, estimate=0.50)
    assert budget.exhausted


def test_no_cost_and_no_estimate_still_halts():
    """An unpriced model on a provider that declares nothing cannot be
    bounded, and the run stops rather than spend blind."""
    budget = SpendBudget(limit_usd=1.00)
    budget.charge(None)
    assert budget.exhausted
    assert budget.cost_known is False
    assert budget.estimated is False


def test_a_declared_cost_is_still_preferred():
    budget = SpendBudget(limit_usd=1.00)
    budget.charge(0.25, estimate=99.0)
    assert budget.spent_usd == pytest.approx(0.25)
    assert budget.cost_known is True
    assert budget.estimated is False
