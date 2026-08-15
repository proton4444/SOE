# Launch Operations

Status: **plan; nothing registered; nothing published**
Date: 2026-08-14
Depends on: [`MARKETING_CLOSED_ALPHA.md`](MARKETING_CLOSED_ALPHA.md)

The card decides *what* is said. This decides *who says it, from where, in
what order, and what happens when it stalls*. It closes the two gates the
card left open, adds the identity layer the card assumes but never names,
and proposes three amendments to the card itself.

Nothing here reopens the locked sentence, the offer's meaning, the visual
contract, or the replay schema. One offer bullet is proposed for
amendment, for a stated operational reason, in **Amendments**.

## The last-mile problem

Read this first. It changes the form.

The offer collects `name, X or Discord, one sentence of doctrine`. Twenty
to thirty `inv_` codes then have to reach those people. They cannot.

- A Discord handle is not addressable. You cannot DM a Discord user you
  do not share a server with, and a friend request from an unknown
  account is usually ignored or blocked.
- An X DM to a non-follower lands in a request folder that most accounts
  never open, and new or low-follower senders are filtered.

So the plan can reach `20 accepted` and then fail to deliver a single
code. The fix is an optional email field on the form, labelled as the
delivery channel for the invite. See **Amendments**.

## Identity

Everything below is created before the page is published. None of it is
outward-facing on its own.

| Asset | Choice | Why |
|---|---|---|
| Domain | `spoilsofempire.com` if free, else `.game` / `.io`. Never a `livingatlas` domain. | Product name is the durable name. The campaign name is a page title and will change. |
| Public page host | Cloudflare Pages | First host passing all four hosting-gate criteria. See below. |
| Operator address | `operator@<domain>`, forwarded to the personal inbox by Cloudflare Email Routing | Satisfies "dedicated address, not a personal inbox". Free, same vendor as the host, no mail server. |
| X — posting | **Personal account** | A new account posting an external link has near-zero distribution and trips spam heuristics. Account age is the only reach available. |
| X — project | Register `@spoilsofempire` (or nearest free), park it | Stops a squatter, gives a handoff path, linked from the page. Does not post at launch. |
| Discord | Dedicated account under the project name | DMing thirty strangers from a personal account is worse for both sides. |
| Hacker News | Existing personal account, warmed | A fresh account submitting a link is the most-flagged pattern on the site. |
| Reddit | Existing aged account, or **drop the channel** | New accounts are removed by karma filters before a human reads the post. |

### The personal-account decision

Using the personal X account is correct, with one deliberate consequence:
applicants and HN readers will read that timeline. Look at it once and
decide you are fine with that before pressing send. That is the whole
cost. The alternative — a day-old brand account — buys nothing and costs
all the reach.

The split is: **personal account carries the posts, project identity
carries the contract.** The privacy notice, the deletion address, the
ledger, and the page all point at `operator@<domain>`, never at a
personal inbox and never at the personal handle.

### Mail trap

If replies are written from the personal inbox, the personal address
leaks on the first reply and the dedicated-address promise is void.
Configure Gmail *Send mail as* `operator@<domain>` with SMTP, set it as
the default for that thread, and send one test to an outside address to
confirm the `From:` header before any application arrives.

### Discord reality

A private server for accepted coaches is fine and is not the "Discord
dump" the card forbids — that non-goal is about pasting an invite into
a Reddit post. Do not create the server until `five qualified / deploy`.
It is cohort infrastructure, not marketing surface.

## Hosting gate: closed

Cloudflare Pages, decided by the gate and not by taste.

| Criterion | Cloudflare Pages |
|---|---|
| HTTPS on a name the operator controls | Yes, with the domain at Cloudflare |
| Static files only | Yes; no build step required |
| Unpublish in one step | Yes; delete the deployment or pause the project |
| No coupling to `scripts/start_beta.ps1` | Yes; separate account, separate lifecycle |

It also carries Email Routing for `operator@`, so hosting and the
operator address close together on one vendor. GitHub Pages passes the
first four and cannot do the mail, which is why it is second.

## Form vendor gate: recommended

Tally passes all six criteria. Verify each one in the account before
building — the gate is a check, not a reputation.

| Criterion | Verify by |
|---|---|
| Custom domain or embed on the poster host | Embed the form on a Pages preview deployment |
| Hidden `src` field from the query string | Load `?src=hn`, submit, confirm `hn` in the row |
| Export of the full ledger | Download CSV, confirm every column |
| Deletion of a single row | Delete a test row, confirm it is gone from the export |
| Operator-only access | Confirm the results view requires login |
| Honeypot or equivalent bot check | Enable it, confirm a bot-filled submit is rejected |

If any check fails, the fallback is a Cloudflare Worker writing to D1 —
same vendor, full data control, no third party in the privacy notice. It
is more build and should not be chosen first.

### The form build sheet

Build these six fields, in this order, with these labels **exactly**.
`waitlist.py ingest` matches vendor columns by lowercased substring, so
the label is not cosmetic: it is the integration contract. Renaming
"X or Discord handle" to "Handle" still works; renaming it to "Contact
me at" still works; renaming it to "Where do we reach you" does not, and
ingest will refuse the file rather than guess.

