"""Dispatch every queued official match in a season.

The operator starts this; they do not edit ``competitions.json``. Resume of
an interrupted match is the arena's. Usage:

    python scripts/run_league.py --season ssn_…
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from webapp import competition  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True, help="Season id (ssn_…)")
    args = parser.parse_args(argv)
    store = competition.default_store()
    report = competition.run_until_idle(store, args.season)
    print(json.dumps(report, indent=2))
    if report["total"] and report["rate"] < competition.AUTO_COMPLETE_THRESHOLD:
        return 2
    return 0 if report["season_status"] == competition.STATUS_COMPLETE else 1


if __name__ == "__main__":
    raise SystemExit(main())
