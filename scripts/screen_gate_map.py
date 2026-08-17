"""Screen candidate gate maps on the two axes a scenario has to keep alive.

`calib_12.json` is the official scenario, and the roadmap is explicit about
why it and not another twelve-town map: size is necessary and not sufficient.
Of three maps at twelve towns, two qualified and one did not, and the one that
failed had the most routes. Topology decides, so a candidate is screened, not
chosen.

The two axes, each 40 seed pairs at 30 turns, scripted policies only -- no
model calls, no cost:

    strategic   scripted:balanced against random
                A map where a policy cannot beat noise has no strategy in it.
    stylistic   scripted:military against scripted:religious
                A map where two styles come out level is a map that does not
                care what you do, which is the one thing a doctrine league
                cannot have.

Both are read on **sweeps**, not wins. A sweep is one policy winning from both
seats of the same pair, so start-city luck cannot explain it; a split is the
map talking rather than the policy. The sign test over sweeps is the number
that decides.

    python -m scripts.screen_gate_map --relief fbm --sea-rule detour \\
        --seeds 1-12 --keep-best

Each candidate is generated, screened, and deleted again unless it wins, so
the maps directory does not fill with rejects.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAPS_DIR = REPO_ROOT / "maps"

#: The official scenario's own recipe, recovered by regenerating it: this and
#: nothing else reproduces `calib_12.json` byte for byte. A candidate that
#: differs in town or region count is not the same kind of object.
GATE_TOWNS = 12
GATE_REGIONS = 3
GATE_SEED_PAIRS = 40
GATE_TURNS = 30

AXES = (
    ("strategic", "scripted:balanced", "random"),
    ("stylistic", "scripted:military", "scripted:religious"),
)

#: Two-sided sign test over sweeps. The roadmap qualified maps at p well under
#: this on both axes; 0.05 is the loosest reading of "separates".
ALPHA = 0.05

_SWEEPS_RE = re.compile(r"\*\*Sweeps:\*\* `([^`]+)` (\d+), `([^`]+)` (\d+)")


def sign_test(a: int, b: int) -> float:
    """Two-sided binomial p for a vs b under an even coin."""
    n = a + b
    if n == 0:
        return 1.0
    lo = min(a, b)
    tail = sum(math.comb(n, k) for k in range(lo + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def run_axis(map_name: str, left: str, right: str, out_dir: Path) -> tuple[int, int]:
    """Sweeps for (left, right) over the pairs, from the arena's own report."""
    result = subprocess.run(
        [
            sys.executable, str(REPO_ROOT / "scripts" / "arena.py"),
            "--policies", f"{left},{right}",
            "--seeds", str(GATE_SEED_PAIRS),
            "--turns", str(GATE_TURNS),
            "--map", map_name,
            "--out", str(out_dir),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise SystemExit(f"arena failed on {map_name}:\n{result.stderr[-2000:]}")

    report = (out_dir / "ARENA_REPORT.md").read_text(encoding="utf-8")
    found = _SWEEPS_RE.search(report)
    if not found:
        raise SystemExit(f"no sweep line in {out_dir / 'ARENA_REPORT.md'}")
    first, first_n, second, second_n = found.groups()
    counts = {first: int(first_n), second: int(second_n)}
    return counts.get(left, 0), counts.get(right, 0)


def screen(map_name: str) -> dict:
    """Both axes for one map, with the verdict."""
    axes = {}
    qualifies = True
    for label, left, right in AXES:
        with tempfile.TemporaryDirectory(prefix="soe_screen_") as tmp:
            a, b = run_axis(map_name, left, right, Path(tmp))
        p = sign_test(a, b)
        separates = p < ALPHA
        qualifies = qualifies and separates
        axes[label] = {
            "left": left, "right": right,
            "sweeps": [a, b], "p": p, "separates": separates,
        }
    return {"map": map_name, "axes": axes, "qualifies": qualifies}


def generate(seed: int, relief: str, sea_rule: str, out: Path) -> None:
    result = subprocess.run(
        [
            sys.executable, str(REPO_ROOT / "scripts" / "generate_world.py"),
            "--seed", str(seed),
            "--towns", str(GATE_TOWNS),
            "--regions", str(GATE_REGIONS),
            "--relief", relief,
            "--sea-rule", sea_rule,
            "--out", str(out),
        ],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise SystemExit(f"generation failed for seed {seed}:\n{result.stderr[-2000:]}")


def parse_seeds(spec: str) -> list[int]:
    seeds: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            seeds.extend(range(int(lo), int(hi) + 1))
        elif part:
            seeds.append(int(part))
    return seeds


def describe(result: dict) -> str:
    bits = []
    for label, axis in result["axes"].items():
        a, b = axis["sweeps"]
        mark = "separates" if axis["separates"] else "FLAT"
        bits.append(f"{label} {a}-{b} p={axis['p']:.2g} {mark}")
    verdict = "QUALIFIES" if result["qualifies"] else "no"
    return f"{result['map']:34} {' | '.join(bits):64} {verdict}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--seeds", default="1-8", help="e.g. 1-12 or 1,4,9")
    parser.add_argument("--relief", default="fbm")
    parser.add_argument("--sea-rule", default="detour")
    parser.add_argument(
        "--existing", default="", help="screen a map already in maps/ and stop"
    )
    parser.add_argument(
        "--keep-best",
        action="store_true",
        help="leave the first qualifying candidate in maps/ instead of deleting it",
    )
    args = parser.parse_args(argv)

    if args.existing:
        print(describe(screen(args.existing)))
        return 0

    print(
        f"screening {args.relief}/{args.sea_rule} candidates at "
        f"{GATE_TOWNS} towns, {GATE_SEED_PAIRS} pairs x {GATE_TURNS} turns\n"
    )
    results = []
    kept: str | None = None
    for seed in parse_seeds(args.seeds):
        name = f"calib12_{args.relief}_s{seed}.json"
        path = MAPS_DIR / name
        generate(seed, args.relief, args.sea_rule, path)
        try:
            result = screen(name)
            result["seed"] = seed
            result["roads"] = len(json.loads(path.read_text(encoding="utf-8"))["roads"])
            results.append(result)
            print(describe(result) + f"  ({result['roads']} routes)")
            if result["qualifies"] and args.keep_best and kept is None:
                kept = name
                continue
        finally:
            if path.exists() and path.name != kept:
                path.unlink()

    passing = [r for r in results if r["qualifies"]]
    print(f"\n{len(passing)} of {len(results)} candidates qualify on both axes")
    if kept:
        print(f"kept {MAPS_DIR / kept}")
    elif passing:
        print("re-run with --keep-best to keep the first that qualifies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
