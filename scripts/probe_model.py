"""
Probe OpenRouter models for SOE order compliance (needs SOE_LLM_KEY).

Usage:
    python scripts/probe_model.py [model ...]

Runs one tiny "write 3 orders" task per model through webapp.ai.brain and
reports whether the reply carried the ORDERS marker, how many orders parsed,
and the structured result (attempts, latency, usage, cost) from
``brain.chat_result``. Default: the recommended set. Exit code 0 if every
probed model parsed at least one order.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from soe import models, parser  # noqa: E402
from soe.models import PopulationBand  # noqa: E402

from webapp.ai import brain  # noqa: E402
from webapp.ai.context import extract_marked_orders  # noqa: E402

PROBE_RECEIPT = _REPO_ROOT / "server_data" / "phase0_probe.json"

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


def probe(model: str) -> tuple[bool, bool, str, dict]:
    result = brain.chat_result(
        model=model,
        messages=[
            {"role": "system", "content": "You are a strategic game AI."},
            {"role": "user", "content": PROBE_TASK},
        ],
        temperature=0.0,
    )
    marked = extract_marked_orders(result.text)
    has_marker = marked is not None
    parsed_ok = False
    if has_marker and marked:
        parsed = parser.parse_orders(marked, _probe_board(), "probe")
        parsed_ok = any(not order.warnings for order in parsed)
    summary = {
        "attempts": result.attempts,
        "latency_ms": result.latency_ms,
        "usage": result.usage,
        "provider_request_id": result.provider_request_id,
    }
    return has_marker, parsed_ok, result.text, summary


def _probe_board() -> models.GameState:
    """Tiny board matching PROBE_TASK so parse_orders can accept a real command."""
    gs = models.GameState()
    gs.world_map.cities["highfell"] = models.City(
        id="highfell", name="Highfell", population_band=PopulationBand.MEDIUM
    )
    gs.world_map.cities["redport"] = models.City(
        id="redport", name="Redport", population_band=PopulationBand.MEDIUM
    )
    gs.factions["probe"] = models.Faction(
        id="probe", name="Probe", controlled_city_ids={"highfell"}
    )
    gs.characters["marcus"] = models.Character(
        id="marcus",
        name="Emperor Marcus",
        faction_id="probe",
        location_city_id="highfell",
        is_leader=True,
    )
    return gs


def _order_lines(reply: str) -> int:
    marked = extract_marked_orders(reply)
    if not marked:
        return 0
    return sum(1 for line in marked.splitlines() if line.strip())


def main() -> int:
    models = sys.argv[1:] or DEFAULT_MODELS
    if not brain.is_configured():
        print("Set SOE_LLM_KEY first.")
        return 2
    failures = 0
    probes = {}
    for model in models:
        try:
            has_marker, parsed_ok, reply, result = probe(model)
        except brain.LLMError as exc:
            print(f"{model:<42} ERROR  {exc}")
            failures += 1
            probes[model] = {
                "success": False,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "failure": str(exc)[:300],
            }
            continue
        status = "OK " if has_marker and parsed_ok else "FAIL"
        if not has_marker or not parsed_ok:
            failures += 1
        usage = result.get("usage") or {}
        cost = usage.get("cost")
        print(
            f"{model:<42} {status}  orders_extracted={has_marker} "
            f"lines={_order_lines(reply)} "
            f"attempts={result['attempts']} latency_ms={result['latency_ms']:.0f} "
            f"tokens={usage.get('total_tokens', '?')} "
            f"cost={cost if cost is not None else 'unknown'}"
        )
        probes[model] = {
            "success": bool(has_marker and parsed_ok),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "provider_request_id": result.get("provider_request_id"),
            "usage": usage,
        }
    PROBE_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    PROBE_RECEIPT.write_text(
        json.dumps({"schema_version": 1, "probes": probes}, indent=2),
        encoding="utf-8",
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
