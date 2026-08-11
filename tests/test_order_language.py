"""
Regressions for the order language exposed by the eight-turn territory playtest.

Every failure protected here was found by a player writing something reasonable
and getting something else. The rule they share: a command the parser accepts
must mean what it looks like it means, and a command it cannot honour must say
so rather than quietly becoming a different command.

Nothing here tests territory *balance*. The occupation rules, the SECURE force
requirement and the economy are exactly as they were; what changed is whether a
player can find out what they are.
"""

from __future__ import annotations

import pytest

from soe import engine, models, parser, reporting, territory
from soe.models import LocationPosition, PopulationBand, UnitType
from soe.orders import AttackOrder, MoveOrder
from soe.parser.control import parse_if_condition


# ============================================================================
# THE PLAYTEST BOARD
# ============================================================================

@pytest.fixture
def board() -> models.GameState:
    """
    Alpha is sovereign in Redport; Beta sits one good road away in Ashford.

    Beta's Borin leads an army large enough that an attack is never declined
    for poor odds, so these tests measure the order language rather than dice.
    """
    gs = models.GameState()
    gs.turn_number = 1
    gs.world_map.cities["ashford"] = models.City(
        id="ashford", name="Ashford", population_band=PopulationBand.MEDIUM)
    gs.world_map.cities["redport"] = models.City(
        id="redport", name="Redport", population_band=PopulationBand.MEDIUM)
    gs.world_map.roads["road"] = models.Road(
        id="road", from_city_id="ashford", to_city_id="redport",
        quality=models.RoadQuality.EXCELLENT)

    gs.factions["alpha"] = models.Faction(
        id="alpha", name="Alpha", controlled_city_ids={"redport"})
    gs.factions["beta"] = models.Faction(
        id="beta", name="Beta", controlled_city_ids={"ashford"})

    gs.characters["aurelia"] = models.Character(
        id="aurelia", name="Aurelia", title="Regent", faction_id="alpha",
        location_city_id="redport", is_leader=True, combat_skill=10, gold=500)
    gs.characters["borin"] = models.Character(
        id="borin", name="Borin", faction_id="beta",
        location_city_id="ashford", is_leader=True, movement_points=100,
        combat_skill=30, gold=5_000)
    gs.characters["vesna"] = models.Character(
        id="vesna", name="Vesna", faction_id="beta",
        location_city_id="ashford", group_leader_id="borin",
        movement_points=100, gold=100)

    gs.unit_stacks["alpha_garrison"] = models.UnitStack(
        id="alpha_garrison", faction_id="alpha", location_city_id="redport",
        unit_type=UnitType.SOLDIER, count=20, owner_character_id="aurelia")
    gs.unit_stacks["beta_army"] = models.UnitStack(
        id="beta_army", faction_id="beta", location_city_id="ashford",
        unit_type=UnitType.SOLDIER, count=600, owner_character_id="borin")
    return gs


def parse(gs: models.GameState, text: str, player_id: str = "beta") -> list:
    return parser.parse_orders(text, gs, player_id)


def one(gs: models.GameState, text: str, player_id: str = "beta"):
    """The single order a one-command submission produces."""
    orders = parse(gs, text, player_id)
    assert len(orders) == 1, orders
    return orders[0]


def run(gs: models.GameState, submissions: dict[str, str], seed: int = 7):
    parsed = {pid: parser.parse_orders(text, gs, pid)
              for pid, text in submissions.items()}
    return engine.run_turn(gs, parsed, seed=seed)


def descriptions(log, player_id: str, event_type: str | None = None) -> list[str]:
    return [e.description for e in log.get_player_events(player_id)
            if event_type is None or e.event_type == event_type]


# ============================================================================
# 1 -- ATTACK TARGET PARSING
# ============================================================================

def test_attack_binds_a_plain_name(board):
    order = one(board, "Attack Aurelia.")
    assert not order.warnings
    assert order.target_character_id == "aurelia"
    assert order.target_faction_id == "alpha"