| # | Label | Type | Required | Notes |
|---|---|---|---|---|
| 1 | `Name` | short text | yes | max 80 |
| 2 | `X or Discord handle` | short text | yes | max 80. Hint: "An X or Discord handle. Other contact methods are not accepted." |
| 3 | `Email (optional)` | email | **no** | max 120. Hint: "Only if you want the invite code sent there." |
| 4 | `One sentence of doctrine` | long text | yes | min 12, max 400 |
| 5 | `src` | hidden | — | populated from the query string, never shown |
| 6 | `Company` | honeypot | — | hidden from humans; a filled value is discarded |

The vendor's own timestamp column ships as `Submitted at` and maps to
`received_at`. Do not rename it.

Verified: an export carrying exactly these headers ingests with every
column mapped and nothing unmatched. Re-run that check after any label
edit, on a two-row test export, before trusting a real one:

```text
python -m scripts.waitlist --ledger /tmp/probe.csv init
python -m scripts.waitlist --ledger /tmp/probe.csv ingest export.csv
```

A silent mismap looks like a successful ingest with a blank column, so
read the row back with `show` rather than trusting the count.

Two copy obligations the form carries beyond the page, both from the
card and neither optional:

- the privacy notice, verbatim, including `email` in its first sentence;
- the sentence **"You will hear back within 7 days, either way."**
  `waitlist.py due` is what keeps it.

## The page

One static bundle. No framework and no build step, but three.js **is**
shipped: the board is a tilted 3D relief, which the card's contract
permits. An earlier draft of this line said "no Three.js" and was wrong
about what was built.

```text
index.html              structure and all copy
atlas.css               layout, type, dark board
atlas.js                replay playback, src capture, form + publish gate
board.js                2D fallback board
board3d.js              3D relief board (three.js)
replay.json             the exported official-gate match, unmodified
textures/               desert hills paper plain
vendor/three.module.js  three.js, 1.27 MB uncompressed
vendor/OrbitControls.js camera control
```

Asset URLs carry a `?v=` token that is **hardcoded in `index.html`, not
generated**. Bump it by hand whenever `atlas.css` or `atlas.js` changes,
or returning visitors keep the old file. It is currently `v=h2`.

`sea.jpg` is **not** shipped. There is no sea. Shipping the texture
invites its use.

### Board

Render as inline SVG. Twelve cities and fourteen roads do not need
WebGL, and SVG stays crisp on a phone.

- Cities at their exact fractional `x`/`y` from `maps/calib_12.json`.
- Roads exactly as listed, stroke weight by `quality`.
- Each city gets a small terrain disk filled with an SVG `<pattern>`
  from its `terrain` label. Local relief only.
- Background is `paper.jpg`. Everything between cities stays empty.
- A slight CSS 3D tilt on the SVG gives the board feel. That is a camera,
  not geography. Allowed.

Downscale every texture to 256px before shipping. The originals are
67–254 KB each for disks a few dozen pixels wide.

### Playback

31 frames, roughly 1.5s per turn, autoplay muted, loop, with a scrub bar
and play/pause. Pieces are markers on city nodes; `secured_by` colours
the city ring; `occupied_by` stacks markers in the same city.

One caption under the board, because the match contains no resolved
attack and a visitor expecting a battle will otherwise see armies
walking:

> Official gate match, 30 turns. Watch where the doctrine sends them:
> movement, two seats sharing a city, and territory changing hands.

### Page order

This order is the mitigation for the Hacker News risk. The board must be
the first thing that happens.

1. Title — The Living Atlas
2. Locked sentence
3. **The board, already playing**
4. Proof line, and the optional second clause
5. The seven offer bullets
6. Form
7. Privacy notice, operator address, project handle

The form is below the fold. A page that opens with "30 seats, apply
here" is a waitlist page and will be treated as one.

### No-JS fallback

Render the final frame as static SVG in the HTML so the board exists
before `atlas.js` runs.

## Sequence

Days are relative to the first working session, not calendar dates.

| Day | Work | Gate to pass |
|---|---|---|
| 0 | Commit the replay slice to git. The exported `replay.json` is not cheaply regenerable once the worktree is gone. | Working tree clean |
| 0 | Check and register the domain. Confirm ownership. | Domain resolves |
| 0 | Cloudflare account, Pages project, Email Routing, `operator@` send-as test | Test mail arrives with the right `From:` |
| 1 | Register and park the project X handle. Create the project Discord account. Check HN account age; start commenting genuinely if thin. | Handles held |
| 1–3 | Build the page. Test on a real phone, not a resized window. | Board renders, replay plays, page under 1.5 MB |
| 3 | Run the form vendor gate, six checks. Build the form. Wire the hidden `src` field. | All six pass |
| 3 | One test submit from each of the three tagged URLs. Confirm `source` is `hn` / `x` / `reddit`. Delete the three rows. Confirm deletion in a fresh export. | Ledger clean |
| 4 | Publish. | **`poster live`** |
| 4 | Controlled-beta preflight, no invite issued. | Infrastructure proven, roster `idle` |
| 5 | Post on X from the personal account. | Outreach started |
| 6–7 | Watch. Fix whatever the first real traffic breaks. | Page survived strangers |
| 8 | Submit to Hacker News. Be at the keyboard for the next four hours. | — |
| 8+ | Reddit only if the account is aged and the fit is real. Otherwise skip. | — |
| Rolling | Answer every reply. Mark every ledger row. | `first application` |

