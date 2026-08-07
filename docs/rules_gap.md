# Rule Coverage (Alpha)

Status of `rules.md` mechanics in the alpha engine. Line references have been
dropped: they went stale as the code moved. Use the named modules instead.

## Headline numbers

| Axis | Coverage |
|---|---|
| Command verbs recognised | **89 of 89 (100%)** — as of v1.1.0 every verb in `rules.md` is recognised |
| Order-language features | **8 of 9** (`HAVE` delegation, `and` target lists, `REPEATEDLY`, groups, pronouns, `and`-chained commands, `IF`, `THEN`) — `QUIETLY`/`SILENTLY` parse but do not yet suppress report lines |
| Turn model | Persistent order queue, advanced one pass per weekly turn; the rules specify hour-level asynchronous time |

Counted by cross-referencing the command sections of `rules.md` against
`parser.ORDER_KEYWORDS`. "Recognised" means the parser routes the verb and the
engine has a phase for it — not that every sub-rule of that command is honoured.

## Commands implemented (89)

ALL commands from `rules.md` are recognised. The v1.1 closure added the last
eight: WORK, TRAIN, UNNAME, CREATE, INVEST, BUY PASSAGE, PREACH and OFFER.
See the "Implemented end-to-end" and "Partial" sections below for what each
still simplifies.

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
| `and` to chain commands | implemented — one sentence carries several orders; see `parser.split_clauses` |
| `THEN` sequencing | implemented — a clause separator (`wait for 2 weeks and then go to Salem`); a pause across turns still comes from the queue behind a WAIT |
| `QUIETLY` / `SILENTLY` | partial — both parse as clause adverbs, but report-line suppression is not implemented (the `silent` flag is recorded on the order and unused) |
| `IF` statements | implemented — condition evaluated when the order is reached on the queue; `else`/`otherwise` supported; scope is the rest of the sentence; never nested. Conditions: gold, recruitable ranks, resources, galleys, summoned creatures, magic/religious power, encumbrance (by group size). Evaluated at turn start, so conditions reflect the state the character begins the turn with rather than after this turn's own preceding orders (see Partial). |
| Pronouns (him/her/them/it) | implemented (resolved before verb dispatch; see `pronouns.py`) |

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

- **WORK** — the actor and their group labour for wages that scale with the
  location's population band; TINY towns pay nothing (voluntary community
  service) and high-skill characters sell their skills for a bonus where
  there is work to sell it into. (`engine.process_work`, `config.WORK_*`)
- **TRAIN** — workers become soldiers (combat skill ≥ 10) or sailors (sailing
  skill ≥ 10). rules.md sizes the work by skill — 70 × trainees / skill days —
  so a weekly turn converts what the skill supports and the rest stays in the
  pool. `sailing_skill` was added to characters and wired into STUDY/TEACH.
  (`engine.process_train`, `config.TRAIN_*`)
- **UNNAME** — a named character with nothing of their own becomes one worker
  in their group leader's group; the lead character cannot be unnamed (the
  engine declines to implement the rules' quit-the-game mechanic).
  (`engine.process_unname`)
- **CREATE (elite troops)** — named units formed from a group's soldiers
  (`EliteUnit` in `models`), starting at combat level 1. They train
  continuously (one partial point per week; five partial points = one level),
  fight at their own level (`combat.calculate_faction_power`), take
  casualties like any force, draw salary of size × level per month prorated
  to a week (`process_income_and_upkeep`), travel with their group leader
  (`sync_elite_locations`), and cannot TAX/SECURE/BUILD/MINE/WORK/GATHER or
  row because they are not characters and never receive orders. The status
  report shows them (`reporting`).
- **INVEST** — gold goes into a per-city pool (`GameState.invest_pools`);
  each week the check (`engine.process_invest_weekly`) spends about
  population/100 gold and raises the population by the same amount (with
  scatter, capped per week). Cities get a numeric `population` (band midpoint
  until first measured) and step up their income band when growth crosses a
  threshold. Ruins cannot be invested in; the investor need not be present.
- **BUY PASSAGE** — travel one direct sealane hop without owning a ship, at a
  fare equal to the party's size in gold. The rules charge the group's
  encumbrance instead, which `encumbrance.group_encumbrance` can now supply;
  head-count stands in until that is switched over. Passage may fail — the
  bigger the group the worse the odds —
  and `definitely` helps. A failure refunds the fare. (`engine.process_passage`)
- **PREACH** — donations scale with religion skill, location population and a
  random day-to-day factor; followers (1-3 workers) sometimes join.
  (`engine.process_preach`, `config.PREACH_*`)