def test_attack_ignores_a_title_on_the_target(board):
    """Design: titles are ignored except in the NAME and PROMOTE commands."""
    order = one(board, "Attack Regent Aurelia.")
    assert not order.warnings
    assert order.target_character_id == "aurelia"


def test_attack_target_name_is_reported_as_the_real_name(board):
    """The report must name the person, not the player's spelling of them."""
    assert one(board, "Attack Regent Aurelia.").target_name == "Aurelia"


@pytest.mark.parametrize("text", [
    "Attack Regent Aurelia in Redport.",
    "Attack Aurelia in Redport.",
    "Attack Aurelia at Redport.",
])
def test_attack_rejects_a_location_qualifier_instead_of_swallowing_it(board, text):
    """
    ATTACK takes a name and nothing else, so a location must be refused loudly.

    The playtest wrote `ATTACK Regent Aurelia in Redport`, the parser accepted
    it, hunted for a character of that entire name, found none, and the attack
    never happened without a word said.
    """
    order = one(board, text)
    assert order.warnings, "an unsupported location must not parse silently"
    warning = order.warnings[0]
    assert "go to redport and attack" in warning, warning
    # Crucially: it did not bind some other target on the way past.
    assert not order.target_character_id


def test_attack_keeps_a_name_that_really_contains_in(board):
    """A location is only blamed once the whole phrase has failed as a name."""
    board.characters["odd"] = models.Character(
        id="odd", name="Ivar in Chains", faction_id="alpha",
        location_city_id="redport")
    order = one(board, "Attack Ivar in Chains.")
    assert not order.warnings
    assert order.target_character_id == "odd"


def test_attack_on_an_unknown_name_says_so(board):
    order = one(board, "Attack Nobody At All.")
    assert order.warnings
    assert "nobody at all" in order.warnings[0]


def test_attack_after_go_binds_the_named_target(board):
    """The supported way to attack elsewhere: GO in the same sentence."""
    orders = parse(board, "Have Borin go to Redport and attack Aurelia.")
    attacks = [o for o in orders if isinstance(o, AttackOrder)]
    moves = [o for o in orders if isinstance(o, MoveOrder)]
    assert len(attacks) == 1 and len(moves) == 1
    assert not attacks[0].warnings
    assert attacks[0].target_character_id == "aurelia"
    assert moves[0].destination_city_id == "redport"


# ============================================================================
# 1b -- ATTACK TARGET PRESENCE
#
# the design, ATTACK: "If Bram Kell is not present, then no attack will take
# place." The engine used to read an absent target as "defender_power == 0",
# which is not the same question: unowned stacks bypass the group filter and
# the defender's allies are added on top, so an ATTACK aimed at a character
# who had left was quietly fought against whoever remained -- and reported as
# a victory over the person who was never there.
# ============================================================================

def _borin_stands_in_redport(board) -> None:
    """Put the attacker in the target's city so only presence is under test."""
    board.characters["borin"].location_city_id = "redport"
    board.unit_stacks["beta_army"].location_city_id = "redport"


def _aurelia_is_elsewhere(board) -> None:
    """Move the named target, and her own troops, out of the attacked city."""
    board.characters["aurelia"].location_city_id = "ashford"
    board.unit_stacks["alpha_garrison"].location_city_id = "ashford"


def battles(log) -> list:
    return [e for e in log.events
            if e.phase == "combat" and e.event_type in ("victory", "defeat")]


def test_absent_target_is_not_replaced_by_loose_faction_soldiers(board):
    """
    THE BUG: Aurelia was in Ashford and still lost a battle in Redport.

    Unowned stacks count for a faction whoever is asked about, so the soldiers
    she had left behind stood in for her and took 123 casualties.
    """
    _borin_stands_in_redport(board)
    _aurelia_is_elsewhere(board)
    board.unit_stacks["alpha_loose"] = models.UnitStack(
        id="alpha_loose", faction_id="alpha", location_city_id="redport",
        unit_type=UnitType.SOLDIER, count=200)

    gs, log = run(board, {"beta": "Have Borin definitely attack Aurelia."})

    assert not battles(log), descriptions(log, "beta")
    assert gs.unit_stacks["alpha_loose"].count == 200, "substitute troops bled"
    assert gs.unit_stacks["beta_army"].count == 600, "attacker bled"
    failures = descriptions(log, "beta", "attack_failed")
    assert failures and "Aurelia is not present" in failures[0]


