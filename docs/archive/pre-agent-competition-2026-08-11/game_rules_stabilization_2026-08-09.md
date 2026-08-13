# Controlled Beta Game Rules Stabilization

This note records the boundary between implementation defects and game-design
choices after the Game Truth Audit. It does not change territorial ownership,
victory, defeat, faction activation, or turn-resolution architecture.

## Audit classification

### Confirmed implementation bugs

- A failed `SECURE` contention check did not stop execution, allowing more than
  one faction to secure the same city.
- `HEAL` cleared `is_dead` after raising health, duplicating resurrection.
- population-changing investment could leave `population` and
  `population_band` inconsistent instead of using the canonical band helper.
- `player_state()` returned every posted notice, including notices in cities
  the requesting faction did not observe.
- sailing selected and moved all co-located faction stacks, including stacks
  assigned to unrelated characters, and did not move grouped passengers.
- `MAX_ORDERS_PER_PLAYER` existed but was not enforced at submission parsing.

### Intentional or potentially intentional mechanics

- `controlled_city_ids` and `secured_city_ids` represent different concepts.
- Combat, death, capture, imprisonment, and `SECURE` do not transfer ownership.
- Character order programs persist across turns and support waits,
  conditionals, repeats, `STOP`, and `HALT IMMEDIATELY`.
- Orders are submitted simultaneously but execute through ordered phases that
  mutate one shared state.

### Undefined game-design decisions

- Whether sovereignty is permanent, conquerable, or distinct from occupation.
- What ends a game and what makes a faction defeated or eliminated.
- Whether unclaimed configured seats are active dormant factions, inactive
  seats, or neutral placeholders.

### Technical behavior testers must know

- Every configured seat creates a real faction, leader, start city, units, and
  resources even when no player has claimed it.
- Unclaimed factions receive no player orders but still participate passively
  in economy and defence; a later player inherits their accumulated state.
- A controlled city supplies its owner with tax generation and fortification
  benefits. Local security can allow a different faction to collect that tax
  pool; it does not change ownership.
- Seeded randomness is reproducible only together with the same faction/order
  iteration order and state.
- Queued programs can survive the current week and resume in later turns.

## Territorial ownership decision

### Model A: permanent homeland control

`controlled_city_ids` remains the permanent sovereign record. Occupation can
change forces, security, and access to local economic actions but never the
owner.

- **Taxation:** the homeland owner generates tax pools; an occupier may need an
  explicit collection rule to avoid surprising cross-faction collection.
- **Fortifications:** sovereign benefits remain with the homeland owner unless
  occupation is separately made relevant.
- **Reports/UI:** label sovereignty and security separately; never imply that a
  secured invader owns the city.
- **Victory:** cannot rely on territorial conquest and needs objectives, score,
  or administrative duration.
- **Empty factions:** retain economically and defensively meaningful homelands.
- **Notices/posting:** can remain a local-security privilege, independent of
  sovereignty.
- **Recapture:** means removing occupiers or restoring security, not changing an
  ownership field.
- **Persistence/save compatibility:** fully compatible with current saves.

### Model B: conquest transfers control

A defined conquest condition moves a city between factions' controlled sets.

- **Taxation:** generation and collection can follow the new owner after a
  clearly specified transfer time.
- **Fortifications:** the conqueror gains the existing fortification unless the
  rule also damages or resets it.
- **Reports/UI:** can show one current owner, but must report when and why a
  transfer occurred.
- **Victory:** territory can support elimination, domination, or scoring.
- **Empty factions:** passive seats can lose their starts before a player joins.
- **Notices/posting:** must define whether conquest removes, preserves, or hands
  over postings and security.
- **Recapture:** is another ownership transfer under the same condition.
- **Persistence/save compatibility:** old saves load, but need normalization for
  duplicate/missing ownership and a rule for historical security state.

### Model C: ownership plus occupation

Keep de-jure ownership and add a distinct current occupation/control record.

- **Taxation:** rules can split generation, collection, and denial between the
  owner and occupier, but each flow must be explicit.
- **Fortifications:** occupation can determine their current military user while
  sovereignty remains visible.
- **Reports/UI:** must display two statuses clearly and increases tester-facing
  complexity.
- **Victory:** can score sovereignty, occupation, or both.
- **Empty factions:** retain claims while their land can be occupied before a
  late join.
- **Notices/posting:** can follow occupation/security while ownership remains
  unchanged.
- **Recapture:** removes occupation and restores effective control without
  rewriting sovereignty.
- **Persistence/save compatibility:** requires a new persisted field and a
  migration default, normally occupation equal to existing ownership.

### Accepted decision: enduring sovereignty + temporary operational occupation

- **Status:** accepted
- **Choice:** enduring sovereignty + temporary operational occupation
- **Reason:** makes cities strategically meaningful while preserving SOE's
  agent/logistics/hidden-order identity
- **Trade-off:** more territorial semantics than permanent homeland, but avoids
  conquest-map gameplay and requires no new persistent state
- **Revisit when:** victory/campaign objectives are designed or playtesting
  shows occupation is too weak or strong

