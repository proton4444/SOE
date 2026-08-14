# Review Corrections — 2026-08-13

Status: **in progress** — Waves 1–2 and Wave 4 (C1–C23, C33–C37) closed  
Date: 2026-08-13  
Source: project-wide code review (engine, parser, webapp, AI/arena; 112 Python files)  
Rules authority: [`MECHANICS.md`](../MECHANICS.md)

This is a correction register, not a product spec. Each item is a defect or
gap found in the current tree, with the change that closes it. Do not treat
completion of a file edit as done until the named test exists and fails on the
pre-fix code.

Severity:

- **bug** — wrong command, wrong state, security/integrity break, or a Phase 0
  guarantee that does not hold
- **suggestion** — real risk or DX break that is not itself a rules defect
- **nit** — dead code, docs mismatch, or low-probability edge

## Verdict

The turn loop, gold helpers, occupation model, atomic JSON saves, per-room
authz, and turn rollback are sound. The corrections below are the remaining
rules and integrity breaks: some written orders never run or run as a different
command; group-priced magic leaves the party behind; any room host can steal
the server LLM key; adversary text is concatenated into bot prompts without the
quoting the module claims; official arena probes and resume hashes do not
enforce the guarantees they advertise.

## Wave 1 — security and integrity

Close these before the next exposed beta or official arena run.

**All six are closed.** Each named test was confirmed to fail against the
pre-fix source before the fix was accepted.

### C1. Operator-only LLM settings

- Severity: bug
- Status: **closed** — `SOE_OPERATOR_KEY` (or loopback when unset) gates both
  write routes; `llm_settings.base_url_error` allowlists the destination and
  `effective()` ignores an off-allowlist persisted value; a base URL changed in
  the same submission is saved but not probed.
  Tests: `tests/test_llm_settings.py::test_host_session_cannot_change_llm_settings`,
  `::test_operator_cannot_point_the_key_at_a_foreign_host`,
  `::test_persisted_off_allowlist_base_url_is_ignored`,
  `::test_probe_refuses_a_just_changed_base_url`.
- File: `webapp/main.py:576` (`_apply_llm_settings`, also room `POST /setup/llm`)
- Defect: Any valid host cookie can change the process-wide LLM config.
  Creating a room is enough. An arbitrary `base_url` is persisted, and
  `action=probe` POSTs `Authorization: Bearer <key>` to that URL. Leaving the
  key blank keeps the operator key (`effective()`), so a host can exfiltrate
  it or overwrite/clear the key every bot on the process uses.
- Correction: Treat LLM settings as operator-only (separate secret, not “any
  host session”). Allowlist `base_url` (https + known hosts), or ignore a file
  `base_url` unless `SOE_LLM_BASE` is unset *and* the URL is on a fixed
  allowlist. Do not send the live key to a just-changed URL without an
  out-of-band confirm.
- Test: host session cannot change `base_url` or probe with a blank key
  against a non-allowlisted host; operator path still can.

### C2. Confine `GET /map/{name}`

- Severity: bug
- Status: **closed** — `_map_path` requires a bare filename and a resolved path
  under `maps/`; the route 404s unless the name is in `available_maps()`.
  Test: `tests/test_webapp_map.py::test_map_preview_is_confined_to_the_maps_directory`.
- File: `webapp/mapview.py:127`, `webapp/main.py:348`
- Defect: `_map_path` is `_MAPS_DIR / map_file` with no confinement. The
  preview route is unauthenticated and does not check `available_maps()`.
  `{name}` cannot contain `/`, but encoded `..%5C` / `..%2F` can leave
  `maps/` on Windows. `load_raw_map` then reads any readable file.
- Correction: Reject names that are not `Path(name).name`, require
  `resolved.is_relative_to(_MAPS_DIR)`, and 404 unless
  `name in available_maps()`.
- Test: `..%5Cserver_data%5Cllm_settings.json` and `..%2F…` return 404;
  allowlisted map names still render.

### C3. Quote untrusted text in the strategist prompt

- Severity: bug
- Status: **closed** — `context.quoted_block` fences and line-quotes the report,
  intel and field sections; `neutralize_untrusted` blanks instruction-shaped
  lines there and in posted-message bodies; the system prompt names those
  sections untrusted. Deterministic, so webapp/arena prompt parity holds.
  Tests: `tests/test_phase0_context.py::test_report_cannot_forge_an_orders_block`,
  `::test_posted_messages_are_neutralized_in_the_state_view`,
  `::test_system_prompt_declares_untrusted_sections`,
  `::test_neutralizer_leaves_ordinary_report_prose_alone`.
- Note: this changes `prompt_signature`, so an arena bundle started before this
  commit will refuse to resume. Finished runs and their evidence are unaffected.
