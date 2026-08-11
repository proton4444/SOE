# Game mechanics

The rules reference for this engine. It describes what the engine does, not
what any design document says it should do: every constant, formula and
ordering below is read out of the implementation, and the implementation is
authoritative where the two disagree.

Derived from `soe/config.py` (constants), `soe/engine.py`
(resolution order), `soe/phases/` (behaviour) and
`soe/parser/` (command surface). See
[`docs/ip_cleanroom.md`](docs/ip_cleanroom.md) for why this document exists.

---

## 1. The shape of the game

Several factions compete for control of a world of towns linked by roads and
sea lanes. A faction acts through named characters, who lead groups of troops,
hold gold, learn skills, and work magic. There is no single victory condition
in the engine: a game runs for as many turns as its operator schedules, and
what counts as winning is decided by the scenario.

Three properties define the engine and should be treated as contracts.

**It is deterministic.** The same starting state, the same orders and the same
seed produce byte-identical output. All randomness flows from one seeded
generator threaded through resolution.

**It is simultaneous.** Every faction writes orders without seeing anyone
else's, and the turn resolves them together in a fixed phase order. Nobody
moves "first" except as that order dictates.

**It is partially observed.** A faction sees its own characters, the towns it
has secured, and whatever its people happen to notice. Everything else is
inferred.

## 2. Time

A turn is one game week: seven days, 168 hours (`DAYS_PER_TURN`,
`HOURS_PER_TURN`). A month is thirty days.

Orders are not all instantaneous. Some — travelling a long road, working for a
fortnight, waiting for someone to arrive — occupy game time and sit on an
order queue. The turn therefore resolves as a sequence of clock instants: the
engine runs the batch of orders ready at the start of the week, then advances
to the next hour at which a queued order wakes, resolves what has become
ready, and repeats until the week is spent. Weekly bookkeeping — income,
upkeep, investment, resource regrowth — runs once, in the first batch.

A consequence worth internalising: an order can be issued this week and take
effect next week, and a player will see it reported as departed before it is
reported as arrived.

`AWAIT_DEFAULT_DEADLINE_DAYS` (90) bounds an open-ended wait so a character
cannot be stranded forever by someone who never comes.

## 3. The world

**Towns** carry a population band, and increasingly a measured population.

| Band | Population | Income/turn | Recruits/turn |
|---|---|---|---|
| Tiny | under 1,000 | 10 | 10 |
| Small | 1,000–9,999 | 50 | 50 |
| Medium | 10,000–99,999 | 200 | 200 |
| Large | 100,000+ | 500 | 500 |

An unmeasured town is treated as its band's midpoint (500 / 5,000 / 55,000 /
150,000). Investment is what makes population concrete and what moves a town
between bands.

**Routes** connect towns and carry a quality: excellent, good, fair, poor, or
sea. Quality is a cost multiplier — 0.5, 1.0, 1.5, 2.0, and 1.0 for sea lanes,
which need a ship. Where the map gives a route a length in miles, crossing it
costs `quality × miles / 10`; a character has 10 movement points per turn, so
100 miles of good road is one full week of walking, about fourteen miles a
day. Maps without mileages fall back to a flat per-hop cost.

**Positions within a town.** A character is inside, outside, or near a town,
and this governs who can see whom (§10).

**Magic-free zones.** Some places suppress magic. After all movement has
resolved, a single sweep catches everyone who has ended up somewhere magic
cannot work.

## 4. Factions and characters

A faction starts with `STARTING_TREASURY` (1,000) gold. A starting character
has combat skill 10 and magic skill 5.

Characters carry four skills — combat, magic, religion, trading — each 0–100.
Where a single number for overall capability is needed, the engine uses the
**effective level**: the square root of the sum of the squares of the
character's skills. Effective level drives salary and resistance to opposed
magic.

**Health** runs 0–100 and scales skill effectiveness; wounds degrade what a
character can do before they kill. Characters can be captured and held as
prisoners, interrogated, freed, enslaved or executed.

**Salary.** A named character costs `(5 + effective_level) / 4` gold per turn.

**Groups.** A character given a direct order becomes a group leader, and their
subordinates and troops travel with them. Leadership is resolved before the
order that named them is carried out, so a chain of command formed this turn
is honoured this turn.

## 5. Units

Four unit types: soldiers, sailors, workers and slaves. Soldiers and sailors
cost 1 gold to recruit, workers likewise (a simplification — the design rate
is a quarter gold), and slaves are not recruited at all but created by
enslaving prisoners.

Upkeep per unit per turn: 0.1 for soldiers and sailors, 0.025 for workers,
0.01 for slaves. A galley costs 1,000 gold and 2.0 per turn to maintain.

**Elite units** are raised with `CREATE` from existing soldiers. They gain one
partial training point per week and one level per five partial points, so an
elite unit improves slowly and continuously. Their salary is soldiers × combat
level per month, charged weekly at 7/30 of that.

