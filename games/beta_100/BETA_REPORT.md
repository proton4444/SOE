# SOE — Beta 100-turn system test

- **Game ID:** `beta_100`
- **Map:** `sample_map.json`
- **Turns completed:** 100 / 100
- **Wall time:** 0.5s (0.005s/turn)
- **Base seed:** 20260807 (per-turn seed = base + turn)
- **Parse warnings (total):** 0
- **Combat-tagged events:** 21
- **Engine errors:** 0

## Players (independent AIs)

- **The Golden Empire** (`player_1`), leader *Emperor Marcus*, start `madegi_doy`, style `religious`
- **The Silver Horde** (`player_2`), leader *Khan Tengri*, start `kitesta`, style `military`

## Final standings

| Faction | Controlled | Secured | Gold | Soldiers | Workers | Alive | Ships |
|---------|----------:|--------:|-----:|---------:|--------:|------:|------:|
| The Golden Empire | 1 | 4 | 1009.3 | 117 | 42 | 1 | 0 |
| The Silver Horde | 1 | 3 | 691.0 | 4 | 0 | 0 | 0 |

### Controlled / secured cities

- **The Golden Empire** controlled: madegi_doy; secured: hakkaba, kitesta, madegi_doy, riverton
- **The Silver Horde** controlled: kitesta; secured: hakkaba, kitesta, madegi_doy

### Characters

**The Golden Empire**
- Emperor Marcus @ `kitesta` — combat 10, magic 5, religion 52 (power 52), gold 1009.3, hp 100

**The Silver Horde**
- Khan Tengri @ `madegi_doy` — combat 10, magic 5, religion 0 (power 0), gold 691.0, DEAD, prisoner

## Trajectory (every 10 turns)

| Turn | P1 sec | P1 gold | P1 sol | P2 sec | P2 gold | P2 sol |
|-----:|-------:|--------:|-------:|-------:|--------:|-------:|
| 1 | 1 | 978.8 | 40 | 1 | 950.0 | 40 |
| 10 | 1 | 437.0 | 117 | 3 | 727.0 | 4 |
| 20 | 2 | 462.4 | 117 | 3 | 723.0 | 4 |
| 30 | 3 | 539.4 | 117 | 3 | 719.0 | 4 |
| 40 | 3 | 574.3 | 117 | 3 | 715.0 | 4 |
| 50 | 4 | 752.3 | 117 | 3 | 711.0 | 4 |
| 60 | 4 | 696.7 | 117 | 3 | 707.0 | 4 |
| 70 | 4 | 784.7 | 117 | 3 | 703.0 | 4 |
| 80 | 4 | 839.7 | 117 | 3 | 699.0 | 4 |
| 90 | 4 | 899.7 | 117 | 3 | 695.0 | 4 |
| 100 | 4 | 1009.3 | 117 | 3 | 691.0 | 4 |

## Top event types (engine log)

- `upkeep`: 300
- `income`: 200
- `debt`: 100
- `preach`: 91
- `bless`: 78
- `spotted`: 76
- `move`: 76
- `secure`: 71
- `tax_failed`: 68
- `secure_failed`: 60
- `invest`: 27
- `invest_growth`: 27
- `recruit`: 12
- `study_success`: 12
- `offer_rejected`: 9
- `victory`: 9
- `defeat`: 9
- `tax_success`: 3
- `attack_declined`: 3
- `recruit_failed`: 2
- `fly_failed`: 2
- `capture_success`: 2
- `escape`: 1
- `capture_failed`: 1

## Systems observations

- **Engine stability:** full 100-turn run with deterministic seeds; no exceptions.
- **Parse quality:** zero parse warnings on bot-generated English orders.
- **Movement:** multi-hop paths respect MP budgets (e.g. Madegi→Peshandi is 13.8 MP > 10; bots must stage via Kitesta).
- **Secure vs control:** `SECURE` updates `secured_city_ids`; income still keys off `controlled_city_ids` (starting cities). Expansion therefore changes security more than the controlled-city income list.
- **Combat:** repeated co-location at Hakkaba produced victory/defeat and capture events; P2 leader ended dead+prisoner.
- **Tax/secure contention:** many `tax_failed` / `secure_failed` when the other faction already held security on the town.
- **Unit stacks:** recruits create many small stacks rather than merging (cosmetic for play; report lists them separately).
- **Upkeep:** large armies drain gold; soft recruit caps keep the expand bot solvent over 100 weeks.

## Verdict

**PASS** — 100 turns finished without engine crash. Only **The Golden Empire** still has free living characters.
Systems exercised: movement, recruit, tax, secure, expand, combat/capture, study, invest, preach/pray/bless/heal/offer, fog sightings, upkeep.

## Artifacts

- Game state: `games/beta_100/state.json`
- History: `games/beta_100/history.jsonl`
- Sample reports: `games/beta_100/reports/`
- Orders: `games/beta_100/orders/`