def test_absent_target_is_not_replaced_by_another_character(board):
    """A second character of the same faction is not a substitute target."""
    _borin_stands_in_redport(board)
    _aurelia_is_elsewhere(board)
    board.characters["cassian"] = models.Character(
        id="cassian", name="Cassian", faction_id="alpha",
        location_city_id="redport", combat_skill=5)
    board.unit_stacks["cassian_men"] = models.UnitStack(
        id="cassian_men", faction_id="alpha", location_city_id="redport",
        unit_type=UnitType.SOLDIER, count=200, owner_character_id="cassian")

    gs, log = run(board, {"beta": "Have Borin definitely attack Aurelia."})

    assert not battles(log), descriptions(log, "beta")
    assert gs.unit_stacks["cassian_men"].count == 200
    # Scouting may well report Cassian standing there; the attack must simply
    # not be aimed at him.
    failures = descriptions(log, "beta", "attack_failed")
    assert failures and "Aurelia is not present" in failures[0]
    assert "Cassian" not in failures[0]


def test_absent_target_is_not_replaced_by_her_allies(board):
    """
    An ally defends the target, not the ground.

    Allied strength was added after the group filter, so it alone could carry
    a battle the named defender was not present for.
    """
    _borin_stands_in_redport(board)
    _aurelia_is_elsewhere(board)
    board.factions["gamma"] = models.Faction(id="gamma", name="Gamma")
    board.factions["alpha"].allies.add("gamma")
    board.factions["gamma"].allies.add("alpha")
    board.unit_stacks["gamma_men"] = models.UnitStack(
        id="gamma_men", faction_id="gamma", location_city_id="redport",
        unit_type=UnitType.SOLDIER, count=200)

    gs, log = run(board, {"beta": "Have Borin definitely attack Aurelia."})

    assert not battles(log), descriptions(log, "beta")
    assert gs.unit_stacks["gamma_men"].count == 200


def test_hidden_movement_evades_a_targeted_attack(board):
    """
    Both orders are written blind; movement resolves first, so she gets away.

    This is the gameplay point of the rule: an ATTACK aimed at a name can be
    dodged by leaving, and what stays behind is not conscripted into the fight.
    """
    _borin_stands_in_redport(board)
    board.characters["aurelia"].movement_points = 100
    board.unit_stacks["alpha_loose"] = models.UnitStack(
        id="alpha_loose", faction_id="alpha", location_city_id="redport",
        unit_type=UnitType.SOLDIER, count=200)

    gs, log = run(board, {
        "alpha": "Have Aurelia go to Ashford.",
        "beta": "Have Borin definitely attack Aurelia.",
    })

    assert gs.characters["aurelia"].location_city_id == "ashford"
    assert not battles(log), descriptions(log, "beta")
    assert gs.unit_stacks["alpha_loose"].count == 200


def test_absent_target_failure_does_not_name_where_she_went(board):
    """The attacker learns not-here, which marching in would have told them."""
    _borin_stands_in_redport(board)
    _aurelia_is_elsewhere(board)

    gs, log = run(board, {"beta": "Have Borin definitely attack Aurelia."})

    failures = descriptions(log, "beta", "attack_failed")
    assert failures, descriptions(log, "beta")
    assert "Ashford" not in failures[0], failures[0]
    assert "no attack takes place" in failures[0]


def test_present_target_still_fights_a_normal_battle(board):
    """CONTROL -- the fix must not narrow an attack that finds its target."""
    _borin_stands_in_redport(board)

    gs, log = run(board, {"beta": "Have Borin definitely attack Aurelia."})

    fought = battles(log)
    assert fought, descriptions(log, "beta")
    assert all(e.location_city_id == "redport" for e in fought)
    assert gs.unit_stacks["alpha_garrison"].count < 20, "defender took no losses"


