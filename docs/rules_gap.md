# Rule Coverage (Alpha)

Status of `rules.md` mechanics in the alpha engine. Line references have been
dropped: they went stale as the code moved. Use the named modules instead.

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