`controlled_city_ids` remains enduring sovereignty. `secured_city_ids` records
temporary operational occupation, established by SECURE and maintained only by
a living, free character inside with ordinary soldiers in the same local group.
Sovereignty generates the tax pool. The valid occupier, otherwise the
sovereign, has current recruitment, tax collection, fortification, and local
administrative rights. Combat can clear occupation but cannot establish it.

### Accepted decision: occupation establishment requires uncontested qualifying presence

- **Status:** accepted
- **Context:** gameplay replay proved 1 soldier could SECURE against 175
  hostile soldiers and that sovereign pre-SECURE was an unintended first-mover
  latch
- **Choice:** new occupation may be established only when no other faction has
  a qualifying garrison inside
- **Reason:** restores combat/physical displacement as meaningful without
  adding force ratios or a new subsystem
- **Trade-off:** two qualifying factions may leave a city temporarily
  unoccupied until one is displaced
- **Revisit when:** multiplayer playtesting shows persistent stalemates are
  common or alliances require consensual shared administration

This refines *establishment* only; the maintenance decision above is unchanged.
SECURE now succeeds only when the actor satisfies the existing eligibility
requirements, the city has no valid foreign occupation, and no other faction
holds a qualifying garrison inside it. The check reuses the one authoritative
`has_qualifying_garrison` predicate through
`territory.has_competing_qualifying_garrison`; it counts factions, never
soldiers, so force size, morale, fortification, and equipment are irrelevant to
it. Because occupation is exclusive administrative control, an *allied* foreign
garrison blocks establishment exactly as a hostile one does, and no
treaty/consent mechanic was added. Sovereignty is not special-cased: a
sovereign with a qualifying garrison blocks a foreign SECURE without having to
pre-SECURE its own city.

Establishment and maintenance stay apart. A foreign faction marching into an
occupied city does not cancel the occupation, and a faction renewing SECURE
over an occupation it already validly holds is not asked to clear the ground
again. Reconciliation is untouched, so persisted `secured_city_ids` load and
lapse exactly as before, including saves where a rival also happens to be
inside. ATTACK → SECURE in one submission still works as the hidden-order
gamble it was: if the fighting leaves no qualifying enemy garrison by the
SECURE checkpoint, the order lands; if any qualifying group of theirs survives
— including one the ATTACK never targeted — it fails. No SECURE cost or
cooldown was added; a barred SECURE simply fails until the obstacle is gone.

## Victory and defeat decision

### Option 1: sandbox beta

Run an announced number of turns and end the session administratively. There is
no strategic winner and no faction elimination. This is the smallest honest
rule for exploratory testing, but it gives players no comparative end goal.

### Option 2: elimination

Define defeat from an approved combination of leader state, living characters,
territory, units, and resources. Each input has recoverability and edge cases;
no combination should be inferred from current engine accidents.

### Option 3: objective victory

Award victory for explicit strategic objectives. This can focus play better
than total elimination but needs objective definitions, visibility rules, tie
handling, and persistence.

### Option 4: score / fixed-duration game

Run a known number of turns, then calculate a winner from approved metrics.
This gives a clear finish and preserves defeated players' ability to act, but
the chosen metrics will shape beta play and must not accidentally reward
unclaimed-seat exploitation.

**Controlled-beta recommendation:** Option 1 for the first controlled session:
announce a short fixed duration and close it administratively, explicitly with
no strategic winner. If comparative competition is required, choose Option 4
only after its metrics are approved. No victory framework is implemented.

## Empty-seat decision

### A. Active dormant factions

This preserves current behavior and saves. Late joiners receive an economically
processed faction, but empty seats occupy map space, can be attacked, affect
victory calculations, and may gain or lose value without player agency. Room
creation remains simple and all configured starts exist immediately.

### B. Seats activate only when claimed

This improves economic fairness between absent and present players only if
activation timing and protection are specified. The map needs a pre-claim
ownership presentation, inactive forces must be non-participating or absent,
attackability must be defined, victory must ignore inactive seats, room creation
must track activation, and old saves need activation-state migration.

### C. Neutral placeholders

This makes unclaimed land an explicit part of the world and keeps it attackable,
but neutral economy, forces, diplomacy, and conversion on claim all need rules.
Late joiners may inherit a damaged placeholder or require protected allocation.
Map ownership and victory become clearer than invisible inactivity, at the cost
of new entity/state and save migration.

**Controlled-beta recommendation:** A, active dormant factions, because it is
the only option requiring no new lifecycle or migration. Mitigate fairness by
filling seats before turn one and disallowing late joins after resolution starts.
This policy recommendation is not implemented.

## Resolution semantics

**Simultaneous submission with deterministic sequential execution.**

- Submission timing does not grant initiative.
- Fixed phase order matters; movement and sailing occur before combat.
- Within a phase, factions and their orders mutate shared state in deterministic
  iteration order. Earlier otherwise-legal actions can therefore win contention;
  for example, the first legal `SECURE` in faction/order iteration order wins.
- Seeded randomness combines with execution ordering; the same seed alone does
  not make differently ordered inputs equivalent.
- Waits and other queue controls can defer programmed actions into later hours
  or turns, so not every submitted action resolves in its submission week.

The controlled beta must not describe this as fully simultaneous resolution.