def test_present_target_still_draws_her_allies_into_the_battle(board):
    """
    CONTROL -- alliance behaviour is unchanged when the target really is here.

    Design: personnel useful in the attack "will automatically come to his
    aid", and a defender's allies present at the battle share the casualties.
    """
    _borin_stands_in_redport(board)
    board.factions["gamma"] = models.Faction(id="gamma", name="Gamma")
    board.factions["alpha"].allies.add("gamma")
    board.factions["gamma"].allies.add("alpha")
    board.unit_stacks["gamma_men"] = models.UnitStack(
        id="gamma_men", faction_id="gamma", location_city_id="redport",
        unit_type=UnitType.SOLDIER, count=200)

    assert engine.defending_side("alpha", "beta", "redport", board) == ["alpha", "gamma"]

    gs, log = run(board, {"beta": "Have Borin definitely attack Aurelia."})

    assert battles(log), descriptions(log, "beta")
    assert gs.unit_stacks["gamma_men"].count < 200, "ally took no casualties"


def test_move_then_attack_still_reads_the_arrival_city_for_presence(board):
    """
    Presence is judged where the attacker ends up, not where the order parsed.

    Borin parses this in Ashford, where Aurelia is not; the march succeeds and
    the battle must be fought against her in Redport.
    """
    gs, log = run(board, {
        "beta": "Have Borin go to Redport. Have Borin definitely attack Aurelia.",
    })

    assert gs.characters["borin"].location_city_id == "redport"
    fought = battles(log)
    assert fought, descriptions(log, "beta")
    assert all(e.location_city_id == "redport" for e in fought)


def test_failed_move_checks_presence_at_the_city_actually_reached(board):
    """The mirror: a march that failed judges presence back home in Ashford."""
    board.characters["borin"].movement_points = 0

    gs, log = run(board, {
        "beta": "Have Borin go to Redport. Have Borin definitely attack Aurelia.",
    })

    assert gs.characters["borin"].location_city_id == "ashford"
    assert not battles(log), descriptions(log, "beta")
    failures = descriptions(log, "beta", "attack_failed")
    assert failures and "Aurelia is not present in Ashford" in failures[0]


def test_faction_attack_without_a_name_is_not_gated_on_presence(board):
    """
    An ATTACK that names nobody has no absentee -- it must still resolve.

    the design points a nameless ATTACK at whoever secures the location, so the
    presence gate applies only when the player actually named a character.
    """
    _borin_stands_in_redport(board)
    order = AttackOrder(player_id="beta", actor_id="borin",
                        location_city_id="redport", target_faction_id="alpha",
                        target_name="Alpha", definitely=True)
    gs, log = engine.run_turn(board, {"beta": [order]}, seed=7)

    assert battles(log), descriptions(log, "beta")


# ============================================================================
# 2 -- EXECUTION-TIME LOCATION
# ============================================================================

def test_move_then_attack_fights_where_the_attacker_arrived(board):
    """
    MOVE runs two phases before combat, so ATTACK must read the new location.

    Freezing the parse-time city sent the battle to the town the attacker had
    just left, where it found nobody.
    """
    gs, log = run(board, {
        "beta": "Have Borin go to Redport. Have Borin definitely attack Aurelia.",
    })
    assert gs.characters["borin"].location_city_id == "redport"
    battles = [e for e in log.events
               if e.phase == "combat" and e.event_type in ("victory", "defeat")]
    assert battles, descriptions(log, "beta")
    assert all(e.location_city_id == "redport" for e in battles)


def test_failed_move_leaves_the_attack_where_the_attacker_really_is(board):
    """
    A march that never happened must not be pretended into the attack.

    No rollback and no chaining: the ATTACK still runs, from Ashford, and
    fails there for the honest reason that the target is somewhere else.
    """
    board.characters["borin"].movement_points = 0
    gs, log = run(board, {
        "beta": "Have Borin go to Redport. Have Borin definitely attack Aurelia.",
    })
    assert gs.characters["borin"].location_city_id == "ashford"
    failures = descriptions(log, "beta", "attack_failed")
    assert failures, descriptions(log, "beta")
    assert "Aurelia is not present in Ashford" in failures[0]


