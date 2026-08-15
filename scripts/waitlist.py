"""
Waitlist ledger: the operator's view of the Closed Coach Alpha funnel.

The public form is not the alpha roster. Applications land in a form vendor and
are merged here, into one CSV the operator owns. This tool answers the three
questions the field plan actually asks:

    who still needs an answer, what state are we in, and who gets a code.

Usage:
    python -m scripts.waitlist init
    python -m scripts.waitlist ingest export.csv [--dry-run]
    python -m scripts.waitlist status [--posted YYYY-MM-DD]
    python -m scripts.waitlist due [--warn 5]
    python -m scripts.waitlist mark <contact> <status> [--note TEXT]
    python -m scripts.waitlist invite <contact> <inv_id>
    python -m scripts.waitlist show <contact>

The ledger lives at private/ledger.csv, which is gitignored. It holds real
names, handles, and doctrine sentences collected under a privacy notice that
promises they are not published. Do not move it inside the tracked tree, and do
not paste its contents into a channel.

Rules enforced here come from docs/MARKETING_CLOSED_ALPHA.md and
docs/LAUNCH_OPERATIONS.md:

  - Same contact is one row. A second submit updates the doctrine and the
    timestamp; it does not duplicate the person.
  - Source comes from the tagged URL, never from the applicant.
  - Rows whose contact is not an X or Discord handle are discarded, as are
    doctrines under 12 characters and any row with the honeypot filled.
  - Every applicant hears back within 7 days, either way. `due` exists to keep
    that promise, and warns at 5.

Exit code 0 = ran, 1 = refused (bad input, unknown contact, breached promise).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = REPO_ROOT / "private" / "ledger.csv"

# The card's minimum columns, plus the two operations needs: an optional email
# (the invite has to reach them) and when we answered (the 7-day promise).
COLUMNS = [
    "received_at", "name", "contact", "email", "doctrine",
    "source", "status", "replied_at", "invite_id", "notes",
]

STATUSES = ["new", "maybe", "yes", "no", "invited", "claimed"]
DECIDED = {"yes", "no", "maybe"}
SOURCES = {"hn", "x", "reddit", "other"}

MIN_DOCTRINE = 12
CAP = 30
MINIMUM_INVITES = 20
DEPLOY_AT = 5
REPLY_PROMISE_DAYS = 7

# Vendor exports do not agree on header names. Match on a lowercased substring,
# most specific first, and report anything left unmatched instead of guessing.
FIELD_HINTS = [
    ("received_at", ["submitted at", "submitted", "received", "timestamp", "date", "created"]),
    ("name", ["name"]),
    ("contact", ["x or discord", "discord", "handle", "contact"]),
    ("email", ["email", "e-mail"]),
    ("doctrine", ["doctrine", "sentence"]),
    ("source", ["src", "source"]),
    ("honeypot", ["company", "honeypot"]),
]


def contact_key(contact: str) -> str:
    """One person, one key. Case and a leading @ are not identity."""
    return contact.strip().lstrip("@").lower()


def looks_like_handle(value: str) -> bool:
    """An X or Discord handle. Mirrors the check on the page."""
    v = value.strip()
    if len(v) < 2 or len(v) > 80:
        return False
    if re.search(r"\s", v):
        return False
    if re.match(r"^https?:", v, re.I) or "/" in v:
        return False
    if re.search(r"@[\w.-]+\.[a-z]{2,}$", v, re.I):  # an email address
        return False
    return bool(re.match(r"^@?[\w.#-]{2,}$", v))


def now_stamp() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def parse_stamp(value: str) -> dt.datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    for parse in (
        lambda v: dt.datetime.fromisoformat(v),
        lambda v: dt.datetime.strptime(v, "%Y-%m-%d %H:%M:%S"),
        lambda v: dt.datetime.strptime(v, "%Y-%m-%d"),
        lambda v: dt.datetime.strptime(v, "%d/%m/%Y %H:%M"),
        lambda v: dt.datetime.strptime(v, "%m/%d/%Y %H:%M"),
    ):
        try:
            stamp = parse(value)
        except ValueError:
            continue
        return stamp if stamp.tzinfo else stamp.astimezone()
    return None


def days_since(value: str) -> float | None:
    stamp = parse_stamp(value)
    if stamp is None:
        return None
    return (dt.datetime.now().astimezone() - stamp).total_seconds() / 86400


def load(ledger: Path) -> list[dict]:
    if not ledger.exists():
        return []
    with ledger.open(newline="", encoding="utf-8") as handle:
        return [{c: (row.get(c) or "") for c in COLUMNS} for row in csv.DictReader(handle)]


def save(ledger: Path, rows: list[dict]) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    tmp = ledger.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: r.get("received_at", "")))
    tmp.replace(ledger)


def find_row(rows: list[dict], contact: str) -> dict | None:
    key = contact_key(contact)
    matches = [r for r in rows if contact_key(r["contact"]) == key]
    return matches[0] if matches else None


# ---------------------------------------------------------------- commands


def cmd_init(args: argparse.Namespace) -> int:
    ledger = args.ledger
    if ledger.exists():
        print(f"{ledger} already exists, {len(load(ledger))} rows. Nothing changed.")
        return 0
    save(ledger, [])
    print(f"Created {ledger}")
    print("It is gitignored. Keep it that way: it holds real names and handles.")
    return 0


def map_headers(headers: list[str]) -> tuple[dict[str, str], list[str]]:
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for field, hints in FIELD_HINTS:
        for hint in hints:
            match = next(
                (h for h in headers if h not in used and hint in h.strip().lower()),
                None,
            )
            if match:
                mapping[field] = match
                used.add(match)
                break
    return mapping, [h for h in headers if h not in used]


def cmd_ingest(args: argparse.Namespace) -> int:
    export = args.export
    if not export.exists():
        print(f"No such export: {export}", file=sys.stderr)
        return 1

    with export.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        incoming = list(reader)

    mapping, unmatched = map_headers(headers)
    missing = [f for f in ("name", "contact", "doctrine") if f not in mapping]
    if missing:
        print(f"Cannot read {export.name}: no column matched {', '.join(missing)}.",
              file=sys.stderr)
        print(f"Columns seen: {', '.join(headers)}", file=sys.stderr)
        return 1
    if unmatched:
        print(f"note: ignoring unmapped columns: {', '.join(unmatched)}")

    rows = load(args.ledger)
    added = updated = 0
    discarded: list[str] = []

    for raw in incoming:
        def field(name: str) -> str:
            return (raw.get(mapping[name], "") or "").strip() if name in mapping else ""

        contact = field("contact")
        doctrine = field("doctrine")
        name = field("name")

        if field("honeypot"):
            discarded.append(f"{contact or name or '?'}: honeypot filled")
            continue
        if not looks_like_handle(contact):
            discarded.append(f"{contact or name or '?'}: not an X or Discord handle")
            continue
        if len(doctrine) < MIN_DOCTRINE:
            discarded.append(f"{contact}: doctrine under {MIN_DOCTRINE} characters")
            continue

        source = field("source").lower()
        if source not in SOURCES:
            source = "other"
        received = field("received_at") or now_stamp()

        existing = find_row(rows, contact)
        if existing is None:
            rows.append({
                "received_at": received, "name": name, "contact": contact,
                "email": field("email"), "doctrine": doctrine, "source": source,
                "status": "new", "replied_at": "", "invite_id": "", "notes": "",
            })
            added += 1
        else:
            # Same contact is one row: a second submit updates the doctrine and
            # the timestamp, and never resets a decision already made. Only a
            # *later* submit wins, so the merge does not depend on the export
            # being in chronological order, and re-ingesting is a no-op.
            new_at = parse_stamp(received)
            old_at = parse_stamp(existing["received_at"])
            newer = old_at is None or (new_at is not None and new_at >= old_at)
            if newer and existing["doctrine"] != doctrine:
                existing["doctrine"] = doctrine
                existing["received_at"] = received
                updated += 1
            elif newer:
                existing["received_at"] = received
            if name and newer:
                existing["name"] = name
            if field("email") and not existing["email"]:
                existing["email"] = field("email")

    if args.dry_run:
        print(f"dry run: {added} new, {updated} updated, {len(discarded)} discarded")
    else:
        save(args.ledger, rows)
        print(f"{added} new, {updated} updated, {len(discarded)} discarded "
              f"-> {args.ledger} ({len(rows)} rows)")

    for note in discarded:
        print(f"  discarded {note}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    rows = load(args.ledger)
    if not rows:
        print("Ledger is empty. State: waiting on `first application`.")
        return 0

    by_status = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    by_source = {}
    for row in rows:
        by_source[row["source"] or "other"] = by_source.get(row["source"] or "other", 0) + 1

    yes = by_status["yes"] + by_status["invited"] + by_status["claimed"]
    invited = by_status["invited"] + by_status["claimed"]
    claimed = by_status["claimed"]
    unanswered = sum(1 for r in rows if not r["replied_at"])

    print(f"{len(rows)} applications")
    print("  by status  " + "  ".join(f"{s}={by_status[s]}" for s in STATUSES))
    print("  by source  " + "  ".join(f"{k}={v}" for k, v in sorted(by_source.items())))
    print(f"  unanswered {unanswered}")
    print()

    if claimed:
        state = "first invite claimed"
    elif yes >= MINIMUM_INVITES:
        state = "20 accepted / open official cohort"
    elif yes >= DEPLOY_AT:
        state = "five qualified / deploy"
    else:
        state = "first application"
    print(f"State: {state}")

    if yes < DEPLOY_AT:
        print(f"  {DEPLOY_AT - yes} more `yes` to deploy infrastructure "
              f"(roster stays idle, no codes)")
    elif yes < MINIMUM_INVITES:
        print(f"  {MINIMUM_INVITES - yes} more `yes` to open /ops/alpha. "
              f"Do not emit inv_ before then.")
    else:
        print(f"  /ops/alpha may open. Cap {CAP}; {CAP - invited} codes left to issue.")
    if unanswered:
        print(f"  {unanswered} unanswered - run `due`")

    # Stall branches from LAUNCH_OPERATIONS.md, only when we know the post date.
    if args.posted:
        elapsed = days_since(args.posted)
        if elapsed is not None:
            if len(rows) < 5 and elapsed >= 14:
                print(f"\nSTALL: {len(rows)} applications {elapsed:.0f} days after the "
                      f"last post. Stop adding surface; re-read what did arrive.")
            elif DEPLOY_AT <= yes < MINIMUM_INVITES and elapsed >= 30:
                print(f"\nSTALL: {yes} yes at {elapsed:.0f} days. Run the cohort with "
                      f"what exists. Do not lower the bar to reach {MINIMUM_INVITES}.")
    return 0


def cmd_due(args: argparse.Namespace) -> int:
    rows = [r for r in load(args.ledger) if not r["replied_at"]]
    if not rows:
        print("Nobody is waiting on an answer.")
        return 0

    aged = []
    for row in rows:
        aged.append((days_since(row["received_at"]), row))
    aged.sort(key=lambda pair: -(pair[0] if pair[0] is not None else 0))

    breached = 0
    print(f"{len(rows)} awaiting an answer (promise: {REPLY_PROMISE_DAYS} days, "
          f"warn at {args.warn})\n")
    for elapsed, row in aged:
        if elapsed is None:
            flag, age = "  ", "  ?  "
        else:
            age = f"{elapsed:4.1f}d"
            if elapsed >= REPLY_PROMISE_DAYS:
                flag, breached = "!!", breached + 1
            elif elapsed >= args.warn:
                flag = " !"
            else:
                flag = "  "
        print(f"{flag} {age}  {row['contact']:<24} {row['source']:<7} "
              f"{row['doctrine'][:52]}")

    if breached:
        print(f"\n{breached} past the {REPLY_PROMISE_DAYS}-day promise. "
              f"Answer them before posting anything new.")
        return 1
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    rows = load(args.ledger)
    row = find_row(rows, args.contact)
    if row is None:
        print(f"No row for {args.contact}", file=sys.stderr)
        return 1
    if args.status not in STATUSES:
        print(f"Unknown status {args.status}. One of: {', '.join(STATUSES)}",
              file=sys.stderr)
        return 1

    row["status"] = args.status
    if args.note:
        row["notes"] = args.note
    # Marking a decision normally means you have just told them. --not-replied
    # is for deciding privately before writing.
    if args.status in DECIDED and not row["replied_at"] and not args.not_replied:
        row["replied_at"] = now_stamp()
        stamped = " (replied stamped)"
    else:
        stamped = ""
    save(args.ledger, rows)
    print(f"{row['contact']}: {args.status}{stamped}")
    return 0


def cmd_invite(args: argparse.Namespace) -> int:
    rows = load(args.ledger)
    row = find_row(rows, args.contact)
    if row is None:
        print(f"No row for {args.contact}", file=sys.stderr)
        return 1

    issued = sum(1 for r in rows if r["invite_id"])
    accepted = sum(1 for r in rows if r["status"] in ("yes", "invited", "claimed"))

    # The card's hardest line: "Opening /ops/alpha or emitting inv_ before
    # twenty people are accepted" is a non-goal, and five yeses deploy
    # infrastructure only. This refusal is not overridable by --force.
    if accepted < MINIMUM_INVITES:
        print(f"{accepted} accepted. Codes are not emitted before "
              f"{MINIMUM_INVITES}. Five yeses deploy infrastructure only; "
              f"/ops/alpha stays closed until the official cohort opens.",
              file=sys.stderr)
        return 1
    if issued >= CAP:
        print(f"Cap {CAP} reached; {issued} codes issued. Refusing.", file=sys.stderr)
        return 1
    if row["status"] not in ("yes", "invited", "claimed"):
        print(f"{row['contact']} is `{row['status']}`, not `yes`. "
              f"Mark them yes first.", file=sys.stderr)
        return 1
    if not row["email"] and not args.force:
        print(f"{row['contact']} has no email, and a code cannot reliably reach "
              f"an X or Discord handle. Add one, or pass --force.", file=sys.stderr)
        return 1

    row["invite_id"] = args.invite_id
    row["status"] = "invited"
    save(args.ledger, rows)
    print(f"{row['contact']}: invited, {args.invite_id} ({issued + 1}/{CAP})")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    row = find_row(load(args.ledger), args.contact)
    if row is None:
        print(f"No row for {args.contact}", file=sys.stderr)
        return 1
    for column in COLUMNS:
        print(f"{column:>12}  {row[column]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    p = sub.add_parser("ingest", help="merge a form vendor CSV export")
    p.add_argument("export", type=Path)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("status", help="counts, funnel state, and what unblocks the next")
    p.add_argument("--posted", help="date of the last post, for the stall checks")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("due", help="who is waiting on an answer")
    p.add_argument("--warn", type=float, default=5.0)
    p.set_defaults(func=cmd_due)

    p = sub.add_parser("mark", help="set a status")
    p.add_argument("contact")
    p.add_argument("status")
    p.add_argument("--note")
    p.add_argument("--not-replied", action="store_true")
    p.set_defaults(func=cmd_mark)

    p = sub.add_parser("invite", help="record an issued inv_ code")
    p.add_argument("contact")
    p.add_argument("invite_id")
    p.add_argument("--force", action="store_true", help="issue without an email")
    p.set_defaults(func=cmd_invite)

    p = sub.add_parser("show", help="print one row")
    p.add_argument("contact")
    p.set_defaults(func=cmd_show)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
