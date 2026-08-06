# Rule Coverage (Alpha)

Status of `rules.md` mechanics in the alpha engine. Line references have been
dropped: they went stale as the code moved. Use the named modules instead.

## Headline numbers

| Axis | Coverage |
|---|---|
| Command verbs recognised | **73 of 89 (82%)** |
| Order-language features | **4 of 9** (`HAVE` delegation, `and` target lists, `REPEATEDLY`, groups) |
| Turn model | Persistent order queue, advanced one pass per weekly turn; the rules specify hour-level asynchronous time |

Counted by cross-referencing the command sections of `rules.md` against
`parser.ORDER_KEYWORDS`. "Recognised" means the parser routes the verb and the
engine has a phase for it — not that every sub-rule of that command is honoured.

## Commands implemented (73)

ALLY, ENEMY, NEUTRAL, ASSIGN, GIVE, ATTACK, AWAIT, BLESS, BUILD, CONSTRUCT,
MAKE, BUY, CAPTURE, COLLECT, GATHER, CURE, CURSE, DISCARD, DISMISS, FREE,
RELEASE, FLY, FORTIFY, UNFORTIFY, GO, MOVE, TRAVEL, HEAL, MINE, NAME, PRAY,
PROMOTE, RECRUIT, HIRE, SAIL, SECURE, SELL, STUDY, SUMMON, TAX, TEACH, TELEPORT,
ENSLAVE, KILL, EXECUTE, INTERROGATE, COMBATANT, NONCOM, LURK, UNLURK,
GET, OBTAIN, TAKE, TRANSFER, UNLOAD, PAY, BORROW, REPAY,
HALT, STOP, WAIT FOR, WAIT UNTIL, JOIN, COME, SUPPORT,
PROBE, SEARCH, EXPLORE, SCAN,
CONJURE, CHARGE, RECHARGE, ABSORB

## Commands not implemented (16)

Grouped by the subsystem they belong to, which is roughly the order they should
be tackled in:

- **Inventory** — WORK
- **Communication** — SAY, TELL, ADDRESS, POST, REPORT, QUERY, PASSWORD
- **Finance** — INVEST, OFFER, PURCHASE, BUY PASSAGE
- **Elite troops** — CREATE. This was previously filed under magical items by
  mistake: `rules.md` defines CREATE as forming a named elite troop unit that
  trains continuously, which belongs with recruitment, not with the enchantress.
- **Religion & training** — PREACH, TRAIN
- **Naming** — UNNAME

## Engine verbs that are not in the rules (3)

TRADE, SCRY, RESURRECT. These were invented during alpha development. They are
not wrong, but they are divergence from `rules.md` and should either be
justified in the design notes or retired in favour of the rules' own
equivalents (`BUY`/`SELL` for TRADE, `PROBE` for SCRY). REPEAT and WAIT were on
this list until v0.9 aligned them with the rules' `REPEATEDLY` and `WAIT FOR`.

## Order language

`rules.md` devotes a dozen sections to the order language itself. Current state:

| Feature | Status |
|---|---|
| `HAVE <character> <command>` | implemented (and promotes them to group leader) |
| `and` to list multiple targets | implemented |
| Groups and group leaders | implemented |
| `REPEATEDLY` | implemented (with an optional `N times` count) |
| `IMMEDIATELY` | partial — modifies HALT/STOP, not a general interrupt |
| `UNTIL` conditions | partial — `wait until turn N`, not dates or loop terminators |
| `and` to chain commands | missing |
| `THEN` sequencing | missing |
| `QUIETLY` / `SILENTLY` | missing |
| `IF` statements | missing |
| Pronouns (him/her/them/it) | missing |

## The structural gap

`rules.md` describes an **asynchronous** game: orders go on a queue and execute
when enough game time has passed, reports arrive as things complete, and a
player may cancel an order already in progress.