def test_move_then_recruit_uses_the_new_location(board):
    """The same parse-time freeze made a chained RECRUIT fail after a good move."""
    board.factions["beta"].controlled_city_ids.add("redport")
    board.factions["alpha"].controlled_city_ids.clear()
    gs, log = run(board, {
        "beta": "Have Borin go to Redport and recruit 5 soldiers.",
    })
    assert gs.characters["borin"].location_city_id == "redport"
    recruited = [s for s in gs.unit_stacks.values()
                 if s.location_city_id == "redport" and s.faction_id == "beta"]
    assert recruited, descriptions(log, "beta")


def test_recruit_in_a_named_city_is_still_taken_at_its_word(board):
    """Naming the city keeps the old meaning: be there, or fail saying so."""
    _, log = run(board, {"beta": "Have Borin recruit 5 soldiers in Redport."})
    failures = descriptions(log, "beta", "recruit_failed")
    assert failures and "is not in Redport" in failures[0]


# ============================================================================
# 3 -- UNIT WORD NORMALIZATION
# ============================================================================

# Every noun an IF condition may count, singular and plural, against the key
# `conditionals._count_condition_units` switches on. The plural-only spelling
# list used to make every singular count zero and take the wrong branch.
UNIT_WORD_PAIRS = [
    ("soldier", "soldiers", "soldier"),
    ("sailor", "sailors", "sailor"),
    ("worker", "workers", "worker"),
    ("slave", "slaves", "slave"),
    ("horse", "horses", "horse"),
    ("catapult", "catapults", "catapult"),
    ("weapon", "weapons", "weapon"),
    ("galley", "galleys", "galley"),
    ("ship", "ships", "galley"),
    ("skeleton", "skeletons", "skeleton"),
    ("zombie", "zombies", "zombie"),
    ("harpy", "harpies", "harpy"),
    ("minotaur", "minotaurs", "minotaur"),
    ("griffin", "griffins", "griffin"),
    ("chimera", "chimeras", "chimera"),
    ("dragon", "dragons", "dragon"),
    ("demon", "demons", "demon"),
    ("gem", "gems", "gems"),
    ("stone", "stones", "stone"),
]

SINGLE_FORM_UNITS = [
    ("gold", "gold"), ("wood", "wood"), ("iron", "iron"),
    ("copper", "copper"), ("silver", "silver"), ("armor", "armor"),
    ("encumbrance", "encumbrance"), ("power", "power"),
]


@pytest.mark.parametrize("singular,plural,key", UNIT_WORD_PAIRS)
def test_singular_and_plural_unit_words_mean_the_same_thing(board, singular,
                                                            plural, key):
    for spelling in (singular, plural):
        condition = parse_if_condition(
            f"borin has more than 3 {spelling}", board, "beta")
        assert condition is not None, spelling
        assert condition["unit"] == key, (spelling, condition)


@pytest.mark.parametrize("word,key", SINGLE_FORM_UNITS)
def test_units_with_one_spelling_still_resolve(board, word, key):
    condition = parse_if_condition(f"borin has more than 3 {word}", board, "beta")
    assert condition is not None and condition["unit"] == key


def test_singular_soldier_condition_takes_the_branch_the_count_deserves(board):
    """
    The playtest's own failure: `soldier` counted nothing and chose wrong.

    Borin leads 600, so a "more than 100 soldier" test must hold.
    """
    gs, log = run(board, {
        "beta": "If Borin has more than 100 soldier then have Borin tax.",
    })
    branches = descriptions(log, "beta", "if_branch")
    assert branches and "held" in branches[0], branches


