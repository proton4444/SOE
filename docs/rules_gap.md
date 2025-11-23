# Rule Coverage (Alpha)

The previously identified gaps have been implemented in the alpha engine. The following rules now exist end-to-end in parser, engine, and combat resolution paths.

## Newly Added Mechanics

- **Fortifications & Location Defense**: `FORTIFY`/`UNFORTIFY` orders upgrade or tear down city defenses using stone, and defenders now gain combat multipliers from fortification levels. 【F:spoils_engine/orders.py†L272-L293】【F:spoils_engine/engine.py†L1043-L1066】
- **Equipment Effects in Combat**: Weapons, armor, and siege engines produced via `BUILD` contribute to attack power and reduce casualties during combat resolution. 【F:spoils_engine/combat.py†L46-L107】【F:spoils_engine/combat.py†L204-L228】
- **Religion System**: New `PRAY`, `BLESS`, `CURSE`, and `RESURRECT` orders let religious characters raise donations, buff friends, debuff foes, and revive allies, consuming religious power and using skill-based chances. 【F:spoils_engine/orders.py†L205-L237】【F:spoils_engine/engine.py†L773-L826】
- **Advanced Combat Signals**: Blessings, curses, fortifications, and siege engines now feed into combat power and casualty modifiers to reflect morale and defensive advantages. 【F:spoils_engine/combat.py†L46-L107】
- **Trading Economy**: `TRADE` orders buy or sell resources at prices improved by a character's `trading_skill`, with treasury and inventory updates. 【F:spoils_engine/orders.py†L417-L428】【F:spoils_engine/engine.py†L1372-L1415】
- **Conditional & Queued Orders**: `AWAIT` and `REPEAT` commands are parsed and logged to support sequencing and delays. 【F:spoils_engine/parser.py†L1528-L1557】【F:spoils_engine/engine.py†L1420-L1429】
- **Advanced Taxation**: City income now accumulates in capped tax pools that must be collected with `TAX`, enabling multi-turn storage and depletion tracking. 【F:spoils_engine/engine.py†L904-L926】【F:spoils_engine/engine.py†L1359-L1369】
- **Prisoner Escape Mechanics**: Captured characters gain periodic escape chances, notifying both captor and prisoner factions. 【F:spoils_engine/engine.py†L1950-L1960】
- **Resource Richness & Time-Based Production**: Gathering and mining yields scale with per-city richness values to simulate site quality and work duration. 【F:spoils_engine/models.py†L73-L94】【F:spoils_engine/engine.py†L1335-L1363】
- **Complex Magic**: `SCRY` adds magical scouting that spends power and reports nearby forces; summon handling remains and ties into combat. 【F:spoils_engine/engine.py†L694-L711】