- File: `webapp/ai/context.py:326` (`user_prompt`, `player_state_from_state`)
- Defect: The docstring says adversary report content and posted messages are
  “presented as quotes, never as instructions.” Both are concatenated raw.
  `test_adversary_report_is_delimited_as_data` only asserts the evil string
  stays out of the system role.
- Correction: Put report text and posted-message bodies in delimited, quoted
  data blocks. Add an explicit system rule that those sections are untrusted
  observations. Strip or neutralize instruction-like lines (`--- ORDERS ---`,
  “ignore previous”) before they enter the prompt.
- Test: a POST/report containing `--- ORDERS ---` / “ignore previous” does
  not appear as an instruction block; the system role forbids treating that
  section as orders.

### C4. Lock `rooms.json` writes

- Severity: bug
- Status: **closed** — `save()` holds `self._lock` across build and replace,
  `RoomStore.transaction()` wraps `store_submission` / `store_reports`, and each
  write uses a pid+token temp name.
  Tests: `tests/test_room_registry.py::test_concurrent_submit_and_join_cannot_drop_a_write`,
  `::test_save_does_not_share_one_temp_file`.
- File: `webapp/rooms.py:142` (`save`, `store_submission`, `store_reports`)
- Defect: `save()` is not under `self._lock`. Two `save()` calls share
  `rooms.json.tmp`; last `replace` wins. Join + submit + resolve can drop a
  seat or a turn of orders even with `--workers 1` (sync routes run in the
  threadpool).
- Correction: Hold `self._lock` for the whole of `save()` and every mutation
  that then saves. Use a unique tmp name per write (as
  `service._atomic_write_text` already does).
- Test: concurrent `store_submission` + `join` + `save` cannot drop a
  recorded submission.

### C5. Stop 4-digit PIN brute force

- Severity: bug
- Status: **closed** — `MAX_PIN_ATTEMPTS` (5) consecutive misses lock joining for
  `PIN_LOCKOUT_SECONDS` (15 min), per room; a success clears the streak and the
  PIN is compared with `compare_digest`. A timed lock keeps a code-holder's
  griefing a nuisance rather than a lobby takeover.
  Tests: `tests/test_room_registry.py::test_join_locks_the_room_after_repeated_wrong_pins`,
  `::test_a_valid_pin_still_joins_before_the_lock`, `::test_the_lockout_is_per_room`.
- File: `webapp/rooms.py:202`
- Defect: Join PIN is `secrets.randbelow(10000)` with no rate limit or
  lockout. Room codes are in the URL and the room page is visible without
  auth.
- Correction: Lock the room after N failed PINs, add per-IP/per-code delay,
  or replace the PIN with a high-entropy invite token bound to the room.
- Test: N+1 failed PIN attempts refuse further guesses; a valid PIN still
  joins before the lock.

### C6. Sanitize arena blueprint ids

- Severity: bug
- Status: **closed** — one `arena.blueprint_path()` helper (`^[a-z0-9][a-z0-9-]*$`
  plus `is_relative_to`) serves all four read sites; `RunBundle.copy_blueprints`
  confines the write side to its own `blueprints/`.
  Tests: `tests/test_phase0_arena.py::test_blueprint_ids_cannot_escape_the_blueprint_directory`,
  `::test_manifest_rejects_a_traversing_blueprint_id`.
- File: `scripts/arena.py:428`, `scripts/arena.py:1907`,
  `scripts/arena_bundle.py:266`
- Defect: `blueprint_id` is joined unsanitized onto `configs/blueprints/`.
  A value such as `../../server_data/llm_settings` reads the API-key file
  into `doctrine_section` and can write a copy outside
  `games/arena/<run_id>/blueprints/`.
- Correction: Allow only `^[a-z0-9-]+$`, or resolve and require
  `is_relative_to(configs/blueprints)` and
  `is_relative_to(bundle.blueprints_dir)` before read/write.
- Test: `../../server_data/llm_settings` is rejected; `expansionist-v1`
  still loads.

## Wave 2 — written order ≠ executed order

These make a player (or bot) issue a command the engine does not honour.

**All seventeen are closed.** Each named test was confirmed to fail against the
pre-fix source before the fix was accepted.

### C7. Revive NAME

- Severity: bug
- Status: **closed** — `parse_name_order` resolves the actor (HAVE or implicit
  leader); short names fail with a warning and are not padded; `process_name`
  takes a stack in that character's group at their city.
  Tests: `tests/test_review_corrections_wave2.py::test_implicit_name_creates_a_character_from_a_local_stack`,
  `::test_have_name_creates_a_character_from_a_local_stack`,
  `::test_short_names_fail_loudly`,
  `::test_name_does_not_consume_a_distant_stack`.