@pytest.mark.parametrize("unit", ["soldier", "sailor", "worker", "slave"])
@pytest.mark.parametrize("plural", [False, True])
def test_recruit_accepts_either_spelling_of_every_unit_it_raises(board, unit,
                                                                 plural):
    """RECRUIT's own noun handling, checked against the same word list."""
    word = f"{unit}s" if plural else unit
    order = one(board, f"Have Borin recruit 3 {word}.")
    assert not order.warnings, order.warnings
    assert order.unit_type == unit
    assert order.count == 3


@pytest.mark.parametrize("word", ["galley", "galleys"])
def test_buy_accepts_either_spelling_of_a_ship(board, word):
    order = one(board, f"Have Borin buy 2 {word}.")
    assert not order.warnings, order.warnings
    assert order.ship_type == "galley"


def test_a_condition_naming_nothing_countable_is_refused_not_guessed(board):
    """It used to evaluate against zero and quietly take the else branch."""
    order = one(board, "If Borin has more than 3 flumphs then have Borin tax.")
    assert order.warnings and "condition" in order.warnings[0].lower()


# ============================================================================
# 4 -- MESSAGE BOUNDARIES
# ============================================================================

def test_message_then_report_parse_independently(board):
    """The documented separator is the period; both orders must survive it."""
    orders = parse(board, 'Have Borin say "Ready" to Aurelia. Have Borin report.')
    assert [type(o).__name__ for o in orders] == ["MessageOrder", "ReportOrder"]
    assert not any(o.warnings for o in orders)


def test_message_then_tax_parse_independently(board):
    orders = parse(board, 'Have Borin say "Ready" to Aurelia. Have Borin tax.')
    assert [type(o).__name__ for o in orders] == ["MessageOrder", "TaxOrder"]
    assert not any(o.warnings for o in orders)


def test_a_message_does_not_silently_eat_the_next_order(board):
    """
    Without the period the next command lands inside the recipient name.

    the design recovers by ignoring input to the next period, so REPORT is not
    obeyed -- but the player is told exactly which words went missing instead
    of being handed "no character called 'aurelia report'".
    """
    orders = parse(board, 'Have Borin say "Ready" to Aurelia Report.')
    assert len(orders) == 1
    warning = orders[0].warnings[0]
    assert "report" in warning and "period" in warning


def test_tell_still_flags_text_running_past_the_message(board):
    orders = parse(board, 'Have Borin tell Aurelia "Ready" report.')
    assert len(orders) == 1
    assert "period" in orders[0].warnings[0]


def test_a_quoted_message_may_contain_a_command_word(board):
    """Only the recipient is inspected; the message body is untouched."""
    order = one(board, 'Have Borin say "Report to me at dawn." to Aurelia.')
    assert not order.warnings
    assert order.message == "Report to me at dawn."
    assert order.recipient_ids == ["aurelia"]


# ============================================================================
# 5 -- TAX LANGUAGE
# ============================================================================

def test_plain_tax_is_local_and_says_nothing_about_a_city(board):
    order = one(board, "Have Borin tax for 2 weeks.")
    assert not order.warnings and not order.stated_city_id
    assert order.duration_days == 14


def test_tax_naming_a_city_is_recorded_not_discarded(board):
    order = one(board, "Have Borin tax Redport.")
    assert order.stated_city_id == "redport"


def test_tax_naming_a_city_the_actor_is_not_in_refuses(board):
    """
    The playtest wrote a city and was taxed somewhere else entirely.

    Design: TAX "will attempt to collect taxes in his current location", so
    the named city is a claim to check, never a target to travel to.
    """
    gs, log = run(board, {"beta": "Have Borin tax Redport."})
    failures = descriptions(log, "beta", "tax_failed")
    assert failures, descriptions(log, "beta")
    assert "Borin is in Ashford, not Redport" in failures[0]
    assert not any(e.event_type == "tax_success" for e in log.events)


def test_tax_naming_the_city_the_actor_reached_is_honoured(board):
    """Order, warning and report all name one place -- and it collects."""
    board.tax_pools["redport"] = 400
    board.factions["beta"].controlled_city_ids.add("redport")
    board.factions["alpha"].controlled_city_ids.clear()
    gs, log = run(board, {
        "beta": "Have Borin go to Redport. Have Borin tax Redport.",
    })
    collected = descriptions(log, "beta", "tax_success")
    assert collected and "Redport" in collected[0], descriptions(log, "beta")