v0.9 built that queue (`spoils_engine/order_queue.py`). Orders now live on a
per-character queue that survives save/load, `AWAIT` and `REPEAT` hold work back
across turns, and `HALT`/`STOP` cancel what has not started. A queued order is
validated when it executes rather than when it was written, so it is judged
against the world it lands in.

What is left of the gap is **granularity**, not structure. The queue advances
one pass per weekly turn, so it measures game time in turns where the rules
measure it in hours: a one-hour wait and a one-day wait both cost a turn, and a
loop body runs at most once per turn. Sub-turn scheduling — and with it `until
<date>` and the rules' partial-progress rules for an interrupted BUILD — is the
remaining work, and it is now an increment on the queue rather than a rewrite.

## Implemented end-to-end

These exist in the parser, the engine and (where relevant) combat resolution,
and are covered by tests.

- **Fortifications & location defense** — `FORTIFY`/`UNFORTIFY` spend stone to
  raise or tear down city defenses; the holding faction gains a combat
  multiplier. The level belongs to the city, so it stays with the walls when the
  city changes hands. (`orders.py`, `engine.process_fortifications`, `combat.py`)
- **Equipment effects in combat** — weapons, armor and catapults from `BUILD`
  add attack power and reduce casualties. (`combat.py`)
- **Religion** — `PRAY`, `BLESS`, `CURSE` and `RESURRECT` spend religious power
  on skill-based rolls. (`engine.process_religion`)
- **Taxation** — city income accumulates in per-city pools, capped at four
  turns' worth, and reaches the treasury only via a `TAX` order issued by a
  character with soldiers present. Enemy-secured cities block collection.
  (`engine.process_income_and_upkeep`, `engine.process_tax`)
- **Resource richness & timed production** — gathering and mining yields scale
  with per-city richness and work duration. (`engine.process_collect`,
  `engine.process_mine`)
- **Prisoners** — `CAPTURE` takes prisoners, `FREE` releases them, and captives
  get a per-turn escape chance. Prisoners cannot issue orders while held.
  (`engine.process_capture`, `process_free`, `process_prisoner_escape`)
- **Trade** — `TRADE` buys and sells resources at config-set prices, with a
  market spread that the trader's skill narrows.
  (`engine.process_trade`, `config.RESOURCE_BASE_PRICE`)
- **Magic** — teleport, flight, summoning and `SCRY` scouting, all drawing on
  magic power. (`engine.process_magic`, `process_summon`)
- **Groups and group leaders** — a character is either assigned to somebody
  (`Character.group_leader_id`) or leads their own group, and unnamed units are
  assigned the same way (`UnitStack.owner_character_id`). A group travels
  together, `JOIN` and `ASSIGN` are the same operation from opposite ends,
  `UNLOAD` sets a character loose, and a direct order (the `HAVE` form) promotes
  its target to group leader. `SUPPORT` puts a character into somebody else's
  battle without merging the groups. (`groups.py`, `engine.process_join`,
  `process_support`, `supporting_side`)
- **Order queue** — orders sit on a per-character queue that persists across
  turns and through save/load. `AWAIT` holds the orders behind it for a duration
  or until a named character arrives; `REPEAT`/`repeatedly` runs its body one
  pass per turn; `HALT` drops the backlog at once and `STOP` does so in
  sequence. A character with nothing in front of them still resolves their whole
  submission in the turn they gave it. (`order_queue.py`, `engine.run_turn`)
- **Fog of war** — each character has a position band (`inside` / `outside` /
  `near`) relative to their city. End-of-turn sightings only report people that
  a living non-prisoner of the faction can notice under the rules' position
  matrix. `LURK` multiplies detection chance by ¼ and still covers the whole
  group. `PROBE` spends 25 magic power for a full character report (magic skill
  vs target effective skill). `SEARCH`/`EXPLORE` dig ruins marked `City.is_ruin`
  when the actor is inside. (`fog.py`, `engine.process_sightings`,
  `process_probe`, `process_search`)