- File: `soe/parser/verbs_units.py:291`, `soe/phases/units.py:540`,
  `soe/phases/common.py:42`
- Defect: `parse_name_order` sets `actor_id = player_id` (faction id).
  Validation looks that up as a character and `process_name` skips warned
  orders. A valid `Name male soldier Joe Henley` never creates a character.
  The HAVE form in the docstring is ignored. Short names are padded with
  unseeded `random.randint` and warned, which would skip them even after the
  actor-id fix. Engine NAME also takes the first live stack of that type
  anywhere on the map.
- Correction: Resolve the actor through `parser.resolve_actor`. Require a
  stack in that character’s group at their city. Reject short names (or pad
  from a seeded source) without marking a still-executable NAME as warned.
- Test: implicit and HAVE NAME create a character from a local stack;
  short names fail loudly; a distant stack is not consumed.

### C8. TELEPORT / FLY must move the group that was priced

- Severity: bug
- Status: **closed** — both spells call `groups.move_group` then write the
  leader's city, the same way land movement does.
  Tests: `tests/test_review_corrections_wave2.py::test_teleport_moves_the_soldiers_that_were_priced`,
  `::test_a_lone_wizard_still_flies_alone`.
- File: `soe/phases/magic.py:45` (`:60`, `:94`)
- Defect: Power uses `group_encumbrance` (leader + subordinates + owned
  units) but only the wizard/target `location_city_id` is written. Units and
  members stay behind. The existing teleport test asserts the 21-power bill
  for 20 soldiers and never checks they moved.
- Correction: Call `groups.move_group` the same way land movement and
  passage do.
- Test: a leader with 20 soldiers pays group cost *and* the soldiers arrive;
  a lone wizard still moves alone.

### C9. GET join must attach

- Severity: bug
- Status: **closed** — the no-cargo form calls `groups.attach`; `get_join` is
  logged only on success.
  Test: `tests/test_review_corrections_wave2.py::test_get_with_no_cargo_attaches_the_donor`.
- File: `soe/phases/finance.py:44`
- Defect: The character-join form logs `get_join` and returns without
  `groups.attach`. The order is a no-op that looks like a join.
- Correction: Call `groups.attach(donor, recipient, game_state)`. Log
  refusal if attach fails; emit `get_join` only on success.
- Test: after `GET` with no gold/units/resources, donor is in recipient’s
  group.

### C10. GET units must honour ownership

- Severity: bug
- Status: **closed** — GET mirrors ASSIGN: donor-owned stack first, then
  unowned local pool; received stacks are owned by the recipient.
  Tests: `tests/test_review_corrections_wave2.py::test_get_cannot_pull_another_characters_troops`,
  `::test_received_troops_travel_with_the_recipient`.
- File: `soe/phases/finance.py:82`
- Defect: GET of units selects the first same-faction, same-city stack of
  that type, ignoring `owner_character_id`. New stacks are created without
  an owner, so they land in the faction pool and do not travel with the
  recipient. ASSIGN already does owner-first selection.
- Correction: Mirror ASSIGN: donor-owned stack first, then unowned local
  pool; merge onto a stack owned by the recipient.
- Test: GET cannot pull another character’s troops; received troops travel
  with the recipient.

### C11. Possessive `her` must not flatten percent invest

- Severity: bug
- Status: **closed** — `\bher\b` is left alone when the next word is a
  possession noun (`her gold`, `her soldiers`), so the invest/offer percent
  regex still matches.
  Tests: `tests/test_review_corrections_wave2.py::test_percent_invest_of_her_gold_uses_the_agents_purse`,
  `::test_percent_offer_of_her_gold_uses_the_agents_purse`.
- File: `soe/pronouns.py:256`, `soe/parser/verbs_economy.py:480`
- Defect: `\bher\b` is always the object pronoun. After another woman is
  named, `Have Mary Wise invest 75 percent of her gold in Redport` rewrites
  to `… of nancy myers gold …`, which parses as a flat 75 gold spend. Same
  break on `offer 75 percent of her gold`.
- Correction: Do not substitute `her` when it is possessive (`her gold`,
  `her soldiers`), or resolve possessives to the agent and keep a form
  `parse_invest_order` still accepts after substitution.
- Test: percent invest/offer of `her gold` spends 75% of Mary’s purse, not
  75 gold.

### C12. IF branches must keep HAVE and failed clauses

- Severity: bug
- Status: **closed** — branch bodies prefix HAVE on elided verbs; an
  unparseable clause becomes the same warned placeholder as the top level;
  `restore_order_quotes` recurses into list fields.
  Tests: `tests/test_review_corrections_wave2.py::test_if_then_have_julia_recruits_both_stacks`,
  `::test_garbage_if_branch_clause_appears_as_a_warning`,
  `::test_quoted_say_inside_if_is_restored`.
