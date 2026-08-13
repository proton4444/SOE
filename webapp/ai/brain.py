"""
LLM client for managed bots — OpenAI-compatible, targeted at OpenRouter.

Config comes from the environment and is never logged:

    SOE_LLM_BASE    API base URL (default https://openrouter.ai/api/v1)
    SOE_LLM_KEY     API key — bots refuse to run without it
    SOE_LLM_MODEL   default model (default openai/gpt-4o-mini)
    SOE_LLM_TIMEOUT request timeout in seconds (default 120)

The interface is deliberately thin (``chat`` + ``is_configured``) so an
Anthropic or Gemini client can be added later without touching the
orchestrator.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from webapp.observability import logger

LLM_BASE_URL = os.environ.get("SOE_LLM_BASE", "https://openrouter.ai/api/v1").rstrip(
    "/"
)
LLM_API_KEY = os.environ.get("SOE_LLM_KEY", "").strip()
LLM_MODEL = os.environ.get("SOE_LLM_MODEL", "openai/gpt-4o-mini").strip()
TIMEOUT_SECONDS = float(os.environ.get("SOE_LLM_TIMEOUT", "120"))
MAX_RETRIES = int(os.environ.get("SOE_LLM_RETRIES", "2"))
MAX_OUTPUT_TOKENS = int(os.environ.get("SOE_LLM_MAX_TOKENS", "1500"))
# Cap how long a single retry may back off (Retry-After may suggest more).
MAX_BACKOFF_SECONDS = 30.0

# Env-only defaults (above) stay frozen for the arena manifest; the runtime
# resolution below prefers the environment and falls back to the
# dashboard-persisted settings (webapp.llm_settings), then to these defaults.


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _api_base() -> str:
    from webapp import llm_settings

    value = llm_settings.effective("base_url", "SOE_LLM_BASE", "")
    return (value or "https://openrouter.ai/api/v1").rstrip("/")


def _api_key() -> str:
    from webapp import llm_settings

    value = llm_settings.effective("key", "SOE_LLM_KEY", "")
    return (value or "").strip()


def _timeout_seconds() -> float:
    from webapp import llm_settings

    return float(llm_settings.effective("timeout_seconds", "SOE_LLM_TIMEOUT", 120))


def _max_retries() -> int:
    from webapp import llm_settings

    return int(llm_settings.effective("max_retries", "SOE_LLM_RETRIES", 2))


def _max_output_tokens() -> int:
    from webapp import llm_settings

    return int(llm_settings.effective("max_tokens", "SOE_LLM_MAX_TOKENS", 1500))


class LLMError(RuntimeError):
    """The model could not be reached or refused the request."""


class _RetryableError(Exception):
    """429 or 5xx from the provider: worth trying again."""

    def __init__(self, status: int, detail: str, retry_after: float = 0.0):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail
        self.retry_after = retry_after


@dataclass(frozen=True)
class ChatResult:
    """Structured outcome of one chat completion (Phase 0, WP2).

    ``usage`` is the provider's own token accounting kept as a structure,
    not a log string; keys are provider-defined. ``cost`` is recorded only
    when the provider declares it directly (``usage["cost"]`` on
    OpenRouter); otherwise it stays absent -- the official record never
    carries an estimated cost.

    Never contains credentials, headers, or signed URLs.
    """

    text: str
    model: str
    attempts: int
    latency_ms: float
    usage: dict[str, int | float] = field(default_factory=dict)
    provider_request_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_configured() -> bool:
    return bool(_api_key())


def model_name(preferred: str) -> str:
    """The model to use for a profile: its own, else the configured default."""
    preferred = preferred.strip()
    if preferred:
        return preferred
    env_model = os.environ.get("SOE_LLM_MODEL", "").strip()
    if env_model:
        return env_model
    from webapp import llm_settings

    return (llm_settings.load_settings().get("model") or LLM_MODEL).strip()


def chat(
    *,
    model: str,
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int | None = None,
    images: tuple[str, ...] = (),
) -> str:
    """One chat completion. Returns the assistant's text content.

    ``images`` are data URIs (e.g. ``data:image/png;base64,...``) appended to
    the final user message for vision-capable models. Nothing about the
    conversation is logged — only model, sizes, latency, and token usage.
    """
    return chat_result(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        images=images,
    ).text


def chat_result(
    *,
    model: str,
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int | None = None,
    images: tuple[str, ...] = (),
) -> ChatResult:
    """One chat completion with structured accounting.

    Same contract as ``chat``; callers that need usage, retries, latency or
    the provider request id use this and get a ``ChatResult``. Raises
    ``LLMError`` after exhausting retries, like ``chat``.
    """
    if not is_configured():
        raise LLMError("LLM not configured: set SOE_LLM_KEY.")
    if images:
        messages = _with_images(messages, images)
    prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
    max_tokens = max_tokens or _max_output_tokens()
    retries = _max_retries()

    last_error: Exception | None = None
    for attempt in range(1, retries + 2):
        started = time.perf_counter()
        try:
            text, usage, request_id = _post_once(
                model, messages, temperature, max_tokens
            )
            latency_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "llm_ok model=%s attempts=%d latency_ms=%.1f prompt_chars=%d "
                "completion_chars=%d usage=%s",
                model,
                attempt,
                latency_ms,
                prompt_chars,
                len(text),
                usage,
            )
            return ChatResult(
                text=text,
                model=model,
                attempts=attempt,
                latency_ms=round(latency_ms, 1),
                usage=dict(usage),
                provider_request_id=request_id,
            )
        except _RetryableError as exc:
            last_error = exc
            logger.warning(
                "llm_retry model=%s attempt=%d status=%d",
                model,
                attempt,
                exc.status,
            )
            time.sleep(_backoff(attempt, exc.retry_after))
        except LLMError:
            raise
        except Exception as exc:  # transport-level: retry, then surface
            last_error = exc
            logger.warning(
                "llm_retry model=%s attempt=%d error=%s",
                model,
                attempt,
                type(exc).__name__,
            )
            time.sleep(attempt)
    raise LLMError(
        f"LLM request failed after {retries + 1} attempts: "
        f"{type(last_error).__name__}: {last_error}"
    ) from last_error


def _backoff(attempt: int, retry_after: float) -> float:
    if retry_after > 0:
        return min(retry_after, MAX_BACKOFF_SECONDS)
    return min(attempt, MAX_BACKOFF_SECONDS)


def _with_images(messages: list[dict], images: tuple[str, ...]) -> list[dict]:
    parts: list[dict] = [
        {"type": "text", "text": str(messages[-1]["content"])},
    ]
    parts += [{"type": "image_url", "image_url": {"url": uri}} for uri in images]
    return [*messages[:-1], {"role": messages[-1]["role"], "content": parts}]


def _post_once(
    model: str, messages: list[dict], temperature: float, max_tokens: int
) -> tuple[str, dict, str]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        # OpenRouter attribution headers; a neutral title is fine.
        "HTTP-Referer": "https://github.com/anomalyco/opencode",
        "X-Title": "SOE",
    }
    try:
        with httpx.Client(timeout=_timeout_seconds()) as client:
            response = client.post(
                f"{_api_base()}/chat/completions",
                headers=headers,
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise _RetryableError(0, type(exc).__name__) from exc
    if response.status_code == 429 or response.status_code >= 500:
        raise _RetryableError(
            response.status_code,
            _provider_error(response),
            _retry_after(response),
        )
    if response.status_code != 200:
        raise LLMError(
            f"LLM refused the request (HTTP {response.status_code}): "
            f"{_provider_error(response)}"
        )
    data = response.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("LLM returned an unexpected payload.") from exc
    usage = data.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    request_id = str(data.get("id", "") or "")
    return text or "", usage, request_id


def _provider_error(response) -> str:
    """A short, safe slice of the provider's own error message."""
    try:
        message = response.json()["error"]["message"]
    except Exception:  # noqa: BLE001 - malformed provider bodies are common
        return ""
    return str(message).strip()[:200]


def _retry_after(response) -> float:
    value = response.headers.get("Retry-After", "")
    try:
        return float(value)
    except ValueError:
        return 0.0
