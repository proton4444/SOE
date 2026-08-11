"""
Probe OpenRouter models for SOE order compliance (needs SOE_LLM_KEY).

Usage:
    python scripts/probe_model.py [model ...]

Runs one tiny "write 3 orders" task per model through webapp.ai.brain and
reports whether the reply carried the ORDERS marker and how many orders parsed.
Default: the recommended set. Exit code 0 if every probed model parsed at
least one order.
"""

from __future__ import annotations

import sys

from webapp.ai import brain
from webapp.ai.orchestrator import extract_orders

PROBE_TASK = (
    "You command a small faction in a fantasy strategy game. Your leader is "
    "Emperor Marcus and he is in Highfell with 30 soldiers. Write 3 orders "
    "for the next turn.\n\n"
    "Order syntax examples:\n"
    "Have Emperor Marcus go to Redport.\n"
    "Recruit 20 soldiers in Highfell.\n"
    "Tax.\n"
    "Have Emperor Marcus attack Khan Tengri.\n"
    "Work for 1 week.\n\n"
    "Rules: one order per line, each ending with a period, and use only "
    "commands from the examples or plain English similar to them.\n\n"
    "End your reply with the marker line `--- ORDERS ---` followed by the "
    "orders. Anything before the marker is reasoning and is ignored."
)

DEFAULT_MODELS = [
    "openai/gpt-4o-mini",
    "openai/gpt-4.1-mini",
    "google/gemini-2.5-flash",
    "meta-llama/llama-3.3-70b-instruct",
    "qwen/qwen3-32b",
]


def probe(model: str) -> tuple[bool, bool, str]:
    reply = brain.chat(
        model=model,
        messages=[
            {"role": "system", "content": "You are a strategic game AI."},
            {"role": "user", "content": PROBE_TASK},
        ],
        temperature=0.0,
    )
    orders = extract_orders(reply)
    return orders != "", bool(orders), reply


def _order_lines(reply: str) -> int:
    return sum(1 for line in extract_orders(reply).splitlines() if line.strip())


def main() -> int:
    models = sys.argv[1:] or DEFAULT_MODELS
    if not brain.is_configured():
        print("Set SOE_LLM_KEY first.")
        return 2
    failures = 0
    for model in models:
        try:
            has_marker, parsed_ok, reply = probe(model)
        except brain.LLMError as exc:
            print(f"{model:<42} ERROR  {exc}")
            failures += 1
            continue
        status = "OK " if has_marker and parsed_ok else "FAIL"
        if not has_marker or not parsed_ok:
            failures += 1
        print(
            f"{model:<42} {status}  orders_extracted={has_marker} lines={_order_lines(reply)}"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