- File: `soe/parser/control.py:212`, `:214`; `soe/parser/text.py:82`
- Defect: Branch bodies re-apply sticky HAVE only when the next clause
  starts with a verb, so `then have Julia recruit 5 soldiers and 3 workers`
  makes the leader recruit the workers. Unparseable branch clauses are
  dropped with no warning. `restore_order_quotes` does not recurse into
  `then_orders` / `else_orders`, so quoted SAY/TELL/POST inside IF keeps
  the `zqzN zqz` placeholder.
- Correction: Mirror the top-level HAVE prefix. On `order is None`, emit
  the same warned placeholder `parse_orders` uses. Recurse into list fields
  when restoring quotes.
- Test: Julia recruits both stacks; a garbage branch clause appears as a
  warning; `If … then say "Hold the gate" to Julia` delivers those words.

### C13. THEN is a barrier, not AND

- Severity: bug
- Status: **closed** — `split_clauses` treats `then` as a command boundary;
  the following order carries `then_after`; `_drain_actor` does not release
  that order in the same pass as the command before it. Attack is not a
  same-turn non-blocking action.
  Test: `tests/test_review_corrections_wave2.py::test_recruit_after_attack_then_does_not_run_the_same_turn`.
- File: `soe/parser/dispatch.py:724`, `soe/order_queue.py:409`
- Defect: MECHANICS says THEN sequences so the second command begins when
  the first completes. The parser strips a leading `then` and treats the
  clause like `and`. `_drain_actor` then releases every non-duration order
  in one pass. `Have Marcus attack Aurelia then recruit 20 soldiers` both
  run this turn, and recruit (phase 3) happens before combat (phase 5).
- Correction: Do not drain past THEN in the same pass, or insert an
  implicit wait-until-complete.
- Test: recruit after ATTACK … THEN does not run in the same turn as the
  attack (unless the attack is a same-turn non-blocking action by design —
  document that if so).

### C14. TAX is a verb, not a substring

- Severity: bug
- Status: **closed** — HAVE and implicit forms require `\btax\b` as the
  command verb; `query the taxman` and `report on taxation` fall through.
  Tests: `tests/test_review_corrections_wave2.py::test_query_the_taxman_is_not_tax`,
  `::test_have_joe_report_on_taxation_is_not_tax`,
  `::test_have_joe_tax_for_2_weeks_still_is_tax`.
- File: `soe/parser/verbs_economy.py:196`, `soe/parser/dispatch.py:423`
- Defect: HAVE match is `have\s+(.+?)\s+tax` (no word boundary); otherwise
  any clause with `'tax' in sentence` is TAX. Dispatch tries TAX long
  before REPORT/QUERY. `Query the taxman` and `Have Joe report on taxation`
  become TAX.
- Correction: Require `\btax\b` as the command verb (HAVE or leading).
- Test: those report/query sentences are not TAX; `Have Joe tax for 2 weeks`
  still is.

### C15. Duration units must be parsed

- Severity: bug
- Status: **closed** — STUDY, COLLECT and MINE use `parse_duration_days`;
  STUDY converts days to weeks (`21 days` → 3 weeks).
  Tests: `tests/test_review_corrections_wave2.py::test_study_for_21_days_is_three_weeks`,
  `::test_collect_for_2_weeks_is_14_days`.
- File: `soe/parser/verbs_magic.py:183`; `soe/parser/verbs_economy.py:230`,
  `:328`
- Defect: STUDY reads `for\s+(\d+)` as weeks, so `study combat for 21 days`
  studies 21 weeks. COLLECT/GATHER/MINE read `for\s+(\d+)` as days and
  ignore the unit, so `collect wood for 2 weeks` runs 2 days. WORK/PREACH
  already use `parse_duration_days`.
- Correction: Use `parse_duration_days` / weeks explicitly; refuse a bare
  `for N` or require a unit.
- Test: `for 21 days` on STUDY is 3 weeks (or 21 days if STUDY is daily);
  `for 2 weeks` on COLLECT is 14 days.

### C16. One STUDY, one skill — or split it

- Severity: bug
- Status: **closed** — `study A and B` expands to two STUDY orders. The
  chain test that pinned “one STUDY of two skills” now expects both skills.
  Tests: `tests/test_review_corrections_wave2.py::test_study_magic_and_sailing_covers_both_skills`,
  `tests/test_v10_and_chain.py::test_skill_lists_are_not_split`.
- File: `soe/parser/verbs_magic.py:183`, `tests/test_v10_and_chain.py:281`
- Defect: `study magic and sailing for 1 week` is one clause; the regex
  captures only the first skill. The test pins “one STUDY of two skills”
  but never checks `skill_name`. Sailing is a silent drop.
