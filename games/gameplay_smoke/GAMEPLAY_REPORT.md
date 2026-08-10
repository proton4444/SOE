# Spoils of Empire - Gameplay Smoke Test

## Verdict

**PASS** - 3 turns completed with 35 gameplay events and 0 parser warnings.

This is a short golden-path check for human play, not a balance test. It verifies that orders can be understood, turns can resolve, and the world changes in a way a master can explain.

## Scenario

- Turn 1: both factions recruit, secure their home city, and collect taxes.
- Turn 2: Emperor Marcus marches from Madegi Doy to Kitesta and attacks Khan Tengri.
- Turn 3: Marcus attacks again, secures Kitesta, and collects taxes; Tengri waits.

## Turn-by-turn

### Turn 1

Orders parsed: 6 | Warnings: 0 | Seed: `1001`

- **OK** Emperor Marcus recruited 80 soldier in Madegi Doy for 80g
- **OK** Khan Tengri recruited 10 soldier in Kitesta for 10g
- **OK** 500g accrued in tax pools (use TAX to collect)
- **OK** Paid 8.0g in upkeep (units, ships, salaries)
- **OK** 500g accrued in tax pools (use TAX to collect)
- **OK** Paid 1.0g in upkeep (units, ships, salaries)
- **OK** Emperor Marcus secured Madegi Doy
- **OK** Khan Tengri secured Kitesta
- **OK** Emperor Marcus: collected 140g in taxes from Madegi Doy (80 soldiers, 7 days, 360g remains)
- **OK** Khan Tengri: collected 17g in taxes from Kitesta (10 soldiers, 7 days, 483g remains)

### Turn 2

Orders parsed: 3 | Warnings: 0 | Seed: `1002`

- **OK** Khan Tengri waits 7 day(s)
- **OK** Khan Tengri is waiting (168 more hour(s))
- **OK** Emperor Marcus moved from Madegi Doy to Kitesta (cost: 4.7)
- **OK** Khan Tengri retreated from Kitesta
- **OK** Emperor Marcus defeated Khan Tengri in Kitesta (lost 0 units)
- **OK** Your forces were defeated by Emperor Marcus in Kitesta (lost 8 units)
- **OK** 500g accrued in tax pools (use TAX to collect)
- **OK** Paid 8.0g in upkeep (units, ships, salaries)
- **OK** 500g accrued in tax pools (use TAX to collect)
- **OK** Paid 0.2g in upkeep (units, ships, salaries)
- **OK** Khan Tengri: 1 pending (AWAIT)
- **OK** Emperor Marcus spotted Khan Tengri outside Kitesta with ~2 soldiers

### Turn 3

Orders parsed: 4 | Warnings: 0 | Seed: `1003`

- **OK** Khan Tengri has finished waiting
- **OK** Khan Tengri waits 7 day(s)
- **OK** Khan Tengri is waiting (168 more hour(s))
- **OK** Khan Tengri retreated from Kitesta
- **OK** Emperor Marcus defeated Khan Tengri in Kitesta (lost 0 units)
- **OK** Your forces were defeated by Emperor Marcus in Kitesta (lost 1 units)
- **OK** 500g accrued in tax pools (use TAX to collect)
- **OK** Paid 8.0g in upkeep (units, ships, salaries)
- **OK** 500g accrued in tax pools (use TAX to collect)
- **OK** Paid 0.1g in upkeep (units, ships, salaries)
- **OK** Emperor Marcus secured Kitesta
- **OK** Emperor Marcus: collected 140g in taxes from Kitesta (80 soldiers, 7 days, 1343g remains)
- **OK** Khan Tengri: 1 pending (AWAIT)

## Final board

| Faction | Sovereign cities | Occupied cities | Gold | Soldiers | Characters |
|---|---|---|---:|---:|---:|
| The Golden Empire | Madegi Doy | Kitesta | 1176.0 | 80 | 1 free / 0 prisoner / 0 dead |
| The Silver Horde | Kitesta | none | 1005.7 | 1 | 1 free / 0 prisoner / 0 dead |

## Checks

- PASS: three turns resolved - engine turn is 3
- PASS: orders were understood - 0 parser warnings
- PASS: movement and combat happened - Emperor Marcus won the Kitesta engagement
- PASS: occupation changed the board - Kitesta is secured by The Golden Empire
- PASS: reports and state were written - final state and player report are present

## Artifacts

- `state.json` - final persisted engine state
- `turn_events.jsonl` - structured event feed used by the master dashboard
- `orders/` - the exact human-readable orders for each turn
- `reports/` - player reports generated from each resolved turn