### Channel order, changed

The card lists Hacker News first. Post it **last**.

HN is one shot, high variance, and unforgiving of a page that breaks
under load or reads as a waitlist. X is a low-stakes rehearsal with a
real audience. Let X find the broken thing first.

## Stall and abort

The card defines success and never defines failure. These are the
branches.

| Condition | Action |
|---|---|
| Fewer than 5 applications 14 days after the last post | Stop adding surface. The pitch or the channel is wrong, not the volume. Re-read the applications that did arrive before writing anything new. |
| Between 5 and 19 `yes` at 30 days | Run the cohort with what exists. A 12-coach alpha is an alpha. Do not lower the bar to reach 20. |
| 20 `yes` reached | Card takes over: open `/ops/alpha`, emit codes, cap 30. |
| Any leak of forbidden data on the page | Unpublish first, diagnose second. |

The form states a reply-by promise and it is kept:

> We read every application. You will hear back within 7 days, either
> way.

Twenty accepted people who applied and then heard nothing for a month
are twenty people who will not show up when the season starts.

## Reply playbook

Written before the posts, not during them. Every answer stays on-card;
the compression table governs what may be dropped.

| Question | Answer |
|---|---|
| Can I try it now? | Not yet — invite only, 30 seats. Tagged URL for that thread. |
| Which model? | Decide this before posting and answer it plainly. Refusing reads worse than answering. The forbidden list covers the replay file and the page, not conversation. |
| Is it open source? | Answer honestly, one sentence, no roadmap promise. |
| How is this different from Agent Arena / Agent Sports League? | The coach loop: you write a doctrine, freeze it, and cannot touch the match. Not a leaderboard. |
| Why no ranking or prize? | Ranking turns a doctrine experiment into a scoring contest. Explicit non-goal. |
| What does the agent actually do? | Point at the board. It reads the world state and issues its own orders under the frozen doctrine. |
| When does the season start? | Only what is true. If unknown, say unknown. |
| Who runs this? | The operator address and the project handle. Both are public. |

Never invent a second offer, a prize, a ranking, a live server address,
or a date that is not decided.

## Amendments proposed to the card

Three. The first is required; the others are corrections.

**1. Add an optional email field to the form.** **Accepted 2026-08-15
and applied.** Offer bullet 7 becomes:

> Apply with: name, X or Discord, one sentence of doctrine, and an email
> if you want the invite code sent there.

Reason: **The last-mile problem** above. Without it, accepted coaches may
be unreachable. The privacy notice gains `email` in its first sentence
and is otherwise unchanged.

Applied in three places: the card's bullet 7 carries the amendment note,
the page grows an optional `email` input whose format is checked only
when non-empty, and `waitlist.py invite` already refused to issue a code
to a row with no email unless forced. The form now also states the reply
promise out loud — "You will hear back within 7 days, either way" — which
is the sentence `waitlist.py due` exists to keep.

**2. "It reads `replay.json` and nothing else" is not satisfiable.**
`replay.json` carries `city_id` references but no coordinates, terrain,
or roads. The page needs the map geometry. Resolution: inline the twelve
cities and fourteen roads into `atlas.js` from `maps/calib_12.json`. That
data is public map topology, not match data, and it keeps the hosting
gate's "one replay JSON" literally true.

**3. Record the closed gates.** *Open choices* should drop the hosting
gate (closed: Cloudflare Pages) and gain a third item that was never
listed: operator identity — domain, address, handles. It was assumed
throughout and decided nowhere.

## Roles

Unchanged from the card, with the identity layer assigned.

| Who | Does |
|---|---|
| Operator | Registers the domain and handles, owns the Cloudflare and form accounts, approves copy, presses send, marks `yes`, runs preflight, issues `inv_` |
| This repo / chat | Keeps both cards, builds the page, keeps the leakage test green, drafts posts and replies |

## Related

- Locked copy, offer, states, visual contract: [`MARKETING_CLOSED_ALPHA.md`](MARKETING_CLOSED_ALPHA.md)
- Paste-ready text for every reply here: [`REPLY_TEMPLATES.md`](REPLY_TEMPLATES.md)
- The three drafted, unsent posts: [`OUTREACH_POSTS.md`](OUTREACH_POSTS.md)
- Ledger tool that keeps the 7-day promise and refuses early codes:
  `python -m scripts.waitlist --help`
- Phase 4 gates and `/ops/alpha`: [`ROADMAP.md`](ROADMAP.md)