- Correction: Emit two STUDY orders, or reject `study A and B` with a
  warning.
- Test: either both skills are studied or the player is told sailing was
  not accepted.

### C17. Unknown city on BLESS/CURSE/SCRY is invalid

- Severity: bug
- Status: **closed** — a city phrase that does not resolve is a warning;
  execution skips warned BLESS/CURSE/SCRY and no longer falls back to the
  priest's hex.
  Test: `tests/test_review_corrections_wave2.py::test_unknown_city_does_not_bless_the_actors_location`.
- File: `soe/parser/verbs_magic.py:109`, `:135`, `:345`;
  `soe/phases/magic.py:255`
- Defect: An unknown city produces no warning and leaves `city_id` empty.
  Execution falls back to the priest’s hex. `Have Joe bless Atlantis`
  blesses wherever Joe is standing.
- Correction: If a city phrase is present and does not resolve, warn and
  leave the order invalid.
- Test: unknown city does not bless/curse/scry the actor’s location.

### C18. Honour documented COLLECT / TEACH forms

- Severity: bug
- Status: **closed** — COLLECT accepts an optional count (stored,
  duration still governs); implicit-leader `Teach Mike magic to level 10`
  is implemented.
  Tests: `tests/test_review_corrections_wave2.py::test_have_engineer_collect_40_wood_parses`,
  `::test_teach_mike_magic_to_level_10_parses`.
- File: `soe/parser/verbs_economy.py:230`, `soe/parser/verbs_magic.py:230`
- Defect: Docstring lists `Have Engineer collect 40 wood`; the regex
  requires `(wood|stone)` immediately after the verb. Implicit-leader
  `Teach Mike magic to level 10` is not implemented.
- Correction: Accept an optional count (honour it or warn that COLLECT is
  duration-based). Add the implicit-leader TEACH pattern every other verb
  already has.
- Test: both documented sentences parse; they no longer become
  `Could not parse`.

### C19. Reflexives on independent NPCs

- Severity: bug
- Status: **closed** — `find_agent` / `_leading_character` include
  independent NPCs, matching `resolve_character`.
  Test: `tests/test_review_corrections_wave2.py::test_independent_heal_herself_heals_that_character`.
- File: `soe/pronouns.py:139`, `soe/parser/resolve.py:51`
- Defect: `find_agent` only considers `faction_id == player_id`.
  `resolve_character` resolves independent NPCs, so before an offer is
  accepted `Have Nancy heal herself` rewrites `herself` to the player’s
  leader. Nancy heals the leader.
- Correction: Use the same NPC-inclusive lookup as `resolve_character`
  when reading the HAVE target for pronoun agent/reflexives.
- Test: `Have <independent> heal herself` heals that character.

### C20. Multi-actor HAVE

- Severity: bug
- Status: **closed** — HAVE and STOP/HALT targets that resolve as several
  characters emit one order each; `stop them` therefore addresses both.
  Tests: `tests/test_review_corrections_wave2.py::test_have_two_named_characters_both_receive_tax`,
  `::test_stop_them_stops_both`.
- File: `soe/parser/verbs_economy.py:196`, `soe/pronouns.py:462`
- Defect: `Have Alan Reed and Mary Wise tax for 4 weeks` stores actor
  `alan reed and mary wise`. Lookup fails. `them` rewrites to the same
  unresolvable list.
- Correction: Split HAVE targets on `and` and emit one order per actor
  (or resolve a real group). `stop them` must address each member.
- Test: both named characters receive TAX; `stop them` stops both.

### C21. Thousands separators in quantities

- Severity: bug
- Status: **closed** — `1,000` is collapsed to `1000` before leftover
  commas are blanked.
  Test: `tests/test_review_corrections_wave2.py::test_recruit_1000_soldiers_with_a_comma`.
- File: `soe/parser/text.py:20`
- Defect: `normalize_text` replaces every comma with a space.
  `Recruit 1,000 soldiers` becomes `recruit 1 000 soldiers` (count 1,
  unit `000`).
- Correction: Strip thousands-separator commas inside numbers
  (`1,000` → `1000`) before blanking remaining commas.
- Test: `Recruit 1,000 soldiers` recruits 1000.

### C22. `If Joe has soldiers` means any, not zero

- Severity: bug
- Status: **closed** — a countable unit with no amount is `more than 0`.
  Test: `tests/test_review_corrections_wave2.py::test_if_joe_has_soldiers_is_true_when_he_has_at_least_one`.
- File: `soe/parser/control.py:183`
- Defect: A countable unit with no amount and no `any`/`some` becomes
  `comparator=exactly, amount=0` — the opposite of the English.