- **OFFER** — independent characters (from `players.yaml` under
  `independent_characters`, or any `is_npc` faction) accept an offer of at
  least half the square of their highest skill plus item value; characters
  under another player's control always decline; one's own prisoners always
  accept (released and recruited). An accepted offeree brings their whole
  group, units, ships and elite units with them (`_transfer_ownership`).
  Orders chained after the offer ("Offer ... and have her come to Pomye") run
  if it is accepted and fail with a warning if it is refused.
  (`engine.process_offer`, `cli.init_game`)
- **IF statements** — `if <condition> then <orders>` with `else`/`otherwise`;
  scope is the rest of the sentence; no nesting. The condition is stored by
  name and evaluated when the order is reached on the queue, then only the
  chosen branch's orders run (`engine.process_if_orders`). Conditions cover
  gold, soldiers/sailors/workers/slaves, resources, catapults/weapons/armor,
  galleys, summoned creatures, magic/religious power (with `magic`/`religion`
  modifiers, or the higher of the two), and encumbrance (approximated by
  group head-count). Pronoun resolution already handled "take it" style
  amounts before IF parsing.
- **THEN sequencing** — `then` chains clauses like `and` ("wait for 2 weeks
  and then go to Salem" is a WAIT then a GO; the queue already holds orders
  behind a wait).
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
- **Communication** — `SAY` and `TELL` carry a message to named characters of
  any faction, to everyone at a town, or to every player (`everyone`); there is
  no cost and no distance limit, per the rules' "inexpensive and readily
  available magic", and a message sent to a prisoner reaches their own player.
  `POST` nails a notice to the gates of a town the faction has secured, and it
  comes down on an empty message or when the town is no longer secured.
  `REPORT` and `QUERY` describe a character, their group and what they can make
  out of the location under the ordinary fog rules, with `briefly` for the
  short form. `ADDRESS` and `PASSWORD` change the player's own details.
  Message bodies are lifted out of the order text before it is lowercased,
  comma-stripped and split on periods, so a message keeps its exact characters
  and pronoun resolution never rewrites what a player wrote.
  (`parser.protect_quotes`, `engine.process_messages`, `process_post`,
  `process_report`, `process_address_and_password`, `expire_postings`)
- **Pronouns** — `me`/`I`/`you` resolve to the lead character, `him`/`her` to
  the most recently named person of that gender who is neither the agent of the
  current order nor the leader, `it` to the last single item, unnamed character
  or quantity of a mass noun, `them` to the last group or list, and the
  reflexives to the agent. Referents carry from one sentence to the next within
  a submission, which is what the rules' examples need. Resolution is a
  substitution pass over the sentence before verb dispatch, so no verb parser
  knows pronouns exist. A pronoun with nothing to bind to is left in place and
  reported as an unknown name rather than silently bound to the wrong actor.
  (`pronouns.py`, `parser.parse_orders`)
- **Magic-free zones** — a city flagged `is_magic_free` drains the magic power
  of everyone standing in it and of every item they carry, and nothing
  regenerates there. One sweep runs after all movement has resolved, so
  walking, sailing, flying and being teleported in are all caught.
  (`engine.process_magic_free_zones`, `items.drain_magic_free_zone`)
- **And-chained commands** — one sentence carries several orders, split by
  `parser.split_clauses` at the `and`s that separate whole commands from the
  `and`s that list items inside one. The HAVE form's actor sticks to the
  clauses that follow it (`Have him go to Riverton and tax for 3 weeks, and go
  to Ennistown and tax` is four orders to the same character), a counted
  continuation inherits the previous verb (`Give 50 gold to Nancy Myers and 20
  horses to Bill Fenton`, `recruit 5 soldiers and 3 workers`), and a clause
  whose target rides in the tail gets it folded back (`assign 20 soldiers and
  23 horses to Bill Jenkins` splits into one order per kind). `PURCHASE`
  parses as `BUY`. Titles are stripped from names (`Assign 200 soldiers to
  Captain Bill Jones`). GIVE/TAKE now move mass resources (`Give 50 armor to
  Thomas Ames`, `Take 10 copper and 20 silver from Bill Hawthorne`, a bare
  `give stone to X` for everything collected), and the prepositionless give
  (`Give Pindimya 10 gold`) and `have him to go to Kitesta` forms parse.
  (`parser.split_clauses`, `pronouns._resolve_him_her`,
  `pronouns._resolve_it_them`, `engine.process_assign`, `engine.process_get`)

## Partial

- **Order-queue timing** is turn-granular. A wait of one hour and a wait of one
  day both cost a turn, and a loop body runs at most once per turn, because the
  engine has no clock finer than a weekly turn. An IF condition is evaluated at
  the start of the turn it is reached, against the world as the character
  begins it — not after this same turn's preceding orders have run, which the
  rules' asynchronous engine would provide.
- **TRAIN** converts what one week can produce rather than holding the order
  across several turns; the rules' training spans days, which the queue could
  model once sub-turn time exists.