# ============================================================================
# 6 -- TERRITORIAL AUTHORITY PRESENTATION
# ============================================================================

def _occupy_redport_with_beta(gs: models.GameState) -> None:
    """Beta's army stands inside Redport and holds it."""
    gs.characters["borin"].location_city_id = "redport"
    gs.characters["borin"].location_position = LocationPosition.INSIDE
    gs.unit_stacks["beta_army"].location_city_id = "redport"
    gs.factions["beta"].secured_city_ids.add("redport")


def test_authority_names_the_three_claims_apart(board):
    _occupy_redport_with_beta(board)
    held = territory.authority_ids(board, "redport")
    assert held == {"sovereign": "alpha", "occupier": "beta",
                    "administrator": "beta"}


def test_sovereign_report_shows_a_foreign_occupier_of_their_own_city(board):
    _occupy_redport_with_beta(board)
    report = reporting.generate_player_reports(
        board, engine.TurnLog(), {})["alpha"]
    assert "TERRITORIAL AUTHORITY" in report
    assert "Sovereign: Alpha (you)" in report
    assert "Occupier: Beta" in report
    assert "Administrator: Beta" in report
    assert "may not tax, recruit, fortify, post or secure here" in report


def test_authority_report_after_the_occupation_lapses(board):
    """When the garrison leaves, the sovereign gets their own city back."""
    _occupy_redport_with_beta(board)
    board.characters["borin"].location_city_id = "ashford"
    board.unit_stacks["beta_army"].location_city_id = "ashford"
    territory.reconcile_occupations(board)

    held = territory.authority_ids(board, "redport")
    assert held == {"sovereign": "alpha", "occupier": None,
                    "administrator": "alpha"}

    report = reporting.generate_player_reports(
        board, engine.TurnLog(), {})["alpha"]
    assert "Occupier: none" in report
    assert "Administrator: Alpha (you)" in report


def test_a_player_is_not_told_who_holds_a_city_they_cannot_see(board):
    """Ashford is Beta's and Alpha has nobody there: no leak either way."""
    assert territory.authority_names(board, "ashford", "alpha") is None
    report = reporting.generate_player_reports(
        board, engine.TurnLog(), {})["alpha"]
    assert "Ashford" not in report.split("THE LIE OF THE LAND")[0]


def test_standing_in_a_city_earns_the_right_to_read_its_authority(board):
    """Beta marches in and may now see that Alpha is sovereign there."""
    assert territory.authority_names(board, "redport", "beta") is None
    board.characters["borin"].location_city_id = "redport"
    held = territory.authority_names(board, "redport", "beta")
    assert held == {"sovereign": "Alpha", "occupier": "none",
                    "administrator": "Alpha"}


# ============================================================================
# 7 -- ORDER FAILURE MESSAGES
# ============================================================================

def test_tax_failure_explains_a_foreign_occupation(board):
    _occupy_redport_with_beta(board)
    board.characters["aurelia"].location_city_id = "redport"
    board.tax_pools["redport"] = 400
    gs, log = run(board, {"alpha": "Have Aurelia tax."})
    failures = descriptions(log, "alpha", "tax_failed")
    assert failures and "suspends your sovereign rights" in failures[0]


def test_recruit_failure_names_the_administrator(board):
    gs, log = run(board, {"beta": "Have Borin go to Redport and recruit 5 soldiers."})
    failures = descriptions(log, "beta", "recruit_failed")
    assert failures and "Alpha is its sovereign and administers it" in failures[0]


def test_secure_failure_distinguishes_outside_the_walls_from_no_soldiers(board):
    board.characters["borin"].location_position = LocationPosition.OUTSIDE
    gs, log = run(board, {"beta": "Have Borin secure."})
    failures = descriptions(log, "beta", "secure_failed")
    assert failures and "requires being inside the walls" in failures[0]