- Correction: Treat a unit with no amount as `any` / more than 0, or
  refuse the condition as unrecognised.
- Test: `If Joe has soldiers then …` is true when Joe has at least one.

### C23. CLI example order filenames

- Severity: bug
- Status: **closed** — `example_setup` prints dest names
  `player_1_turn1.txt` / `player_2_turn1.txt`, which is what
  `process_turn` reads.
  Test: `tests/test_review_corrections_wave2.py::test_example_setup_copy_lines_use_the_names_process_turn_reads`.
- File: `cli.py:427`, `cli.py:259`
- Defect: `example_setup` tells the operator to copy
  `examples/orders_player1_turn1.txt` into `games/example/orders/`.
  `process_turn` only reads `{faction_id}_turn{turn}.txt`.
- Correction: Print copy lines that include the required dest name, or
  accept the example filenames as aliases.
- Test: following the printed steps produces non-empty orders for
  `player_1` turn 1.

## Wave 3 — engine / rules

### C24. Summons take casualties

- Severity: bug
- File: `soe/combat.py:89`, `:312`; `soe/phases/magic.py:224`
- Defect: Summoned creatures add `attack_value` to faction power.
  `apply_casualties` never reduces or deletes them. `expires_turn=0`
  means they contribute forever.
- Correction: Apply the same proportional count loss used for unit
  stacks, keyed by summoner presence at the city; delete empty records.
- Test: a losing fight reduces or removes the summon.

### C25. Outside observers can notice a securer

- Severity: bug
- File: `soe/fog.py:141`
- Defect: MECHANICS §10 says a securer is visible to people outside.
  `notice_chance` returns 0.0 as soon as `can_see_position(OUTSIDE,
  INSIDE)` is false, so `_is_securer` never runs. The existing test
  encodes the blocked path and never covers a securer.
- Correction: If the observer is outside and the target’s faction
  occupies the city, skip the position-matrix early return before
  applying LURK.
- Test: an outside observer can notice an inside securer (LURK still
  reduces the chance).

### C26. UNNAME / death must not orphan gold or items

- Severity: bug
- File: `soe/phases/units.py:223`, `soe/combat.py:308`
- Defect: UNNAME only checks subordinates, stacks, and ships. Deleting
  the character destroys purse gold. Items keep `holder_character_id`
  pointing at a corpse and become unreachable. Combat deaths have the
  same item hole.
- Correction: Refuse UNNAME if the target holds gold or items, or
  transfer both to the group leader. On death, leave items lootable
  (clear holder or drop at the city).
- Test: UNNAME with gold/items is refused or transfers; a dead holder’s
  items can be taken at that city.

### C27. Prisoners travel with the captor

- Severity: bug
- File: `soe/groups.py:204`, `soe/phases/prisoners.py:64`
- Defect: `move_group` excludes prisoners. Capture does not attach or
  move them. Sail/passage/teleport leave them behind. FREE / KILL /
  ENSLAVE / INTERROGATE do not require co-location.
- Correction: Move prisoners with their captor on every travel path.
  Require co-location for prisoner actions.
- Test: after the captor GO/SAIL/FLY, the prisoner is in the same city;
  remote KILL fails.

### C28. TRANSFER-all can pay its fee

- Severity: bug
- File: `soe/phases/finance.py:140`, `soe/orders.py:920`
- Defect: `gold_amount <= 0` means transfer-all. The amount is set to
  the entire purse, then the fee is added, then `debit_gold` requires
  amount+fee. Transfer-all always fails.
- Correction: When transferring all, send `max(0, available - fee)`.
  Fail only if the purse cannot cover the fee.
- Test: purse 100, fee N, transfer-all sends `100-N` and leaves 0.

### C29. Enforce borrow minimum after grace

- Severity: bug
- File: `soe/phases/economy.py:199`, MECHANICS §8
- Defect: After `BORROW_GRACE_TURNS` the bank “demands at least 10% of
  the balance per turn.” Weekly processing only accrues interest and
  decrements grace. The log line is informational.
- Correction: After grace expires, debit
  `max(10% of balance, configured floor)` from the leader purse (else
  add wage/loan default).
- Test: a loan past grace reduces the purse (or records a default) by
  at least the configured fraction.

### C30. One effective-level helper

- Severity: bug
- File: `soe/config.py:479`, `soe/fog.py` (`effective_skill_level`),
  MECHANICS §4
- Defect: Effective level is `sqrt(sum of squares of the character’s
  skills)` and “drives salary and resistance to opposed magic.” Salary
  uses only combat and magic; PROBE resistance also counts religion and
  trading.
- Correction: Share one helper (include sailing if it is a charged
  skill) and use it for both.
