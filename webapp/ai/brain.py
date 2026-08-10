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


class LLMError(RuntimeError):
    """The model could not be reached or refused the request."""


class _RetryableError(Exception):
    """429 or 5xx from the provider: worth trying again."""

    def __init__(self, status: int, detail: str, retry_after: float = 0.0):
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail
        self.retry_after = retry_after


def is_configured() -> bool:
    return bool(LLM_API_KEY)


def model_name(preferred: str) -> str:
    """The model to use for a profile: its own, else the configured default."""
    return preferred.strip() or LLM_MODEL


def chat(
    *,
    model: str,
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int = MAX_OUTPUT_TOKENS,
    images: tuple[str, ...] = (),
) -> str:
    """One chat completion. Returns the assistant's text content.

    ``images`` are data URIs (e.g. ``data:image/png;base64,...``) appended to
    the final user message for vision-capable models. Nothing about the
    conversation is logged — only model, sizes, latency, and token usage.
    """
    if not is_configured():
        raise LLMError("LLM not configured: set SOE_LLM_KEY.")
    if images:
        messages = _with_images(messages, images)
    prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 2):
        started = time.perf_counter()
        try:
            text, usage = _post_once(model, messages, temperature, max_tokens)
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
            return text
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
        f"LLM request failed after {MAX_RETRIES + 1} attempts: "
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
) -> tuple[str, str]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
        # OpenRouter attribution headers; a neutral title is fine.
        "HTTP-Referer": "https://github.com/anomalyco/opencode",
        "X-Title": "Spoils of Empire",
    }
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{LLM_BASE_URL}/chat/completions",
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
    usage_summary = ",".join(f"{k}={v}" for k, v in usage.items())
    return text or "", usage_summary


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
