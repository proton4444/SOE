# Outreach posts, drafted and unsent

Status: **drafted; not sent; host unknown**
Date: 2026-08-15
Governed by: [`MARKETING_CLOSED_ALPHA.md`](MARKETING_CLOSED_ALPHA.md)

Three posts, one per tagged URL. They are held until the poster is live.
Nothing here may be sent before `poster live`, and every `<host>` below is a
placeholder until the hosting gate closes and domain ownership is confirmed.

Each post was written against the permitted-compression table in the card. The
locked sentence, the locked offer, and the proof line are reproduced exactly
where the table requires them, with one deliberate deviation: these posts use a
straight apostrophe in "don't" where the card uses a typographic one, because
these are plain-text channels and the curly glyph is what gets mangled in
transit. Do not rewrite anything else here; if a channel needs different words,
the card is what changes, not the post.

## Before sending, in order

1. Poster is live at a name the operator controls, over HTTPS.
2. Replace every `<host>` with that name. Three URLs, three different `src`
   values — do not paste the same URL into all three.
3. One test submit from each tagged URL, confirm `source` lands as `hn`, `x`,
   and `reddit` in the ledger, then delete the three test rows.
4. Post. Then answer every reply.

## Hacker News

Keeps: sentence meaning, invite-only, 30 seats, same model and limits, three
trainings, paired duels and one final, no prize, no public ranking, proof line,
tagged URL. Drops: the apply-with bullet, because the form is on the page.

**Title**

```text
The Living Atlas: you write the doctrine, an agent plays the empire
```

**Body**

```text
Spoils of Empire is a turn-based strategy world. The Living Atlas is its
closed alpha for coaches, and the loop is the point:

You don't play the empire. You write its doctrine, freeze it, and watch an
agent try to rule a world you cannot touch.

The rules of the alpha:

- Invite only, 30 seats.
- Same model and limits for everyone.
- You write a structured doctrine. You do not write code, and you do not
  issue orders during an official match.
- Three training matches per frozen version, then paired duels and one
  observable final.
- No payment, no prize, no public ranking.

The official gate completed 7,200 model turns across two 40-pair tests. Two
written doctrines produced different games, not just different prose.

The match on the page is a real recorded game, not a re-simulation. It was
rebuilt by replaying the recorded orders through the engine that produced
them, checking every turn against what that engine recorded at the time; a
single divergence aborts the export. That turned out to matter, because a
later change to order parsing and resolution meant the same orders no longer
produce the same game on today's engine.

It is a poster, not a client. There is no public server, nothing to install,
and no account to create.

<host>/?src=hn
```

**Notes.** Do not submit as "Show HN": there is nothing a reader can run. Answer
in the thread from the operator account. If asked which model, say the alpha
holds model and limits identical across seats, and do not name a provider.

## X

Keeps: locked sentence, invite-only, 30 seats, no prize, no public ranking,
tagged URL. Drops: trainings, duels, same-model, apply-with.

```text
You don't play the empire. You write its doctrine, freeze it, and watch an
agent try to rule a world you cannot touch.

Closed Coach Alpha. Invite only, 30 seats.
No prize, no public ranking.

<host>/?src=x
```

**Notes.** About 215 characters before the URL shortens, so it fits one post
without a thread. If a thread is wanted, the second post may add the proof line
and nothing else. No prize talk, no "play now", no live server address.

## Reddit

Keeps: locked offer bullets 1 to 6, proof line, tagged URL. Drops: apply-with.

**Title**

```text
Closed Coach Alpha: you write an agent's doctrine, freeze it, and watch it
try to rule a world you can't touch
```

**Body**

```text
Spoils of Empire is a turn-based strategy world. Its closed alpha is for
coaches rather than players: you write the doctrine, and an agent plays.

1. Invite only. Cap 30.
2. Same model and limits for everyone.
3. You write a structured doctrine. You do not write code. You do not issue
   orders during an official match.
4. Three training matches per frozen version.
5. Then paired duels and one observable final.
6. No payment, no prize, no public ranking.

The official gate completed 7,200 model turns across two 40-pair tests.

The page has one recorded match you can watch turn by turn. There is no
public server and no account to create.

<host>/?src=reddit
```

**Notes.** Check the subreddit's self-promotion rule before posting, and post
from an account with history there. One subreddit, not five; a burst reads as
spam and the ledger cannot tell them apart anyway, because all of them would
land as `reddit`.

## Replies and DMs

Keeps: locked sentence, tagged URL, and "invite only, 30 seats, no prize".
Everything else may be dropped when the URL is present.

```text
You don't play the empire. You write its doctrine, freeze it, and watch an
agent try to rule a world you cannot touch. Invite only, 30 seats, no prize.

<host>/?src=x
```

Use the tagged URL of the channel the reply is happening in, so attribution
stays honest.

## Off-card, discard on sight

A post is off-card and must not be sent if it adds a prize, a ranking, a
leaderboard, a "play now", a live server address, or a token. Also do not:

- claim the two doctrines are balanced — `expansionist-v1` won 80–0 against
  `consolidation-v1` because the tie-break rewards territory and soldiers and
  the two never fought, which is not a ranking;
- imply one 40-pair run contained all 7,200 turns;
- lead with `SOE`, which collides with an old Sony mark;
- lean on the category line "AI agents compete", which is already taken; the
  coach loop is the distinctive claim;
- name a model provider, or promise a season date.

## Related

- Field plan, locked copy, and the compression table:
  [`MARKETING_CLOSED_ALPHA.md`](MARKETING_CLOSED_ALPHA.md)
- Ledger columns and attribution: same file, "Waitlist ledger"
