# Closed Alpha Public Face

Status: **contract locked; replay and model gates closed; poster page built;
hosting and form vendor gates still open; spend ceiling undecided; posts not
sent**  
Date: 2026-08-14, model gate closed 2026-08-16  
Depends on: [`ROADMAP.md`](ROADMAP.md) Phase 4, [`READINESS_AND_MARKET.md`](READINESS_AND_MARKET.md), [`../configs/alpha/closed.json`](../configs/alpha/closed.json)

This is the field plan for Phase 4. Nobody outside the repo knows the
project exists. The next increment is a public object strangers can open,
not more product surface.

The alpha **instrument** is feature-ready: roster, training cap, debrief,
share link, and observable final exist. That is not the same as
operational readiness. The 20-agent control-plane test used a fake model
and one-turn boards. It proves the ledger, not a live LLM season.

Revised the same day against the field-plan review. Four gaps are closed
here as contract: separate milestones, a sanitized replay export, a map
visual boundary, and form privacy/attribution/abuse rules. They are not
yet built.

## Objective

Fill the Phase 4 funnel so an official cohort of 20–30 coaches can be
invited under `configs/alpha/closed.json` (`minimum_invites`: 20,
`capacity`: 30).

Success is not impressions. Success is named people who write a doctrine
sentence, are accepted, and claim an invite.

This plan does not complete Phase 4. Phase 4 go criteria stay those in
the roadmap. This plan only creates the empty funnel’s first public face
and the first claimed invite.

## States

Keep these separate. Crossing one is not crossing the next.

| State | Meaning | Not the same as |
|---|---|---|
| `poster live` | Public URL shows the locked sentence, the atlas board, and a working form. | Outreach. Invites. |
| `first application` | One real human row is in the ledger. | Qualified. Invited. |
| `five qualified / deploy` | Five ledger rows are `yes`. Controlled beta is stood up and the preflight passes. Roster stays `idle`. No `inv_` yet. | Official cohort. |
| `20 accepted / open official cohort` | Twenty rows are `yes`. `/ops/alpha` opens. Codes are emitted one by one, cap 30. | Field plan complete. |
| `first invite claimed` | One guest has redeemed an `inv_` code. | Season running. |
| `field plan complete` | Poster live, three tagged posts sent, twenty invites issued, at least one claimed, form still not wired to the roster. | Phase 4 go criteria. |

Deployment after five qualified people is allowed. Declaring the official
cohort started, or this plan complete, is not.

Rollback at every state is unpublishing the poster or disabling the form.
No game data or schema needs to change.

## Why this shape

Phase 4 is blocked on the field: roster `idle`, zero invitees. There is
no warm list.