- **BUY PASSAGE** prices a party by head-count instead of encumbrance, and the
  rules' `via` multi-stop form (`Travel to Im Prok via Amesbok`) is not
  parsed — each hop must be ordered separately, as the rules allow.
- **OFFER** acceptance is deterministic (no hidden variation between NPCs),
  and the rules' flavour — independents who will never accept, or players'
  characters who might jump ship when unpaid — is not modelled. An NPC is
  resolved for orders (including "have <npc> come to ...") from the turn they
  are offered to.
- **CREATE** elite units can neither be handed to another group leader nor
  disbanded once formed; they follow their creator's group for life.
- **INVEST** uses the city's exact `population` when the map provides one,
  and the band-midpoint until a city without one is first measured, so a
  TINY town's weekly spend is approximated; the population growth cap keeps
  a huge pool from exploding a town in one turn.
- **PREACH** attracts only workers; the rules' rare skilled converts and the
  wider miracle table are absent.
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
- **SCAN** works off a real orb and prices distance in map miles (one power
  per ten miles, per the rules) when the route carries `distance_miles`;
  maps without mileages fall back to the movement-cost conversion
  (`config.ORB_POWER_PER_HOP`). The distance is measured over roads *and* sea
  lanes, since an orb follows neither — an island reachable only by water can
  still be scanned. It remains an approximation: the rules take distance off
  the drawn map ("crow-flight"), and route mileage is longer than a straight
  line, so a scan over winding roads costs more than it should. Map
  coordinates are presentation-only and not to scale, so there is nothing
  better to measure yet. One order carries one orb — the rules' form pairing
  several city groups with several orbs in one sentence is rejected rather
  than misread.
- **Magical items** are not lost or looted when their holder dies: an item stays
  with the body rather than falling to the victor, because `rules.md` does not
  say what should happen and the items are indestructible. Item weight and
  encumbrance are likewise unmodelled, so carrying six crystals costs nothing.
- **QUERY** parses and reports, but it is not yet more immediate than `REPORT`.
  The rules have QUERY reach a subordinate who is busy and get an answer out of
  turn; the engine has no sub-turn clock, so both verbs answer at the same
  point in the turn.
- **REPORT** does not scale its detail with city size or group size the way the
  rules describe. It uses the same fog roll as an end-of-turn sighting.
- **Pronouns** resolve position-by-position: each `him`/`her`/`it`/`them`
  binds to what was most recently named before it, so a sentence can use the
  same pronoun for two different people, and the two-them form of the rules
  (`Purchase 20 horses and assign them and 2 sailors ... assign them to Joe
  Flint`) comes out right. A pronoun naming a multi-character actor (`them`
  for "Joe Flint and Mary Wise") resolves to the list text, but the verb
  parsers still act on single actors, so a group-level order warns honestly.
  Multi-item GIVE/TAKE lists hand over each kind in its own order.
- **Amulets** cover trading and combat. The rules allow an amulet for any skill
  except magic and religion; the engine only has fields for the skills it
  actually uses (`items.AMULET_SKILLS`).
- **Population-based security** (how hard it is to lurk under enemy SECURE) is
  approximated by city population band only; SECURE does not yet raise local
  detection odds beyond making the securer visible from outside.

## Not implemented

- Sub-turn game time, and with it the rules' partial-progress accounting for a
  BUILD or FORTIFY interrupted part-way through, `until <date>` and
  hour-level waits.
- Horses, wagons, armour, weapons, catapults, battering rams and siege towers
  as *carried* things. `encumbrance.py` weighs people, unit stacks, mined
  substances and purses to Appendix B, which is what `FLY` and `TELEPORT` now
  charge for; the Appendix B figures for the rest are recorded in
  `UNMODELLED_ENCUMBRANCE` but contribute nothing until those items are tracked
  as cargo. With them absent, the horse/wagon rules that lighten a group on
  land, and the land-speed bonus for horses, are also still missing.
  `BUY PASSAGE` fares and IF encumbrance checks continue to use head-count and
  could now be switched to `encumbrance.group_encumbrance`.
- Item weight: magical items are weightless, so carrying six crystals costs
  nothing to fly.
- `QUIETLY`/`SILENTLY` report suppression (the adverbs parse; the `silent`
  flag on orders is recorded and unused).
- Retreat and morale in combat.
- Elite troops' restrictions are enforced structurally (they cannot take
  orders), but they cannot be reassigned between leaders or disbanded.
- Group-level possession of ships, resources and gold; combat still totals a
  faction's strength at a location rather than resolving group by group.
- Resource depletion (accumulation and its cap are in; depletion is not).
- Religion's `PREACH` follower variety and the wider miracle table.
- Named-character hiring, education and the starting-character creation phase.

See [`audit_2025-11.md`](audit_2025-11.md) for the defects fixed in v0.7.1 and
the design debt closed in v0.7.2.