def test_secure_failure_names_a_missing_garrison(board):
    board.unit_stacks["beta_army"].count = 0
    gs, log = run(board, {"beta": "Have Borin secure."})
    failures = descriptions(log, "beta", "secure_failed")
    assert failures and "no ordinary soldiers" in failures[0]


def test_fortify_failure_names_the_administrator(board):
    gs, log = run(board, {"beta": "Have Borin go to Redport and fortify."})
    failures = descriptions(log, "beta", "fortify_failed")
    assert failures and "Alpha is its sovereign" in failures[0]


def test_attack_failure_does_not_leak_where_a_missing_target_went(board):
    """Not-here is all the attacker learns -- the design grants that much."""
    board.characters["aurelia"].location_city_id = "ashford"
    board.unit_stacks["alpha_garrison"].location_city_id = "ashford"
    board.characters["borin"].location_city_id = "redport"
    gs, log = run(board, {"beta": "Have Borin definitely attack Aurelia."})
    failures = descriptions(log, "beta", "attack_failed")
    assert failures and "Aurelia is not present in Redport" in failures[0]
    assert "Ashford" not in failures[0]


# ============================================================================
# 8 -- SUPPORT CLARITY
# ============================================================================

def test_support_result_explains_that_it_does_not_merge_groups(board):
    """
    CORRECT BUT CONFUSING -- the wording changed, the mechanics did not.

    Design: the HAVE form makes the named character a group leader, and a
    supporter fights "if and when he attacks someone else" as a separate group.
    Both surprised the playtester, so the result now says so.
    """
    gs, log = run(board, {"beta": "Have Vesna support Borin."})
    assert gs.characters["vesna"].supporting_id == "borin"
    told = descriptions(log, "beta", "support")
    assert told, descriptions(log, "beta")
    assert "does not merge the groups" in told[0]
    assert "does not help Borin defend" in told[0]


def test_support_leaving_the_group_is_reported_as_it_happens(board):
    """The detach is the design's HAVE rule, and the player is told about it."""
    gs, log = run(board, {"beta": "Have Vesna support Borin."})
    assert not gs.characters["vesna"].group_leader_id
    assert any("left Borin's group" in d
               for d in descriptions(log, "beta", "became_leader"))


# ============================================================================
# PLAYTEST REPRODUCTION
# ============================================================================

def test_the_campaign_turn_that_failed_now_works_end_to_end(board):
    """
    Beta marches on Redport and attacks, secures, then taxes -- in one turn.

    This is the disposable campaign's critical interaction, which the parser
    used to break at the first step and then hide behind the rest. It proves
    the attack found the person the player named, that combat really resolved,
    that SECURE saw the state combat left behind, and that TAX collected in
    the town the order says.
    """
    board.tax_pools["redport"] = 500
    gs, log = run(board, {
        "beta": (
            "Have Borin go to Redport. "
            "Have Borin definitely attack Regent Aurelia. "
            "Have Borin secure. "
            "Have Borin tax Redport."
        ),
    })

    beta_orders = parser.parse_orders("Have Borin definitely attack Regent Aurelia.",
                                      board, "beta")
    assert not beta_orders[0].warnings
    assert beta_orders[0].target_character_id == "aurelia"

    assert gs.characters["borin"].location_city_id == "redport"

    battles = [e for e in log.events
               if e.phase == "combat" and e.event_type in ("victory", "defeat")]
    assert battles, descriptions(log, "beta")
    assert battles[0].location_city_id == "redport"

    assert "redport" in gs.factions["beta"].secured_city_ids
    assert territory.authority_ids(gs, "redport") == {
        "sovereign": "alpha", "occupier": "beta", "administrator": "beta"}

    collected = descriptions(log, "beta", "tax_success")
    assert collected and "Redport" in collected[0], descriptions(log, "beta")

    # Alpha, still sovereign and still standing there, can read what happened.
    report = reporting.generate_player_reports(gs, log, {})["alpha"]
    assert "Sovereign: Alpha (you)" in report
    assert "Occupier: Beta" in report