- **Magical items** — all five kinds from `rules.md`, held in
  `GameState.magical_items` and named in the enchantress's `*Starred*` style so
  orders can refer to them. Amulets lend a skill (never magic or religion, best
  one wins); crystals pool with the caster and are drained before their own
  power, one crystal at a time; orbs power `SCAN` at a cost set by the distance
  and never fill up; rings divide an attacker's hit and capture chance, with a
  blessing worth +1; wands supply both the skill and the power for one spell,
  but only when the order names them with `with`/`using`, and never borrow from
  a crystal. `CONJURE` spends every point the caster has for a success chance
  equal to that number and yields a temporary item; `CHARGE`/`RECHARGE` and
  `ABSORB` move power in and out, reaching items held by a companion in the same
  place; `SEARCH` in ruins yields permanent items. Orbs and wands regain a point
  a day, and a crystal gains one only on a day its possessor ended at their
  natural maximum. Items are given by name (`Give *Wameka* to Joe Flint`) and
  show on status reports in the rules' format. (`items.py`,
  `engine.process_conjure`, `process_charge`, `process_absorb`, `process_scan`,
  `process_search`, `process_item_upkeep`, `combat.apply_casualties`)
- **Magic-free zones** — a city flagged `is_magic_free` drains the magic power
  of everyone standing in it and of every item they carry, and nothing
  regenerates there. One sweep runs after all movement has resolved, so
  walking, sailing, flying and being teleported in are all caught.
  (`engine.process_magic_free_zones`, `items.drain_magic_free_zone`)

## Partial

- **Order-queue timing** is turn-granular. A wait of one hour and a wait of one
  day both cost a turn, and a loop body runs at most once per turn, because the
  engine has no clock finer than a weekly turn.
- **Diplomacy** decides combat sides — an ally cannot be attacked, and a
  defender's allies present at the battle fight and share the casualties. Stance
  still does not affect movement rights or non-combat support.
- **Gold** is held per character as of v0.8. Legacy `Faction.treasury` still
  acts as a spend fall-back and migrates onto the leader when an old save is
  loaded. Multi-item GET lists remain simplified.
- **Group possession** covers characters and unit stacks. Ships, resources and
  gold are still held by their character rather than travelling with a group as
  a single pool, and combat still totals a faction's strength at a location
  rather than resolving group by group.
- **SCAN** works off a real orb, but distance is priced from the overland
  movement cost (`config.ORB_POWER_PER_HOP`) rather than the rules' miles, and
  one order carries one orb — the rules' form pairing several city groups with
  several orbs in one sentence is rejected rather than misread.
- **Magical items** are not lost or looted when their holder dies: an item stays
  with the body rather than falling to the victor, because `rules.md` does not
  say what should happen and the items are indestructible. Item weight and
  encumbrance are likewise unmodelled, so carrying six crystals costs nothing.
- **Amulets** cover trading and combat. The rules allow an amulet for any skill
  except magic and religion; the engine only has fields for the skills it
  actually uses (`items.AMULET_SKILLS`).
- **Population-based security** (how hard it is to lurk under enemy SECURE) is
  approximated by city population band only; SECURE does not yet raise local
  detection odds beyond making the securer visible from outside.

## Not implemented

- Sub-turn game time, and with it the rules' partial-progress accounting for a
  BUILD or FORTIFY interrupted part-way through.
- Encumbrance and item weight. Magical items ship as of v1.0, but nothing in
  the engine weighs anything, so `FLY` and `TELEPORT` still charge a flat cost
  where the rules charge by what is being carried.
- Elite troop units (`CREATE`), which train continuously and cannot TAX,
  SECURE, BUILD or work.
- Religion's `PREACH` donations and the wider miracle table.
- Named-character hiring, education and the starting-character creation phase.
- Communication verbs (SAY/TELL, POST, ADDRESS, REPORT, QUERY, PASSWORD).

See [`audit_2025-11.md`](audit_2025-11.md) for the defects fixed in v0.7.1 and
the design debt closed in v0.7.2.