- Test: a high-religion subordinate’s salary matches the same formula
  PROBE uses.

### C31. ELSE must log as issued

- Severity: bug
- File: `soe/phases/conditionals.py:139`
- Defect: When the condition is false the else branch is spliced into
  the turn, but the log always says those orders were “skipped”.
- Correction: Log “issued” whenever `branch` is extended, and name
  which branch (then/else) was taken.
- Test: a false IF with ELSE records the else orders as issued.

### C32. NONCOM casualties

- Severity: bug
- File: `soe/combat.py:68`, `:293`
- Defect: Non-combatants are excluded from power and equipment.
  `apply_casualties` still wounds every living character in
  `member_ids`.
- Correction: Skip `is_noncom` characters unless they are the named
  attacker/target of this fight.
- Test: a NONCOM in a defending group is unwounded unless named.

## Wave 4 — arena / Phase 0 guarantees

These are the reasons an official run can look valid when it is not.

### C33. Stable `state_sha`

- Severity: bug
- Status: **closed** — `state_sha` hashes the same bytes `storage.save_game_state` writes (`GameStateEncoder`, sets as sorted lists). Tested under two `PYTHONHASHSEED` values.
  Tests: `tests/test_review_corrections_wave4.py::test_c33_state_sha_is_identical_under_two_pythonhashseed_values`,
  `::test_c33_state_sha_matches_saved_state_json_bytes`.
- File: `scripts/arena_bundle.py:79`
- Defect: `json.dumps(..., default=str)` on `dataclasses.asdict` emits
  `str(set)`. Set order depends on `PYTHONHASHSEED`. Resume can raise
  `BundleError` on identical engine state.
- Correction: Convert sets to sorted lists, or hash the same canonical
  `state.json` bytes `storage.save_game_state` already writes. Do not
  use `default=str` on unordered collections.
- Test: hash is identical under two `PYTHONHASHSEED` values.

### C34. Official runs must not inherit dashboard LLM knobs

- Severity: bug
- Status: **closed** — `isolate_headless_runtime` points `SOE_LLM_SETTINGS_FILE` at an empty isolated file and bridges only the dashboard key into `SOE_LLM_KEY`. `pin_official_llm_knobs` writes timeout/retries/tokens from the run config. The manifest records `_max_retries()` / `_timeout_seconds()`, not import-time constants.
  Tests: `tests/test_review_corrections_wave4.py::test_c34_official_isolation_does_not_inherit_dashboard_knobs`,
  `::test_c34_pin_official_knobs_from_run_config`.
- File: `scripts/arena.py:2082`, `webapp/llm_settings.py:115`,
  `scripts/arena.py:1946`
- Defect: Isolation claims “only the key from that file is bridged,”
  then points `SOE_LLM_SETTINGS_FILE` at `server_data/llm_settings.json`.
  Unset `SOE_LLM_*` picks up dashboard retries, timeout, base URL, and
  reasoning effort. The manifest records import-time
  `brain.MAX_RETRIES` / `TIMEOUT_SECONDS`, not the values used.
- Correction: For headless/official runs, pin every LLM knob from env
  or the run config. Stop loading the dashboard file for non-key
  fields, or record and resume-check the effective values.
- Test: changing dashboard timeout/base URL does not change an official
  run’s recorded policy unless those values are in the manifest.

### C35. Probe must require ORDERS and a parse

- Severity: bug
- Status: **closed** — `extract_marked_orders` returns `None` without the marker. The probe parses the marked block against a tiny Highfell board and succeeds only when at least one warning-free command is produced.
  Tests: `tests/test_review_corrections_wave4.py::test_c35_essay_without_orders_marker_fails_the_probe`,
  `::test_c35_marked_valid_command_passes_the_probe`.
- File: `scripts/probe_model.py:71`, `webapp/ai/context.py:448`
- Defect: Official preflight treats any non-empty reply as
  `has_marker` / `parsed_ok` because `extract_orders` returns the whole
  reply when the marker is absent. The probe never calls
  `parser.parse_orders`.
- Correction: Require the marker regex to split the reply, parse the
  extracted block, and set `success` only when at least one
  warning-free command is produced.
- Test: an essay with no `--- ORDERS ---` fails the probe; a marked
  valid command passes.

### C36. Empty 200 is a provider failure

- Severity: bug
- Status: **closed** — `_post_once` raises `LLMError` on a blank 200. Arena records a `failure_class` and does not set `raw_reply`, so `calls_completed` stays 0. The orchestrator already maps `LLMError` to `STATE_ERROR`.
  Tests: `tests/test_review_corrections_wave4.py::test_c36_empty_200_raises_llm_error`,
  `::test_c36_empty_completion_does_not_count_as_completed_call`.
