# Rule Coverage (Alpha)

Status of `rules.md` mechanics in the alpha engine. Line references have been
dropped: they went stale as the code moved. Use the named modules instead.

## Headline numbers

| Axis | Coverage |
|---|---|
| Command verbs recognised | **58 of 89 (65%)** |
| Order-language features | **2 of 9** (`HAVE` delegation, `and` target lists) |
| Turn model | Synchronous fixed turns; the rules specify an **asynchronous order queue** |

Counted by cross-referencing the command sections of `rules.md` against
`parser.ORDER_KEYWORDS`. "Recognised" means the parser routes the verb and the
engine has a phase for it — not that every sub-rule of that command is honoured.

## Commands implemented (58)

ALLY, ENEMY, NEUTRAL, ASSIGN, GIVE, ATTACK, AWAIT, BLESS, BUILD, CONSTRUCT,
MAKE, BUY, CAPTURE, COLLECT, GATHER, CURE, CURSE, DISCARD, DISMISS, FREE,
RELEASE, FLY, FORTIFY, UNFORTIFY, GO, MOVE, TRAVEL, HEAL, MINE, NAME, PRAY,
PROMOTE, RECRUIT, HIRE, SAIL, SECURE, SELL, STUDY, SUMMON, TAX, TEACH, TELEPORT,
ENSLAVE, KILL, EXECUTE, INTERROGATE, COMBATANT, NONCOM, LURK, UNLURK,
GET, OBTAIN, TAKE, TRANSFER, UNLOAD, PAY, BORROW, REPAY

## Commands not implemented (31)

Grouped by the subsystem they belong to, which is roughly the order they should
be tackled in:

- **Order control** — HALT, STOP, WAIT FOR, WAIT UNTIL (needs v0.9 queue)
- **Inventory** — WORK
- **Communication** — SAY, TELL, ADDRESS, POST, REPORT, QUERY, PASSWORD
- **Finance** — INVEST, OFFER, PURCHASE, BUY PASSAGE
- **Exploration & intel** — EXPLORE, SCAN, SEARCH, PROBE
- **Magical items** — CONJURE, CREATE, CHARGE, RECHARGE, ABSORB
- **Groups** — JOIN, COME, SUPPORT (UNLOAD is a thin alpha placeholder)
- **Religion & training** — PREACH, TRAIN
- **Naming** — UNNAME

## Engine verbs that are not in the rules (5)

TRADE, SCRY, RESURRECT, REPEAT, WAIT. These were invented during alpha
development. They are not wrong, but they are divergence from `rules.md` and
should either be justified in the design notes or retired in favour of the
rules' own equivalents (`BUY`/`SELL` for TRADE, `PROBE` for SCRY).

## Order language

`rules.md` devotes a dozen sections to the order language itself. Current state:

| Feature | Status |
|---|---|
| `HAVE <character> <command>` | implemented |
| `and` to list multiple targets | implemented |
| `and` to chain commands | missing |
| `THEN` sequencing | missing |
| `UNTIL` conditions | missing |
| `REPEATEDLY` | missing |
| `IMMEDIATELY` | missing |
| `QUIETLY` / `SILENTLY` | missing |
| `IF` statements | missing |
| Pronouns (him/her/them/it) | missing |
| Groups and group leaders | missing |

## The structural gap

`rules.md` describes an **asynchronous** game: orders go on a queue and execute
when enough game time has passed, reports arrive as things complete, and a
player may cancel an order already in progress. The engine instead processes
fixed turns in phases, and every order either completes or fails within the turn
it was submitted.

This is why `AWAIT` and `REPEAT` parse but do nothing — there is nowhere to
queue them. `UNTIL`, `REPEATEDLY` and `IF` need the same machinery. A persistent
order queue with per-order game-time costs is the single largest piece of work
between here and rules fidelity, and most of the remaining order-language
features fall out of it.

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

## Partial

- **`AWAIT` and `REPEAT`** are parsed but rejected at validation with a warning
  saying they are not executed yet. There is no cross-turn order queue, which
  the rules' asynchronous design ultimately requires.
- **Diplomacy** decides combat sides — an ally cannot be attacked, and a
  defender's allies present at the battle fight and share the casualties. Stance
  still does not affect movement rights or non-combat support.
- **Gold** is held per character as of v0.8. Legacy `Faction.treasury` still
  acts as a spend fall-back and migrates onto the leader when an old save is
  loaded. Full group-level possession and multi-item GET lists remain simplified.
- **UNLOAD / groups** — UNLOAD logs independence but there is no full group-
  leader model yet (JOIN/COME/SUPPORT are still open).
- **LURK** stores a flag and reports it; detection odds need fog of war (v1.0).

## Not implemented

- Fog of war — reports are scoped per faction, but the engine models no notion
  of what a faction can observe.
- Per-character gold; gold is held per faction.
- Encumbrance, item weight and the full magical-item system.
- Religion's `PREACH` donations and the wider miracle table.
- Named-character hiring, education and the starting-character creation phase.

See [`audit_2025-11.md`](audit_2025-11.md) for the defects fixed in v0.7.1 and
the design debt closed in v0.7.2.
