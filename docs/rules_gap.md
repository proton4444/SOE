# Rule Coverage (Alpha)

Status of `rules.md` mechanics in the alpha engine. Line references have been
dropped: they went stale as the code moved. Use the named modules instead.

## Headline numbers

| Axis | Coverage |
|---|---|
| Command verbs recognised | **41 of 89 (46%)** |
| Order-language features | **2 of 9** (`HAVE` delegation, `and` target lists) |
| Turn model | Synchronous fixed turns; the rules specify an **asynchronous order queue** |

Counted by cross-referencing the command sections of `rules.md` against
`parser.ORDER_KEYWORDS`. "Recognised" means the parser routes the verb and the
engine has a phase for it — not that every sub-rule of that command is honoured.

## Commands implemented (41)

ALLY, ENEMY, NEUTRAL, ASSIGN, GIVE, ATTACK, AWAIT, BLESS, BUILD, CONSTRUCT,
MAKE, BUY, CAPTURE, COLLECT, GATHER, CURE, CURSE, DISCARD, DISMISS, FREE,
RELEASE, FLY, FORTIFY, UNFORTIFY, GO, MOVE, TRAVEL, HEAL, MINE, NAME, PRAY,
PROMOTE, RECRUIT, SAIL, SECURE, SELL, STUDY, SUMMON, TAX, TEACH, TELEPORT

## Commands not implemented (48)

Grouped by the subsystem they belong to, which is roughly the order they should
be tackled in:

- **Prisoner & execution** — ENSLAVE, KILL, EXECUTE, INTERROGATE
- **Status & stealth** — COMBATANT, NONCOM, LURK, UNLURK
- **Order control** — HALT, STOP, WAIT FOR, WAIT UNTIL
- **Inventory** — GET, OBTAIN, TAKE, TRANSFER, UNLOAD, WORK
- **Communication** — SAY, TELL, ADDRESS, POST, REPORT, QUERY, PASSWORD
- **Finance** — BORROW, REPAY, PAY, INVEST, OFFER, HIRE, PURCHASE, BUY PASSAGE
- **Exploration & intel** — EXPLORE, SCAN, SEARCH, PROBE
- **Magical items** — CONJURE, CREATE, CHARGE, RECHARGE, ABSORB
- **Groups** — JOIN, COME, SUPPORT
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
  multiplier. (`orders.py`, `engine.process_fortifications`, `combat.py`)
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

- **`AWAIT` and `REPEAT`** are parsed and written to the turn log, but nothing
  executes them. There is no cross-turn order queue, which the rules'
  asynchronous design ultimately requires. Treat these as accepted-but-inert.
- **Diplomacy** tracks ally/enemy/neutral stances, but stance does not yet
  affect combat sides, movement rights or support.
- **Fortification state** is stored in three overlapping places
  (`City.fortification_level`, `Faction.fortifications`,
  `GameState.city_fortifications`); combat reads the last. These should be
  collapsed into one.

## Not implemented

- Fog of war — reports are scoped per faction, but the engine models no notion
  of what a faction can observe.
- Per-character gold; gold is held per faction.
- Encumbrance, item weight and the full magical-item system.
- Religion's `PREACH` donations and the wider miracle table.
- Named-character hiring, education and the starting-character creation phase.

See [`audit_2025-11.md`](audit_2025-11.md) for defects fixed in v0.7.1.