**Training.** `TRAIN` converts workers into soldiers or sailors. The trainer
needs at least 10 in the relevant skill — combat for soldiers, sailing for
sailors. Throughput scales with the trainer's skill: a level-50 trainer
produces five trained units a week. A `TRAIN` order takes what one week can
deliver and leaves the remainder for the next.

## 6. The order language

Orders are written as English sentences, one per line, each ending in a
period. The parser recognises 89 command verbs mapping onto 64 order types.

```
Have Marcus go to Ravenna.
Recruit 40 soldiers in Ravenna.
Invest 200 gold in Ravenna.
Have Marcus attack Tullia.
Ally Northern League.
```

**Actors.** An order may name its actor (`Have Marcus …`) or leave it implicit,
in which case it falls to the faction or the current actor in context.

**Pronouns** resolve against the sentence before them: `me`/`I`/`you`,
`him`/`her`, `it`, `them`, and the reflexives.

**Chaining.** Several commands can share one sentence with `and`. `THEN`
sequences them so the second begins when the first completes.

**Conditionals.** `IF` takes a condition and a branch, with optional `else`. A
condition that arrives on the queue mid-week is judged against the world it
lands in, not the world at the start of the turn.

A player may issue at most `MAX_ORDERS_PER_PLAYER` (100) orders per turn.
Routes are capped at `MAX_PATH_LENGTH` (20) hops.

## 7. Resolution order

The single most important thing to understand about a turn: orders do not
resolve in the order you wrote them. They resolve by category, in this
sequence, for every batch of orders that becomes ready at one clock instant.

1. **Conditionals** — `IF` statements pick a branch, which joins the turn.
2. **Validation** — malformed or impossible orders are rejected with warnings.
3. **Offers** — resolved first so an independent character who accepts has
   joined the faction before any order naming them runs. A refusal fails the
   orders that assumed acceptance.
4. **Group leadership** — a character given a direct order becomes a leader.
5. **Movement**, then **sailing**, then **bought passage**; elite units follow
   whoever led them. Occupation is then reconciled, so recruitment sees who
   actually holds a town rather than who is expected to.
6. **Recruiting and buying.**
7. **Magic**: absorb first (so power drawn from an item is spendable this
   turn), then spells, summoning, conjuring, charging last (so unspent power
   can be stowed), then religion. Then the magic-free sweep.
8. **Combat**, then **capture**.
9. **Weekly economy** — investment, income and upkeep, resource regrowth.
   First batch of the week only.
10. **Everything else** — securing, fortifying, diplomacy, assignment,
    taxation, trade, gathering, building, prisoner actions, transfers,
    borrowing, study and teaching, probing, searching, scanning, work,
    training, elite creation, preaching.
11. **Communication** — messages, then postings, then reports. Reports run
    last of all, so what a player reads describes the world they will actually
    wake up to.

Two orderings are deliberate and load-bearing: securing resolves before
posting, so a notice at the gates is judged against who holds the town at the
end of the turn; and reporting resolves after everything.

## 8. Economy

**Income** accrues per turn from held towns by band. **Upkeep** is charged for
every unit, ship and named character.

**Tax** takes an extra levy from a held town. **Invest** puts gold into a
town's growth: each week the town spends roughly population/100 from the
invested pool and grows by about the same, with random scatter of ±50% and a
cap of 2,000 population a week, so a large pool cannot detonate a village into
a metropolis.

**Work** earns wages by the day, scaled by town size — 0 in tiny towns (there
is no work to find, so the character volunteers), 1, 2 and 3 gold a day in
small, medium and large. A skilled character does better than common labour:
2% of a day's wage extra per point of their best skill.

**Preaching** collects donations, again by town size (1 / 3 / 8 / 20 gold a day
at religion 100, scaled by actual skill). Each week a preacher has a
`religion/100 × 0.25` chance of attracting one to three workers as followers.

**Resources** — wood, stone, iron, copper, silver, gold, gems, weapons, armour,
catapults — are gathered, mined or traded. Base prices run from 4 (wood) to
120 (catapults), with 5 as the default for anything unlisted. The market
quotes a buy and a sell price separated by a spread of 40% of base; trading
skill narrows the spread but never closes it, so round-tripping a purchase
into a sale always loses gold. Prices are fixed by the engine, never by the
order text, so no player can name the price at which their own goods trade.

A deposit holds `10,000 × richness` and recovers 10% a week.

**Banking.** `TRANSFER` moves gold between characters for a fee of 10 gold
plus 1% of the principal. `BORROW` succeeds 55% of the time, defaults to at
most 500 gold, accrues 1% interest per turn, allows four turns' grace, and
then demands at least 10% of the balance per turn.

**Passage.** Buying passage is sea travel without owning a ship: one gold per
person in the group. It succeeds 95% of the time, less 25 percentage points
per hundred people; insisting ("definitely") adds back 25.

## 9. Combat and magic

**Combat power** is the sum of the attack values of everything present — units,
ships, summoned creatures, elite units — multiplied by `1 + best_combat_skill /
100`. An attack only goes ahead if the attacker has at least 50% of the
defender's power.