The category line “AI agents compete” is already used by
[Agent Sports League](https://www.agentsportsleague.com/) and
[Agent Arena](https://arena.ai/leaderboard/agent?stream=top). The
distinctive offer is the coach loop: write a doctrine, freeze it, watch
an agent rule a world you cannot touch, debrief, iterate. Do not cite
Spartic as verified positioning evidence.

The 60-second trailer *The Living Atlas* is not finished. Do not wait
for it.

The live webapp stays invite-only. The public page is a poster, not a
client.

## Locked names

| Role | Name |
|---|---|
| Public product | Spoils of Empire |
| Campaign / page title | The Living Atlas |
| Mode offered | Coach League |
| Offer | Closed Coach Alpha, 30 seats |

Do not lead with `SOE`. It collides with an old Sony mark and means
nothing to a stranger.

## Locked sentence

> You don’t play the empire. You write its doctrine, freeze it, and watch an
> agent try to rule a world you cannot touch.

## Locked offer

Canonical card. The landing page must carry every bullet.

1. Invite only. Cap 30.
2. Same model and limits for everyone.
3. You write a structured doctrine. You do not write code. You do not
   issue orders during an official match.
4. Three training matches per frozen version.
5. Then paired duels and one observable final.
6. No payment, no prize, no public ranking.
7. Apply with: name, X or Discord, one sentence of doctrine, and an
   email if you want the invite code sent there.

Do not invent a second offer. Channels may compress only as the table
below allows.

> **Bullet 2 has a name now, decided 2026-08-16: Claude Haiku 4.5.** The
> bullet does not change — the card's claim is *sameness*, not the name, and
> the name belongs in a reply rather than in copy. What changed is that the
> claim is now enforced: the frozen regulation
> (`configs/competition/coach_league.json`) names the model, and a doctrine
> asking for a different one is refused entry. Asked in a thread, name it
> plainly and stop there: no price, no prompt, no rate limits. The gate is
> recorded in `LAUNCH_OPERATIONS.md`, **Model gate: closed**, including the
> one thing that surprises people — a claude.ai subscription is not API
> access, and the seats bill through the Anthropic API on its own key.

> **Amendment 1, accepted 2026-08-15.** Bullet 7 previously read "Apply
> with: name, X or Discord, one sentence of doctrine." The email is
> optional and a blank submission stays valid, so the offer is unchanged
> in substance. It exists because the card otherwise has a last-mile
> problem: X DMs need a follow-back and Discord DMs can be closed to
> non-friends, so an accepted coach could be unreachable at exactly the
> moment there is a code to deliver. See **Amendments** in
> `LAUNCH_OPERATIONS.md`.

### Permitted compression

| Surface | Must keep | May drop |
|---|---|---|
| Landing page | All seven bullets, locked sentence, proof line, privacy notice | Nothing |
| Hacker News | Sentence meaning, invite-only, 30 seats, same model/limits, three trainings, paired duels and one final, no prize, no public ranking, proof line, tagged URL | The apply-with bullet (the form is on the page) |
| X | Locked sentence, invite-only, 30 seats, no prize, no public ranking, tagged URL | Trainings, duels, same-model, apply-with |
| Reddit | Locked offer bullets 1–6, proof line, tagged URL | Apply-with |
| Replies / DMs | Locked sentence + tagged URL + “invite only, 30 seats, no prize” | Everything else, if the URL is present |

A channel post that adds a prize, a ranking, a “play now”, or a live
server address is off-card. Discard it.

## Proof line

Use exactly:

> The official gate completed 7,200 model turns across two 40-pair tests.

That is 2,400 calls in
`games/arena/run-20260813-141002-20e66d` plus 4,800 in
`games/arena/run-20260813-153826-f562a8`. Do not imply one 40-pair run
contained all 7,200 turns.

A second optional clause is allowed on HN and the page only:

> Two written doctrines produced different games, not just different prose.

Do not say the doctrines are balanced. `expansionist-v1` won 80–0
against `consolidation-v1` because the tie-break rewards territory and
soldiers and the two never fought. That is not a ranking.

**The proof line is not evidence about the alpha's model.** Those 7,200
turns ran on `openai/gpt-4o-mini`; the alpha runs on Claude Haiku 4.5. The
sentence stays exactly as written and stays true — it says what the gate
completed, not what the alpha runs — but it must never appear in the same
breath as the model's name, because together they claim a test that was
never run. If a thread asks both questions, answer them in separate
sentences and do not join them.

Re-running the gate on Haiku is what would make it evidence about the
alpha's model. That costs real money under a ceiling nobody has set, and
on Anthropic it also fails the gate's own cost criterion — Anthropic bills
tokens and declares no dollars. See `LAUNCH_OPERATIONS.md`, **Model gate**.

## Non-goals

- Public signup, accounts, or an open server.
- A Three.js game client attached to the live engine.
- A multi-page marketing site, blog, or docs portal.
- Token, prize, betting, or “win money with your bot” copy.
- Steam, mobile, or general-strategy advertising.
- Waiting for the trailer master.
- Opening `/ops/alpha` or emitting `inv_` before twenty people are
  accepted. Five yeses deploy infrastructure only.
- Turning the public replay or the observable final into a permanent
  ranking or a scoring experiment.
- Inventing coastlines, continents, or elevation the map does not have.
- Shipping `decisions/`, `orders/`, reports, provider metadata, or raw
  arena bundles to the public page.

## Visual contract: atlas board

The board is generated from **`maps/starter_map.json`** — six cities with
fractional `x`/`y`, terrain labels, populations, grid references, regions,
port and magic-free flags, and roads with distances (including one sea
lane). It has no coastline, no
land polygon, and no elevation mesh. `webapp/mapview.py` draws traced
coastlines only when a paired geography file exists
(`soe_geography.json`). That file is not this map — for this one the app
falls back to a padded convex hull of the road-connected cities.

**Render what the app renders.**

- Place the twelve cities at their exact `x`/`y`, **on mapview’s own
  frame** — the app draws a 1300×1000 mile field into 1180×680 units, and
  that anisotropy is the map’s proportions. One scale on both axes renders
  the world 23% too narrow for its height, which is what made the board
  and the app read as two different places. Carry the population, grid
  reference, terrain, port and magic-free flags the map gives them.
- Draw the roads exactly as listed, with their mileage and movement
  cost. The movement cost is the engine’s own number, not a second
  formula.
- Draw each city as a **settlement**: a walled platform, roofed houses and a
  keep with a spire. A ruin loses its roofs and its spire and keeps the
  stump; a port gains a jetty. Stylised and out of scale on purpose, in
  the tradition of the little drawn towns on an estate map — a city has to
  be recognisable as one from across the board, not merely labelled as one.
- Give the landmass **a surface**: elevation interpolated from the twelve
  cities’ `terrain` labels, with fractal detail, falling to sea level at
  the shore. A city on hills stands on high ground because the ground is
  high, not because it wears a cone. Vertical is exaggerated, as a relief
  map’s always is, and the ground carries contour lines — shading alone
  cannot tell a reader whether a slope runs up or down.
- The heightmap is **baked**, by `scripts/build_elevation.py`, and shipped
  as `elevation.js`. Not computed in the browser: baking it makes the
  terrain identical on every machine, lets a test regenerate and compare
  it, and keeps the work off the reader’s phone. It is a visual output
  and nothing else — no order, no movement cost and no result reads a
  value from it.
- Because that surface is interpolated and the map has no elevation at
  all, **the page says so where it is drawn**, exactly as it does for the
  coast. The legend carries “relief interpolated from city terrain — high
  ground is data, contours are not”.
- Draw the landmass, its coast, the sea outside it, and the region
  names. The landmass must be **the polygon `webapp/mapview.py` computes
  for this map**, carried across by `scripts/build_public_board.py` —
  not a shore invented for the poster, and not a second computation of
  the same idea that can drift from the app’s. It is drawn as a **solid
  standing out of the water**, not a fill printed on a plate: a coast is
  an edge, and giving it a real one is what makes this a relief of a
  world rather than a picture of a map. The water is ruled; the land is
  not. The whole object is framed, so the sea is never cut off
  mid-picture — the board scales down to hold it.
- The hull is a **confine, not a coastline**. It is convex — for
  starter_map’s mainland, four points and four straight edges — and drawn
  as a shore it looks like the survey boundary it is. The shoreline is an
  **isoline of the heightfield** instead: the distance to the hull is
  perturbed by fractal noise before the coastal shelf is taken from it,
  and the ground goes on descending past it to a seabed. Where that
  surface crosses sea level is the coast, bays and headlands included.
  Nothing draws it; it is an intersection.
- The wobble is **biased inward**. A hull is the smallest convex shape
  containing its cities, so a real coast inside one mostly bites into it
  and only occasionally pushes a headland out — and a symmetric wobble
  puts land past the sheet it is printed on.
- Because that polygon is a road-connectivity confine and not a survey,
  **the page says so where it is drawn.** The legend carries
  “road-connected extent, not a surveyed coast”.
- Call this an **atlas relief board**. That name is allowed. “Continent”
  and “world map” are not — the board shows one landmass of a world, at
  a calibration size, and neither word is true of it.

The page may rotate or tilt the board.

> **Amendment 2, accepted 2026-08-17.** This section previously read
> “Render the coordinate topology that exists”, and forbade the rest:
> “Empty surrounding space stays empty. No sea, no implied landmass, no
> invented shore… It may not add geography.” The board therefore drew
> twelve mounds on blank paper while the map a coach opens in the app
> drew a named landmass, ports, populations, grid references and road
> mileages — the same twelve cities reading as two different worlds, and
> the public one reading as the emptier.
>
> What the old rule was protecting is real and is kept: the coastline is
> **not** surveyed, and a map that draws a shore is read as claiming one.
> The resolution is to draw it and say what it is, rather than to
> withhold it — the legend line above is part of the contract, not
> decoration, and the board is built from mapview’s own polygon so the
> two pictures cannot disagree about where the coast runs.
>
> The withheld fields (population, mile coordinates, grid references,
> regions, port and magic-free flags, road distances) now cross to the
> public page. They are map topology from a tracked, generated
> calibration map — not match data, and not the traced material the
> cleanroom excludes. Replay sanitization is untouched: see **Sanitized
> replay** below, which this amendment does not open.
>
> Applied in `scripts/build_public_board.py`, `board.js`, `board3d.js`,
> `atlas.js`, `atlas.css`, and guarded by `tests/test_public_board.py`.
> See **Amendments** in `LAUNCH_OPERATIONS.md`.

> **Amendment 3, accepted 2026-08-17.** Amendment 2 kept one line from the
> original rule: “elevation still comes from the twelve terrain labels and
> nowhere else”, which in practice meant a flat slab with twelve cones
> standing on it. That is what the board looked like — pins pushed into a
> plane — and it is not what the game’s world is.
>
> The landmass now carries an interpolated surface. Be exact about what
> that is: these maps carry terrain **labels** and no elevation
> whatsoever — no mesh, no heightfield, not one spot height. Which cities
> stand on hills is data. The shape of the ground between them is a
> plausible invention, deterministic from position so it is at least the
> same invention on every machine and every reload.
>
> Same resolution as the coast: draw it, and say on the page that it is
> implied. The legend line above is part of the contract. **Vertical is
> exaggerated** (×2.6) — true to scale, 60 units of hill across a
> 1300-unit vale is a 4.6% grade, which is geologically honest and
> visually nothing.
>
> **Amendment 4, accepted 2026-08-18.** The board moves from
> `calib_12.json` to `starter_map.json`, and its replay from the official
> gate match `AR031_ba` to an exhibition, `exh-ex017`.
>
> Reason: calib_12 is a calibration map and its terrain is nine plain, two
> hills and one desert — no mountains, no forest, no rivers, no sea lane.
> The board was rendering the most it could of a map that had almost
> nothing to render. starter_map has six cities carrying six terrains
> across all four population bands, and one sea lane, which makes it an
> **archipelago**: `compute_landmasses` does not join land across water,
> so Gullhaven is its own island and the board draws two masses.
>
> The cost, stated plainly: the caption changes from **"Official gate
> replay"** to **"Exhibition replay"**, and the page claims correspondingly
> less about that picture. It is generated by
> `export_public_replay exhibition`, scripted against scripted, with no
> model calls — deterministic, reproducible from the seed, and never
> described as gate evidence. The proof section is untouched: the official
> gate's 7,200 model turns are a separate claim and remain true.
>
> `configs/phase0_gate.json` is NOT touched. The engine's frozen gate is
> still calib_12 and its hashes are unchanged; this amendment moves what
> the poster draws, not what the gate measures.

## Sanitized replay

A replay cannot be copied from a bundle. `turns.jsonl` stores hashes and
seeds, not piece positions. Official runs also do not automatically
qualify as the poster match: the doctrine bundle recorded **zero
attacks and zero eliminations** in 80 games. It proves behavioral
difference. It does not prove a watchable war.

### Export

**Built 2026-08-14.** `soe/public_replay.py` (schema, sanitiser,
validator) and `scripts/export_public_replay.py` (reconstruction, audit,
exhibition). It:

1. Reconstructs one finished match by replaying recorded orders through
   the engine, checking every turn against the bundle's recorded
   `state_sha`. A divergence aborts the export.
2. Emits one static JSON file, schema `soe.public_replay.v1`.
3. Ships that file with the poster. The page never calls the live
   server and never reads the arena bundle.

It replays into a scratch `SOE_DATA_DIR`, so it never touches the beta
room store.

#### Engine drift: an official-gate replay needs its own commit

The card assumed the arena could replay a bundle at any time. It cannot
replay one *across a code change*. The bundles were recorded at
`1e47f9c` (competence) and `8bd4751` (doctrine); commit `269c9a4`,
"seventeen order bugs", then rewrote the parser and three resolution
phases. Replaying either bundle on today's engine diverges at turn 1 —
same orders, different resolution.

So an `official-gate` replay must be reconstructed on the engine that
produced it. `export` refuses the label when `HEAD` differs from the
bundle's `git_commit` and prints the worktree commands. A replay built
on a drifted engine is a new simulation of the same orders, not the
recorded match, and cannot carry the gate's name.

This also means the poster's replay file is an artefact to keep. It is
not cheaply regenerable once the worktree is gone.

Allowlisted schema:

```text
soe.public_replay.v1
  map          "calib_12.json"
  match_id     opaque id of the source game, not a path
  label        "exhibition" | "official-gate"
  turns        integer
  seats        [{id, label}]     public labels only; no model ids required
  result       {winner_seat, decided_by}
  frames[]
    turn
    pieces[]   {id, seat, city_id, kind}   kind in {character, stack}
    cities[]   {id, occupied_by[], secured_by}
```

`occupied_by` and `secured_by` are public ownership/occupation markers.
They are seat ids, not faction secrets.

### Forbidden in the file and on the page

- `decisions/`, `orders/`, player reports, raw bundle files
- provider names, API metadata, usage, latency, keys
- order text, rationale text, warning text
- gold, inventory, skills, health, messages, passwords
- report hashes, state hashes, seeds (the poster is not a benchmark)
- character personal names if they encode a player handle
- any path under `games/arena/`

### Leakage test

**Built.** `tests/test_public_replay.py`, 50 cases, in the suite. It
loads an exported JSON and fails if:

- a key exists outside the allowlist;
- a string matches order-like verbs in context (`Recruit`, `ATTACK`,
  `--- ORDERS ---`) or looks like a report;
- a value looks like a SHA-256, a seed integer, an API key, or a
  filesystem path;
- `label` is `official-gate` while the source match fails the visual
  bar below.

### Choosing the match

**Audit run 2026-08-14. Chosen: `AR031_ba` from the competence bundle
`run-20260813-141002-20e66d`, label `official-gate`, at
`webapp/static/public/replay.json`.**

Both official bundles were reconstructed in full, each at its own
commit — 160 games, every turn hash-checked against its bundle.

| Bundle | Games passing the visual bar | Best candidate | moves / contact / territory |
|---|---|---|---|
| competence `20e66d` | 32 of 80 | `AR031_ba` | 134 / 16 / 23 |
| doctrine `f562a8` | 26 of 80 | `AR031_ba` | 113 / 16 / 16 |

`AR031_ba` leads both. The competence version is the export: more
movement, more territorial change, warning rate 0.000, and it is one of
the few candidates where the two seats ever stand in the same city.

No exhibition was needed. The card's fallback stays available
(`export_public_replay.py exhibition`) and unused.

One correction to the note above: the doctrine bundle is *not* devoid of
watchable games — 26 of its 80 clear the bar. "Zero attacks and zero
eliminations" remains true and is a different claim; co-occupation,
movement, and territorial change all happen without a resolved attack.
The doctrine bundle was not chosen because the competence bundle scored
higher, not because it had nothing.

Re-running the audit, for a different match or a new bundle:

```text
git worktree add ../soe-replay <bundle git_commit>
cp soe/public_replay.py ../soe-replay/soe/
cp scripts/export_public_replay.py ../soe-replay/scripts/
cd ../soe-replay
python -m scripts.export_public_replay audit <bundle>
python -m scripts.export_public_replay export <bundle> <game_id> -o <out>
```

Each candidate is scored on:

- visible movement (pieces change `city_id` across frames);
- contact (two seats occupy the same city on the same turn, or a
  secured marker flips after both were present);
- territorial change (`secured_by` changes);
- warning rate not anomalous versus that run’s published rate.

Do **not** default to `run-20260813-153826-f562a8`. Audit at least:

- the competence bundle `run-20260813-141002-20e66d` (`scripted:military`
  recorded attacks; the LLM seat did not);
- the doctrine bundle, only if some game still shows movement and
  territorial change worth watching;
- a local scripted-versus-scripted match on `calib_12.json`, labeled
  `exhibition`, if no official-gate game meets the visual bar.

An exhibition replay is allowed on the poster. It must be labeled as
such. It is not evidence of the 7,200-turn gate.

## Waitlist ledger

The public form is not the alpha roster. Applications land in a ledger
the operator reads. `/ops/alpha` stays closed until the
`20 accepted / open official cohort` state.

Minimum columns:

| Column | Meaning |
|---|---|
| received_at | when they applied |
| name | as written |
| contact | X or Discord |
| doctrine | the one sentence |
| source | `hn` / `x` / `reddit` / `other`, from the tagged URL, not from the applicant |
| status | `new` / `maybe` / `yes` / `no` / `invited` / `claimed` |
| invite_id | filled only after `/ops/alpha` emits `inv_` |
| notes | one line |

Same contact = one row. A second submit updates the doctrine and the
timestamp, it does not duplicate the person.

### Attribution

One public path, three tagged entry URLs:

- `https://<host>/?src=hn`
- `https://<host>/?src=x`
- `https://<host>/?src=reddit`

The page copies `src` into a hidden form field. The ledger `source`
column is that field, default `other`. Applicants do not pick a source.
HN, X, and Reddit posts each use their own tagged URL.

### Privacy notice

The form shows, above the submit button:

> We collect your name, public handle, and doctrine sentence only to
> decide Closed Coach Alpha invites. The operator of this experiment
> reads them. They are not sold, not published, and not used as
> marketing quotes without your later consent. We keep a row until the
> closed alpha ends, then 90 days, unless you ask us to delete it
> sooner. To delete, write to the operator contact on this page.

The operator contact is a dedicated address or handle, not a personal
inbox mixed with the live game.

### Abuse controls

- Honeypot field, hidden from humans.
- Minimum doctrine length: 12 characters, one word is not enough.
- Rate limit: one accepted submit per contact per day; coarse IP cap
  on the form vendor.
- Discard rows whose contact is not an X or Discord handle.
- The operator can disable the form without touching the game.

### Form vendor gate

Do not pick Tally, Google Form, or Airtable on taste. Pick the first
vendor that can do all of:

- custom domain or embed on the poster host;
- hidden `src` field filled from the query string;
- export of the full ledger;
- deletion of a single row by the operator;
- operator-only access, not a shared public sheet;
- the honeypot or an equivalent bot check.

Claude may build the form after that check. The operator owns the
sheet.

## Hosting gate

Do not pick a host on taste. Pick the first host that can do all of:

- HTTPS on a name the operator controls, or a temporary page host
  with a name that can later redirect;
- static files only (HTML, JS, CSS, textures, one replay JSON);
- unpublish in one step;
- no coupling to `scripts/start_beta.ps1`.

A Cloudflare or GitHub page is enough for `poster live`. A custom
domain is preferred once ownership is confirmed. Confirm ownership
before printing the name on posts.

## Outreach

Borrow three rooms, once. Post only after `poster live` and after one
test submit from each tagged URL has landed in the ledger with the
right `source`.

**Hacker News** — tagged `?src=hn`

Title: `Show HN: Spoils of Empire – a grand strategy game you coach, not play`

Body:

```text
Spoils of Empire is a deterministic play-by-email grand strategy engine.
You do not issue orders. You write a doctrine, freeze it, and an agent
plays the world without you.

Closed Coach Alpha, 30 seats. Same model and limits for everyone. Three
training matches per version, then paired duels and one observable final.
No prize, no public ranking.

The official gate completed 7,200 model turns across two 40-pair tests.
Two written doctrines produced different games, not just different prose.

Landing page and application: <URL>?src=hn
```

**X** — tagged `?src=x`

```text
You don’t play the empire.
You write its doctrine, freeze it, and watch an agent try to rule a
world you cannot touch.

Closed Coach Alpha. 30 seats. No prize. No public ranking.

<URL>?src=x
```

Attach a 10–20s silent loop of the atlas board when it exists. If it
does not, post the text and the tagged URL. Do not wait for video.

**Reddit** (`r/promptengineering` or `r/LocalLLaMA`, one only) — tagged
`?src=reddit`

Title: `I don’t need another chatbot. I need to know if my instructions survive 30 turns of war.`

Body: locked offer bullets 1–6, the proof line, `<URL>?src=reddit`.
No Discord dump. No “check out my startup”.

Claude drafts the final posts from this card and can open the target
pages. The operator presses send. Claude does not invent a new pitch.

After the three posts, Claude’s only job is replies: every “how do I
try this?” gets the tagged URL for that thread; every completed
application is a ledger row.

## Infrastructure handoff

At `five qualified / deploy`:

1. Deploy the controlled beta (`scripts/start_beta.ps1` + HTTPS
   terminator). Do not publish port 8000.
2. Run the preflight below. Do not open `/ops/alpha`.
3. Do not emit `inv_`.
4. Do not point the public form at the live roster.

At `20 accepted / open official cohort`:

1. Open `/ops/alpha`.
2. Emit `inv_` codes one by one. Cap 30.
3. Mark ledger rows `invited`, then `claimed` when redeemed.

### Pre-invite smoke checklist

Run this at `five qualified / deploy`, and again immediately before the
first `inv_`. Every item is a blocker.

- `SOE_BETA_ACCESS_CODE` and `SOE_OPERATOR_KEY` are set and persisted
  where the process will actually see them after a reboot.
- `SOE_COOKIE_SECURE=1`. App listens on `127.0.0.1` only, one worker.
- HTTPS terminator in front (`deploy/Caddyfile` or
  `scripts/start_https.ps1`).
- `scripts/check_beta.ps1` and `scripts/check_https.ps1 -BetaHostname
  <host>` both exit 0. Certificate checks are not relaxed.
- Backup directory writable. One restore drill
  (`scripts/restore_beta.ps1`) has been run against a copy, not against
  empty hope.
- Operator authentication works; an unauthenticated client cannot open
  `/ops/alpha`.
- Provider key present if live seats will run. A written budget ceiling
  exists. A run without a key is a null run, not a season.
- Rollback written down: `scripts/stop_beta.ps1`, unpublish poster,
  disable form. No invite is issued during the first preflight.

## Sequence

| When | Work | State reached |
|---|---|---|
| Day 0 | This file is the card. Sentence, offer, states, visual contract, replay schema, and form rules stay closed. | Contract locked |
| ~~Next slice~~ **done 2026-08-14** | Exporter + leakage test. Reconstruction audit over both bundles. One sanitized replay JSON (`AR031_ba`). | **Replay chosen** |
| ~~Next slice~~ **built 2026-08-14** | The poster page itself: atlas relief board, replay transport, locked copy, form markup with honeypot and `src` capture. Not hosted, not wired to a vendor. | Page builds and renders |
| Next slice | Form vendor and host that pass their gates. Fill the two publish-gate placeholders. `python -m scripts.check_poster` exits 0. One poster page on a phone. One test submit from each tagged URL. Deletion of the three test rows. | `poster live` |
| Same window | Controlled-beta preflight without an invite. | Infrastructure proven, roster still `idle` |
| URL day | Three tagged posts. | Outreach started |
| As they arrive | Answer every reply. Mark ledger rows. | `first application` |
| Five `yes` | Deploy if not already stood up. Re-run preflight. Still no `inv_`. | `five qualified / deploy` |
| Twenty `yes` | Open `/ops/alpha`. Issue codes. | `20 accepted / open official cohort` |
| First redeem | Mark `claimed`. | `first invite claimed` |
| Twenty issued and one claimed | Stop adding marketing surface. | `field plan complete` |

## Roles

| Who | Does |
|---|---|
| Operator | Approves copy, presses send, marks `yes`, owns the ledger, runs preflight, issues `inv_` |
| This repo / chat | Keeps the card, writes the exporter, runs the leakage test, writes page copy |
| Claude in the browser | Builds the static page against this visual contract, creates the form after the vendor gate, drafts posts, logs replies |

## Next slice

The replay gate is closed and the page is built. What remains before
`poster live` is entirely operator work.

1. Lock stays locked. Do not reopen the sentence or the offer.
2. Run the hosting gate and the form vendor gate. Both are operator
   decisions and neither is made yet.
3. ~~Build the static page against the visual contract.~~ **Built
   2026-08-14**, see below.
4. Confirm domain ownership before printing a name on any post.
5. One test submit from each tagged URL, then delete the three rows.

Do not send the posts before `poster live`.

### The page

`webapp/static/public/` is the whole deployable: `index.html`,
`atlas.css`, `atlas.js`, `board3d.js`, `board.js`, `replay.json`,
`vendor/` (three.js and OrbitControls), and four textures copied from
`maps/textures/`. Static files only, no build step, no server call.

**Weight: 1.91 MB on disk, 0.71 MB gzipped**, of which
`vendor/three.module.js` is 1.27 MB uncompressed. The compressed number
is the one that matters: a phone opening the poster from a link
downloads the wire size, not the disk size, and Cloudflare Pages serves
text assets gzipped or Brotli-compressed by default. At 0.71 MB the page
clears the 1.5 MB gate in `LAUNCH_OPERATIONS.md` with room, and Brotli
would be smaller still. Confirm it on the deployed URL's transfer size
rather than on a local measurement before calling the gate closed.
Nothing else on the page is close — the next largest files are
`plain.jpg` at 174 KB and `replay.json` at 123 KB, both already
compressed formats that gzip cannot improve.

The board is a tilted 3D relief board rendered with three.js
(`board3d.js`), which the contract permits: "The page may rotate or
tilt the board." Twelve cities at their exact `x`/`y`, the fourteen
roads as listed and weighted by quality, and a terrain-textured
**mound** per city whose height and tint come from that city's own
`terrain` label and nothing else. Since Amendment 2 the board is a relief
of a world rather than a printed sheet: mapview's landmass stands 30
units out of ruled water with a cut cliff at the coast, the cities sit on
its surface, and the three region names are lettered across it. They are
placed on mapview's own 1180x680 frame, so the arrangement is the one a
coach already knows rather than a square approximation of it. City names, their data rows, the region titles and
the road mileages are HTML labels projected over the canvas, planned
against each other in screen space so a rotation cannot pile them up.

**The match is decided by movement, so the board animates movement.**
`AR031_ba` records 134 piece-moves: two forces grow from one piece to
fifteen and march back and forth along the Dreliwick–Narunon road while
a lone commander walks west to Rhaethdale and Zelothvale. Pieces
therefore travel their road between turns instead of jumping, staggered
so a column reads as a column, and the road they use lights up in their
seat colour as they use it. Each piece is its own token, arranged in a
packed arc on its seat's side of the city, so fifteen stacks stay
countable and contact — two seats in one city — is visible as two arcs
meeting. Secured cities carry a solid ring and a soft field; occupied
cities a dashed ring.

Under the board, a readout per seat counts forces, cities standing in,
and cities secured, and a tick strip shows where the movement is across
the thirty turns. All of it is read from the replay; none of it is a
ranking.

Playback starts only when the board is actually on screen, pauses when
it scrolls away, and honours `prefers-reduced-motion` by not animating
at all.

Board topology is baked into `board.js` by
`scripts/build_public_board.py`, which copies only id, name, `x`, `y`,
one terrain label, and the ruin flag out of `maps/calib_12.json`. That
keeps the page's only fetch `replay.json`, as the card requires.
Population, mile coordinates, grid refs, regions, and road distances do
not cross the boundary.

**Two placeholders block publication**, and a gate in `atlas.js`
enforces them: while either is empty it shows a "not published yet"
banner and disables the submit button, so the page cannot go live
silently broken or silently swallow an application.

| Placeholder | In | Filled after |
|---|---|---|
| `data-endpoint` on `<form id="apply-form">` | `index.html` | Form vendor gate |
| `data-contact` on `<span id="operator-contact">` | `index.html` | Operator picks a dedicated address or handle |

**The bundle is checked before it is published.**
`scripts/check_poster.py` is the preflight, and it is the last repo-side gate:
it refuses a bundle whose placeholders are unfilled, whose locked sentence,
offer bullets, proof line, privacy notice or reply promise have been edited,
whose `replay.json` fails the leakage test or names a city the board cannot
draw, whose `board.js` has drifted from `maps/calib_12.json`, which points at
the live server or a third party, whose `?v=` cache token is split or stale,
or which is over the weight gate. Run it at the publish stage before the
files go to the host:

```text
python -m scripts.check_poster            # exit 0 = clear to publish
python -m scripts.check_poster --stage build   # placeholders still open
```

`tests/test_poster_preflight.py` keeps it honest and runs the build stage
over the tree in CI, so a copy edit that reopens a locked line fails the
suite rather than the launch.

The form already carries the abuse controls: off-screen honeypot,
12-character doctrine minimum, handle-shaped contact check that rejects
emails and URLs, and a courtesy one-per-day throttle. The binding rate
limit is still the vendor's. The privacy notice sits above the submit
button, verbatim.

## Open choices

Only these remain open, and only after their gates:

1. Public host, after the hosting gate.
2. Form vendor, after the form vendor gate.
3. **The spend ceiling.** Undecided, and it is the one open choice with no
   gate to close it — it is a number the operator picks. Nothing paid runs
   until it exists: not a gate re-run, and not an official season. It is
   also why two poster improvements are parked, below.

Closed 2026-08-14: the source match for the replay, by the
reconstruction audit — `AR031_ba`, competence bundle, `official-gate`.

Closed 2026-08-16: the model. Claude Haiku 4.5, in the frozen regulation.
See `LAUNCH_OPERATIONS.md`, **Model gate: closed**.

### Parked, and why: the poster's map

The map the project draws got a great deal better on 2026-08-16 — owned
coastlines, terrain, sea lanes, a scale bar — and a stronger twelve-town
scenario was screened and frozen as `calib_12_fbm.json`. **None of that is
on the poster**, and it should not be forced there.

The poster shows a real recorded match, and that match was played on
`calib_12.json`. Its map and its replay are one object: drawing the new
coast under the old game would be a picture of a world the game was not
played in, and swapping in a prettier match means dropping to an
`exhibition` label and a 17-move game in place of a 134-move one. Both
improvements need the same thing — a paid run on the new scenario — which
needs the ceiling above.

So the poster ships as it is, honestly labelled `official-gate`, and the
map work waits for the money rather than for more code.

Everything else in this file is decided.

## Related

- Drafted, unsent posts for the three tagged URLs:
  [`OUTREACH_POSTS.md`](OUTREACH_POSTS.md)
- Paste-ready replies: [`REPLY_TEMPLATES.md`](REPLY_TEMPLATES.md)
- The publish preflight, run before the bundle goes to the host:
  `python -m scripts.check_poster --help`. Its cache-token record is
  `configs/poster.json`; bump `?v=` everywhere, then re-record with
  `--accept-token`.
- The ledger itself is not a spreadsheet to eyeball. `scripts/waitlist.py`
  merges the vendor export into `private/ledger.csv` (gitignored), keeps one
  row per contact, discards what the abuse controls say to discard, reports
  which state the funnel is in, lists who is past the reply promise, and
  refuses to record an `inv_` before twenty are accepted.
- Product promise: [`AGENT_COMPETITION.md`](AGENT_COMPETITION.md)
- Why 20–30 invited coaches, not a public platform: [`READINESS_AND_MARKET.md`](READINESS_AND_MARKET.md)
- Phase 4 gates and `/ops/alpha`: [`ROADMAP.md`](ROADMAP.md)
- Trailer, later, not a blocker: [`../trailer/00_project/creative-brief.md`](../trailer/00_project/creative-brief.md)
