"""
Anthropic Messages transport for the bot brain.

``brain`` speaks OpenAI chat-completions, which is what OpenRouter and most
other providers accept. Anthropic does not: it has its own wire format
(``POST /v1/messages``), its own auth header, and it takes the system prompt
out of the message list. Pointing ``SOE_LLM_BASE`` at ``api.anthropic.com``
without this module produces a 404, not a completion — the host was already
on the allowlist, which made the failure look like a key problem.

This module is deliberately pure: it builds a request and parses a response,
and never touches the network. ``brain._post_once`` owns the HTTP call, the
retry classification, and the error policy for both transports, so the two
providers cannot drift apart on what counts as retryable.

Three differences are worth knowing before pointing the alpha at Anthropic:

* **Temperature is capped at 1.0.** OpenAI-compatible providers accept up to
  2.0. A regulation asking for more is refused here rather than clamped: the
  regulation hash records the temperature the season was frozen with, and
  quietly running a different one makes that record a lie.
* **Reasoning effort is not translated.** The knob is per model family on
  Anthropic (adaptive on 4.6 and later, a token budget before it) and the
  alpha does not use it. ``brain`` logs when it is set and ignores it.
* **No cost is declared.** Anthropic returns token counts, never dollars, so
  ``usage["cost"]`` — the field the official record and the spend ceiling
  both read — is absent. We publish an estimate under its own name instead;
  see ``PRICES_PER_MTOK``.
"""

from __future__ import annotations

from urllib.parse import urlsplit

#: Hosts served by the Messages API rather than by chat-completions.
ANTHROPIC_HOSTS: tuple[str, ...] = ("api.anthropic.com",)

#: Pinned wire version. Anthropic requires it on every request and treats a
#: missing header as an error, so it is not optional configuration.
API_VERSION = "2023-06-01"

#: Anthropic's published list price, US dollars per million tokens, as
#: (input, output). Read from Anthropic's model table on 2026-06-24.
#:
#: Only models this project has decided to run are priced. An unpriced model
#: yields no estimate at all, which stops a spend ceiling rather than letting
#: it run on a guessed number — a wrong price is worse than no price.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
}

#: Prompt-cache tokens are billed off the input rate: 1.25x to write a
#: 5-minute entry, 0.1x to read one. Nothing here sends ``cache_control``, so
#: these stay at zero; they are priced anyway so that turning caching on
#: later cannot silently understate the bill.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.1

MAX_TEMPERATURE = 1.0


def is_anthropic_base(base_url: str) -> bool:
    """Whether this base URL is served by the Messages API."""
    host = urlsplit(base_url if "//" in base_url else f"//{base_url}").hostname or ""
    host = host.lower()
    return any(
        host == known or host.endswith(f".{known}") for known in ANTHROPIC_HOSTS
    )


def price_key(model: str) -> str:
    """The priced name for a model id, dated alias or not.

    ``claude-haiku-4-5-20251001`` and ``claude-haiku-4-5`` are the same model
    at the same price; only the first is a snapshot pin.
    """
    name = model.strip()
    if name in PRICES_PER_MTOK:
        return name
    head, _, tail = name.rpartition("-")
    if head and len(tail) == 8 and tail.isdigit() and head in PRICES_PER_MTOK:
        return head
    return ""


def estimate_cost_usd(model: str, usage: dict) -> float | None:
    """Dollars this call cost at list price, or ``None`` for an unpriced model.

    An estimate, and named one everywhere it travels. The provider declared
    nothing; this is arithmetic over published rates, and it is wrong the
    moment those rates change or a discount applies.
    """
    key = price_key(model)
    if not key:
        return None
    inp, out = PRICES_PER_MTOK[key]

    def count(field: str) -> float:
        value = usage.get(field, 0)
        return float(value) if isinstance(value, (int, float)) else 0.0

    billed_input = (
        count("input_tokens")
        + count("cache_creation_input_tokens") * CACHE_WRITE_MULTIPLIER
        + count("cache_read_input_tokens") * CACHE_READ_MULTIPLIER
    )
    return (billed_input * inp + count("output_tokens") * out) / 1_000_000


def split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """Lift ``system`` turns out of the list, as the Messages API requires.

    Several system turns are joined in order. A conversation that is nothing
    but system prompts would leave no message to answer, which the API
    rejects, so the caller's structure is otherwise left alone.
    """
    system_parts: list[str] = []
    rest: list[dict] = []
    for message in messages:
        if message.get("role") == "system":
            content = message.get("content", "")
            text = content if isinstance(content, str) else _flatten(content)
            if text.strip():
                system_parts.append(text)
        else:
            rest.append(message)
    return "\n\n".join(system_parts), rest


def _flatten(content) -> str:
    if isinstance(content, list):
        return "\n".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content)


def _image_block(url: str) -> dict:
    """An OpenAI ``image_url`` part as an Anthropic image block.

    Data URIs carry their own media type; anything else is passed as a URL
    source and fetched by Anthropic.
    """
    if url.startswith("data:"):
        header, _, data = url.partition(",")
        media_type = header[len("data:") :].split(";")[0] or "image/png"
        if ";base64" not in header:
            raise ValueError("Only base64 data URIs can be sent to Anthropic.")
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        }
    return {"type": "image", "source": {"type": "url", "url": url}}


def _content(content) -> str | list[dict]:
    if isinstance(content, str):
        return content
    blocks: list[dict] = []
    for part in content:
        if not isinstance(part, dict):
            blocks.append({"type": "text", "text": str(part)})
        elif part.get("type") == "image_url":
            blocks.append(_image_block(str(part.get("image_url", {}).get("url", ""))))
        else:
            blocks.append({"type": "text", "text": str(part.get("text", ""))})
    return blocks


def build_request(
    *,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    api_key: str,
) -> tuple[str, dict, dict]:
    """``(path, headers, payload)`` for one Messages call.

    Raises ``ValueError`` for a request Anthropic would reject on its face —
    caught by the caller and surfaced as a configuration error rather than
    burnt as a retry.
    """
    if temperature > MAX_TEMPERATURE:
        raise ValueError(
            f"Anthropic accepts temperature 0.0-{MAX_TEMPERATURE:.1f}; "
            f"this request asks for {temperature}."
        )
    system, conversation = split_system(messages)
    if not conversation:
        raise ValueError("Anthropic needs at least one non-system message.")
    payload: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": m.get("role", "user"), "content": _content(m.get("content", ""))}
            for m in conversation
        ],
    }
    if system:
        payload["system"] = system
    headers = {
        "x-api-key": api_key,
        "anthropic-version": API_VERSION,
        "Content-Type": "application/json",
    }
    return "/messages", headers, payload


def parse_response(model: str, data: dict) -> tuple[str, dict, str]:
    """``(text, usage, request_id)`` from a Messages response.

    Text blocks are concatenated and every other block type is dropped: the
    orders parser reads prose, and a thinking or tool block is not prose.

    ``usage`` is the provider's own accounting plus one key of ours, named so
    it can never be mistaken for it: ``cost_estimated_usd``.
    ``usage["cost"]`` stays absent, because Anthropic declared no cost and
    the official record only carries costs a provider stated itself.
    """
    try:
        blocks = data["content"]
        text = "".join(
            str(block.get("text", ""))
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("LLM returned an unexpected payload.") from exc
    usage = data.get("usage", {})
    usage = dict(usage) if isinstance(usage, dict) else {}
    estimate = estimate_cost_usd(model, usage)
    if estimate is not None:
        usage["cost_estimated_usd"] = round(estimate, 8)
    return text, usage, str(data.get("id", "") or "")