Casualties at parity are 10% for the winner and 30% for the loser. A lopsided
fight scales those by the margin, defined as the winning roll over the losing
roll and clamped to 10. The winner's losses fall as the margin grows but never
below 1%; the loser's rise as the square root of the margin but never above
95%, so a rout still costs the victor something and still leaves survivors.

Characters can be wounded, killed or captured in battle. Fortification is
credited to whoever administratively holds the site at the moment combat
resolves.

**Magic power** refills completely each turn. Teleport and flight are priced
by what the caster is carrying rather than how far they go — there is no
distance limit on a teleport.

**Magical items** come in five kinds, and none has a fixed strength: every one
is rolled when found or conjured. Amulets grant skill 40–85; crystals store up
to 20–80; orbs hold 10–60 power; rings give protection 2–5; wands hold up to
30–90 and grant skill 40–90. Conjuring requires magic skill 25.

An orb scanning a distant location spends one power per ten miles; on maps
without mileages, five power per hop.

Searching ruins finds an item with probability 10% plus 1.5% per day, capped
at 60%. What turns up is weighted: crystals 30, amulets 25, wands 20, orbs 15,
rings 10 — so rings and orbs are the rare finds.

## 10. Fog of war

What one character can notice about another depends on where each of them
stands:

| Observer | Can notice |
|---|---|
| Inside | inside, outside |
| Outside | outside |
| Near | near, outside |

Someone inside a town cannot see who is lurking near it; someone near it
cannot see inside. A faction that has secured a town gets an exception to the
outside rule.

Beyond position, detection is a roll. It is affected by the size of the party
— named companions count singly, and troops add bulk, capped at 200 soldiers
so an army cannot become certain to be seen on size alone — and by whether the
target is deliberately lurking. Characters never detect their own faction's
people or the dead through this system; they simply know where their own are.

`PROBE` and comparable opposed magic are resisted with the target's effective
level.

## 11. Diplomacy, territory and communication

Factions stand as allied, enemy or neutral toward each other, set by `ALLY`,
`ENEMY` and `NEUTRAL`.

`SECURE` claims a town; occupation is reconciled repeatedly through the turn,
because travel, transfers and prisoner actions can all remove the last
qualifying garrison.

Communication is in-world, not out-of-band. `SAY`/`TELL` sends a private
message of at most 2,500 characters. `POST` leaves a public notice of at most
256 at a town's gates. `REPORT`/`QUERY` asks the engine for information.
`ADDRESS` and `PASSWORD` manage identity; a password must be 8–64 characters,
shorter is generated for you and longer is truncated.

## 12. Command reference

64 order types, addressed by 89 verbs. Aliases are listed together.

| Type | Verbs | Type | Verbs |
|---|---|---|---|
| ABSORB | ABSORB | MINE | MINE |
| ADDRESS | ADDRESS | MOVE | COME, GO, MOVE, TRAVEL |
| ALLY | ALLY | NAME | NAME |
| ASSIGN | ASSIGN, GIVE | NEUTRAL | NEUTRAL |
| ATTACK | ATTACK | NONCOM | COMBATANT, NONCOM |
| AWAIT | AWAIT, WAIT | OFFER | OFFER |
| BLESS | BLESS | PASSAGE | BUY PASSAGE |
| BORROW | BORROW | PASSWORD | PASSWORD |
| BUILD | BUILD, CONSTRUCT, MAKE | PAY | PAY |
| CAPTURE | CAPTURE | POST | POST |
| CHARGE | CHARGE, RECHARGE | PRAY | PRAY |
| COLLECT | COLLECT, GATHER | PREACH | PREACH |
| CONJURE | CONJURE | PROBE | PROBE |
| CREATE | CREATE | PROMOTE | PROMOTE |
| CURSE | CURSE | RECRUIT | HIRE, RECRUIT |
| ENEMY | ENEMY | REPAY | REPAY |
| ENSLAVE | ENSLAVE | REPORT | QUERY, REPORT |
| FLY | FLY | SAIL | SAIL |
| FORTIFY | FORTIFY | SAY | SAY, TELL |
| FREE | DISCARD, DISMISS, FREE, RELEASE | SCAN | SCAN |
| GET | GET, OBTAIN, TAKE | SEARCH | EXPLORE, SEARCH |
| HALT | HALT | SECURE | SECURE |
| HEAL | CURE, HEAL | STOP | STOP |
| INTERROGATE | INTERROGATE | STUDY | STUDY |
| INVEST | INVEST | SUMMON | SUMMON |
| JOIN | JOIN | SUPPORT | SUPPORT |
| KILL | EXECUTE, KILL | TAX | TAX |
| LURK | LURK, UNLURK | TEACH | TEACH |
| TELEPORT | TELEPORT | TRAIN | TRAIN |
| TRADE | BUY, PURCHASE, SELL | TRANSFER | TRANSFER |
| UNFORTIFY | UNFORTIFY | UNLOAD | UNLOAD |
| UNNAME | UNNAME | WORK | WORK |

## 13. Constants

Every number in this document lives in `soe/config.py` and is
tunable there. Balance changes belong in that file, not scattered through the
phases.