- File: `webapp/ai/brain.py:327`, `webapp/ai/orchestrator.py:60`,
  `scripts/arena.py:384`
- Defect: HTTP 200 with `content is None` or `""` is treated as
  success. `run_bot_turn` marks `STATE_SUBMITTED`. Arena records
  `no_op` without `failure_class`, so empty completions inflate
  `calls_completed` and can still satisfy
  `minimum_completed_call_rate` (0.99).
- Correction: Raise `LLMError` (or a distinct empty-completion class)
  when content is blank after a 200. Count those as provider failures.
  Set `STATE_ERROR` instead of submitting a mute turn.
- Test: empty 200 does not increment `calls_completed` as success and
  does not satisfy the 0.99 rate by itself.

### C37. Determinism verify must read the full log

- Severity: bug
- Status: **closed** — `_read_jsonl(..., limit=None)` scans the whole file. Dashboard callers keep the default newest-N cap. `verify_determinism.py` uses the full scan.
  Test: `tests/test_review_corrections_wave4.py::test_c37_determinism_verify_reads_turn_1_of_a_60_turn_log`.
- File: `scripts/verify_determinism.py:41`, `webapp/service.py:597`
- Defect: `_read_jsonl(..., limit=100)` keeps only the newest records.
  Each turn writes at least `started` and `completed`, so after ~50
  turns older rows fall out. A 100-turn beta cannot verify early turns.
- Correction: Scan the full jsonl (or filter by turn while reading).
  The cap is for dashboard snippets, not a determinism guard.
- Test: turn 1 of a 60-turn room still verifies.

## Suggestions

Not blockers for a private sandbox. Do these after Waves 1–2, or with
the matching wave if you are already in the file.

| ID | File | Correction |
|---|---|---|
| S1 | `soe/phases/combat_phase.py:104` | Iterate `sorted(orders_by_player)` and `sorted(attacks_by_location)` (and other RNG phases). |
| S2 | `soe/parser/dispatch.py:779` | Dedicated failed-parse order type; stop reifying garbage as MOVE. |
| S3 | `soe/parser/dispatch.py:700` | Refuse a trailing mid-sentence IF, or document that the head always runs and THEN/ELSE do not inherit it. |
| S4 | `webapp/llm_settings.py:612`, `webapp/ai/brain.py:79` | Cap timeout (120s), retries (5), max_tokens (4096), `SOE_SUBAGENT_TOKENS`. |
| S5 | `webapp/main.py:306` | **Closed.** `/healthz` reports only `ai.configured`. `public_settings()` no longer includes `file`. |
| S6 | `webapp/main.py:830` | Accept only `X-Agent-Key` (or POST body) for mutating/state routes; deprecate `?key=`. |
| S7 | `webapp/mapimg.py:53` | Cache PNG/SVG; bound concurrent Playwright; rate-limit `/map/{name}`. |
| S8 | `webapp/ai/autoplay.py:155` | Default `wait_humans` on, or require an explicit force checkbox. |
| S9 | `scripts/arena.py:178` | Fog the scripted competence opponent and restrict it to the shared whitelist, or record the asymmetry in the gate contract. |
| S10 | `webapp/ai/autoplay.py:139`, `webapp/ai/registry.py:141` | Per-(room, faction) lock around `run_bot_turn`; init `default_registry()` under a module lock. |
| S11 | `soe/phases/combat_phase.py:81` | Collapse history-narrating comments to one-line invariants. |

## Nits

| ID | File | Correction |
|---|---|---|
| N1 | `soe/combat.py:208` | Delete unused `should_attack` / `COMBAT_MINIMUM_ATTACK_RATIO`, or make “normal” stance use it and align MECHANICS §9. |
| N2 | `soe/parser/control.py:137` | Accept `\b(?:has\|have)\b` so `if they have 1000 gold` is recognised. |
| N3 | `webapp/main.py:47` | Disable `/docs`, `/redoc`, `/openapi.json` on the beta process (or gate on loopback). |
| N4 | `webapp/service.py:473` | On rollback failure, refuse further resolve (sticky “needs operator restore”) instead of leaving split state writable. |

## Suggested sequence

1. Wave 1 (C1–C6) — closed.
2. Wave 2 (C7–C23) — closed.
3. Wave 3 (C24–C32) — combat/fog/prisoner/finance rules.
4. Wave 4 (C33–C37) — closed.
5. Suggestions and nits opportunistically.

## Counts

| Severity | Open | Closed |
|---|---|---|
| bug | 9 | 28 |
| suggestion | 11 | 0 |
| nit | 4 | 0 |

Waves 1–2 and Wave 4 are closed. Wave 3 (C24–C32) remains.
