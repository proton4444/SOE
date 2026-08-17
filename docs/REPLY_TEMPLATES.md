# Reply templates

Status: **drafted; nothing sent**
Date: 2026-08-15, model reply added 2026-08-16
Governed by: [`MARKETING_CLOSED_ALPHA.md`](MARKETING_CLOSED_ALPHA.md),
[`LAUNCH_OPERATIONS.md`](LAUNCH_OPERATIONS.md) — "Reply playbook"

Paste-ready text for every reply the funnel needs. The playbook in
`LAUNCH_OPERATIONS.md` decides *what is true*; this decides *what gets typed*,
so an answer takes ten seconds and never drifts off-card.

## Rules that bind every template

- Send from `operator@<domain>`, never a personal inbox. Confirm the `From:`
  header once before the first application arrives.
- Never add a prize, a ranking, a leaderboard, a live server address, or a date
  that is not decided. If the season date is unknown, say it is unknown.
- Accepted is not invited. A code is emitted only when twenty people are
  accepted and the official cohort opens. Do not imply a code is coming on a
  particular day, because it is not scheduled.
- Every applicant hears back within 7 days, either way. Run
  `python -m scripts.waitlist due` before writing anything new.
- After sending, mark the row:
  `python -m scripts.waitlist mark <contact> <status> --note "<one line>"`

`<angle brackets>` are placeholders. Replace all of them.

## 1. Acknowledgement, on submit

Only if the form vendor sends it automatically. Do not hand-send this as well
as a decision; one message is better than two.

```text
Thanks — your application for the Closed Coach Alpha is in.

We read every application. You will hear back within 7 days, either way.

Nothing else is needed from you now.
```

## 2. Accepted

Status `yes`. Deliberately promises no date.

```text
Hi <name>,

You have a seat in the Closed Coach Alpha.

Your doctrine sentence is what got read, so to be plain about what happens
next: you will write a structured doctrine, freeze it, and then not touch
the match. Three training matches per frozen version, then paired duels and
one observable final. Same model and limits for everyone. No payment, no
prize, no public ranking.

Seats are filled one at a time and the cohort opens when it is full, so I
cannot give you a date yet. When it opens you will get a single invite code
at this address. If you would rather it went somewhere else, tell me where.

<operator>
```

## 3. Waitlisted

Status `maybe`. Honest about the cap without ranking anyone.

```text
Hi <name>,

Thank you for applying to the Closed Coach Alpha. I am holding your
application rather than turning it down.

The cap is 30 and I would rather run a small alpha well than a large one
badly. If a seat frees up, or the cohort widens, I will write to you before
anyone new is asked.

<operator>
```

## 4. Declined

Status `no`. Short, no false encouragement, no critique of their doctrine.

```text
Hi <name>,

Thank you for applying to the Closed Coach Alpha. I am not able to offer you
a seat this time.

The cap is 30 and there is nothing else to read into it. If this opens up
beyond the closed alpha, the page is where it will be announced.

<operator>
```

## 5. Incomplete — no usable handle

Sent when the application cannot be accepted as written. The ledger discards
these, so this reply is the only way the person is recovered.

```text
Hi <name>,

I have your application, but I need an X or Discord handle to place it — the
contact field had <what was there> and I cannot reach you on it.

Reply with your handle and I will attach it. Your doctrine sentence is
already saved, so you do not need to write it again.

<operator>
```

## 6. Invite, at cohort open

Only after twenty are accepted and `/ops/alpha` is open. One code, one person.

```text
Hi <name>,

The Closed Coach Alpha is open and this is your seat.

Invite code: <inv_id>
Redeem at: <url>

The code is yours alone and works once. If it does not redeem, tell me
before trying it again anywhere else.

<operator>
```

Then record it, which refuses if the cohort is not open or the cap is reached:

```text
python -m scripts.waitlist invite <contact> <inv_id>
```

## 7. In a public thread — "can I try it now?"

Keeps the sentence, the tagged URL, and the three facts. Everything else may go.

```text
Not yet — it is invite only, 30 seats, no prize. You write the doctrine,
freeze it, and watch an agent try to rule a world you cannot touch.

<host>/?src=<channel>
```

Use the tagged URL for the channel the thread is in, so attribution stays
honest.

## 8. In a public thread — "which model?"

Closed 2026-08-16. Name it; refusing reads worse than answering, and the
forbidden list covers the replay file and the page, not conversation.

```text
Claude Haiku 4.5 — the same model in every seat, with the same limits.
```

That is the whole answer. Do not extend it with the price, the prompt, the
rate limits, or the provider's plan names, and do not attach the proof line:
the gate's 7,200 turns ran on a different model, so the two sentences
together would claim a test nobody ran. If the same thread asks about the
gate, answer that separately, in its own sentence.

## 9. Deletion request

The privacy notice promises this, so it has to be quick and complete.

```text
Hi <name>,

Done — your row is deleted: name, handle, and doctrine sentence. Nothing of
it is kept, and it was never published or shared.

If you want back in later, the page is still there.

<operator>
```

Delete the row in the form vendor, then re-export and re-ingest so the local
ledger matches. Confirm the row is gone from a fresh export before replying,
not just from the vendor's screen.

## Related

- Locked copy and the compression table:
  [`MARKETING_CLOSED_ALPHA.md`](MARKETING_CLOSED_ALPHA.md)
- Identity, mail trap, and the reply playbook:
  [`LAUNCH_OPERATIONS.md`](LAUNCH_OPERATIONS.md)
- The posts these replies follow: [`OUTREACH_POSTS.md`](OUTREACH_POSTS.md)
