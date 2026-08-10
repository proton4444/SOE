"""
Establishing occupation needs a city nobody else is still holding by force.

The playtest that prompted these tests found SECURE deciding by turn order
what the map said should be decided by fighting: one Beta soldier, walked in
beside a hundred and seventy-five Alpha ones, could write SECURE and take over
the administration of Alpha's own city. Force size changed nothing, and the
only defence was to have written SECURE first -- a latch no rules text
announced.

The rule these tests protect is small and deliberately unquantified:

    a faction may *establish* occupation only where no other faction still has
    a qualifying garrison inside.

No ratios, no thresholds, no contested flag. Twenty-five does not beat
twenty-four, because that is combat's job. Two armed factions simply leave the
city unoccupied until one of them stops being there.

*Holding* an occupation is a separate question and is not touched here: an
existing occupation lapses only when its own garrison stops qualifying, which
``test_territory_occupation`` covers.
"""

from __future__ import annotations

import pytest

from spoils_engine import engine, models, orders, parser, territory
from spoils_engine.models import LocationPosition, PopulationBand, UnitType


# ============================================================================
# THE BOARD
# ============================================================================

@pytest.fixture
def board() -> models.GameState:
    """
    Alpha is sovereign in Kitesta and garrisons it; Beta waits in Riverton.

    Beta's Borin leads an army large enough that an attack is never declined
    for poor odds, so what these tests measure is the establishment rule and
    not the dice.
    """
    gs = models.GameState()
    gs.turn_number = 1
    gs.world_map.cities["riverton"] = models.City(
        id="riverton", name="Riverton", population_band=PopulationBand.MEDIUM)
    gs.world_map.cities["kitesta"] = models.City(
        id="kitesta", name="Kitesta", population_band=PopulationBand.MEDIUM)
    gs.world_map.roads["road"] = models.Road(
        id="road", from_city_id="riverton", to_city_id="kitesta",
        quality=models.RoadQuality.EXCELLENT)

    gs.factions["alpha"] = models.Faction(
        id="alpha", name="Alpha", controlled_city_ids={"kitesta"},
        treasury=10_000)
    gs.factions["beta"] = models.Faction(
        id="beta", name="Beta", controlled_city_ids={"riverton"},
        treasury=10_000)

    gs.characters["aurelia"] = models.Character(
        id="aurelia", name="Aurelia", title="Regent", faction_id="alpha",
        location_city_id="kitesta", is_leader=True, combat_skill=10, gold=500)
    gs.characters["borin"] = models.Character(
        id="borin", name="Borin", faction_id="beta",
        location_city_id="riverton", is_leader=True, movement_points=100,
        combat_skill=30, gold=5_000)

    gs.unit_stacks["alpha_garrison"] = models.UnitStack(
        id="alpha_garrison", faction_id="alpha", location_city_id="kitesta",
        unit_type=UnitType.SOLDIER, count=175, owner_character_id="aurelia")
    gs.unit_stacks["beta_army"] = models.UnitStack(
        id="beta_army", faction_id="beta", location_city_id="riverton",
        unit_type=UnitType.SOLDIER, count=600, owner_character_id="borin")
    return gs


def _beta_walks_in(gs: models.GameState, soldiers: int) -> None:
    """Borin and his soldiers stand inside Kitesta, beside whoever is there."""
    gs.characters["borin"].location_city_id = "kitesta"
    gs.characters["borin"].location_position = LocationPosition.INSIDE
    gs.unit_stacks["beta_army"].location_city_id = "kitesta"
    gs.unit_stacks["beta_army"].count = soldiers


def _add_second_alpha_group(gs: models.GameState, soldiers: int = 30) -> None:
    """A second Alpha character with a garrison of his own, inside Kitesta."""
    gs.characters["doran"] = models.Character(
        id="doran", name="Doran", faction_id="alpha",
        location_city_id="kitesta", combat_skill=10)
    gs.unit_stacks["doran_guard"] = models.UnitStack(
        id="doran_guard", faction_id="alpha", location_city_id="kitesta",
        unit_type=UnitType.SOLDIER, count=soldiers, owner_character_id="doran")


def _secure(player_id: str = "beta", actor_id: str = "borin"):
    return orders.SecureOrder(
        player_id=player_id, actor_id=actor_id, city_id="kitesta")


def _run(gs: models.GameState, submissions: dict[str, list], seed: int = 7):
    return engine.run_turn(gs, submissions, seed=seed)


def _run_text(gs: models.GameState, submissions: dict[str, str], seed: int = 7):
    """Through the real parser, the way a player's submission arrives."""
    parsed = {pid: parser.parse_orders(text, gs, pid)
              for pid, text in submissions.items()}
    return engine.run_turn(gs, parsed, seed=seed)


def _secure_failures(log, player_id: str) -> list[str]:
    return [event.description for event in log.get_player_events(player_id)
            if event.event_type == "secure_failed"]


# ============================================================================
# 1 -- FORCE SIZE IS NOT THE QUESTION
# ============================================================================

@pytest.mark.parametrize("beta_soldiers", [1, 5, 25, 50])
def test_no_number_of_beta_soldiers_secures_past_an_armed_alpha(
        board, beta_soldiers):
    """
    The reported defect, at every size the replay tried.

    One soldier could not take Kitesta from 175 because one soldier is few; it
    could not take it because Alpha is still standing inside it under arms.
    """
    _beta_walks_in(board, beta_soldiers)
    gs, log = _run(board, {"beta": [_secure()]})
    assert gs.factions["beta"].secured_city_ids == set()
    assert territory.occupying_faction_id(gs, "kitesta") is None
    assert _secure_failures(log, "beta")


def test_overwhelming_beta_force_still_cannot_secure_past_one_alpha_soldier(
        board):
    """
    And the rule does not quietly become a ratio at the other end.

    175 against 1 is a battle Beta would win easily -- but it must actually
    fight it. SECURE is administration, not a substitute for combat.
    """
    _beta_walks_in(board, 175)
    board.unit_stacks["alpha_garrison"].count = 1
    gs, _ = _run(board, {"beta": [_secure()]})
    assert gs.factions["beta"].secured_city_ids == set()


def test_failure_names_the_physical_obstacle_without_counting_the_enemy(board):
    """
    A player told only "you may not" marches back and tries again next turn.

    The message says what is in the way -- an armed garrison -- and stops
    there: not whose, not how many, not who leads it.
    """
    _beta_walks_in(board, 1)
    _, log = _run(board, {"beta": [_secure()]})
    failures = _secure_failures(log, "beta")
    assert failures, "Beta should be told why SECURE failed"
    message = failures[0]
    assert "Borin" in message and "Kitesta" in message
    assert "another faction still maintains an armed garrison inside" in message
    assert "175" not in message
    assert "Aurelia" not in message


# ============================================================================
# 2 -- WHAT COUNTS AS SOMEONE ELSE BEING THERE
# ============================================================================

def test_alpha_soldiers_without_a_qualifying_character_do_not_block(board):
    """Leaderless soldiers are not a garrison under the existing predicate."""
    _beta_walks_in(board, 1)
    board.characters["aurelia"].location_position = LocationPosition.OUTSIDE
    gs, _ = _run(board, {"beta": [_secure()]})
    assert gs.factions["beta"].secured_city_ids == {"kitesta"}


def test_alpha_character_without_ordinary_soldiers_does_not_block(board):
    """
    A regent alone in her own city cannot keep an army out administratively.

    Same asymmetry the maintenance rule already has: presence is soldiers plus
    somebody to command them, and elite units have never counted.
    """
    _beta_walks_in(board, 1)
    del board.unit_stacks["alpha_garrison"]
    board.elite_units["guard"] = models.EliteUnit(
        id="guard", name="Household Guard", faction_id="alpha",
        leader_character_id="aurelia", location_city_id="kitesta", size=200)
    gs, _ = _run(board, {"beta": [_secure()]})
    assert gs.factions["beta"].secured_city_ids == {"kitesta"}


def test_blocking_is_measured_per_faction_not_per_character(board):
    """
    Removing the character Beta happened to think of is not enough.

    Alpha keeps two independent groups inside. Aurelia goes, Doran stays, and
    Alpha is still there -- so establishment is still barred.
    """
    _beta_walks_in(board, 600)
    _add_second_alpha_group(board)
    board.characters["aurelia"].is_dead = True
    gs, _ = _run(board, {"beta": [_secure()]})
    assert gs.factions["beta"].secured_city_ids == set()

    gs.characters["doran"].is_dead = True
    gs, _ = _run(gs, {"beta": [_secure()]})
    assert gs.factions["beta"].secured_city_ids == {"kitesta"}


def test_a_qualifying_allied_garrison_blocks_as_firmly_as_an_enemy_one(board):
    """
    Occupation is exclusive, so an ally's soldiers are still someone else's.

    Nothing here consults diplomacy, and nothing here invents a way to consent
    to shared administration; Beta simply may not establish occupation over an
    allied garrison's head.
    """
    _beta_walks_in(board, 600)
    del board.unit_stacks["alpha_garrison"]
    board.characters["aurelia"].location_position = LocationPosition.OUTSIDE
    board.factions["gamma"] = models.Faction(
        id="gamma", name="Gamma", treasury=1_000, allies={"beta"})
    board.factions["beta"].allies.add("gamma")
    board.characters["kell"] = models.Character(
        id="kell", name="Kell", faction_id="gamma",
        location_city_id="kitesta")
    board.unit_stacks["gamma_column"] = models.UnitStack(
        id="gamma_column", faction_id="gamma", location_city_id="kitesta",
        unit_type=UnitType.SOLDIER, count=20, owner_character_id="kell")

    gs, log = _run(board, {"beta": [_secure()]})
    assert gs.factions["beta"].secured_city_ids == set()
    assert _secure_failures(log, "beta")


def test_sovereignty_needs_no_special_case_to_defend_itself(board):
    """
    Alpha never SECUREd its own city and does not have to.

    The first-mover latch is gone because sovereignty is not what is being
    checked: Alpha's garrison blocks establishment the same way any other
    faction's would.
    """
    _beta_walks_in(board, 50)
    assert board.factions["alpha"].secured_city_ids == set()
    gs, _ = _run(board, {"beta": [_secure()]})
    assert gs.factions["beta"].secured_city_ids == set()
    assert territory.administrative_faction_id(gs, "kitesta") == "alpha"


# ============================================================================
# 3 -- TWO CLAIMANTS, NO WINNER
# ============================================================================

@pytest.mark.parametrize("first", ["alpha", "beta"])
def test_mutual_secure_leaves_the_city_to_nobody_in_either_order(board, first):
    """
    Both fail, and which faction the engine happens to reach first is not a
    tie-break because there is no tie to break. Iterating the factions the
    other way round must read the same.
    """
    _beta_walks_in(board, 600)
    submissions = {
        "alpha": [_secure(player_id="alpha", actor_id="aurelia")],
        "beta": [_secure()],
    }
    if first == "beta":
        submissions = dict(reversed(list(submissions.items())))
        board.factions = dict(reversed(list(board.factions.items())))

    gs, log = _run(board, submissions)
    assert gs.factions["alpha"].secured_city_ids == set()
    assert gs.factions["beta"].secured_city_ids == set()
    assert territory.occupying_faction_id(gs, "kitesta") is None
    assert _secure_failures(log, "alpha") and _secure_failures(log, "beta")


def test_repeating_a_barred_secure_costs_nothing_and_changes_nothing(board):
    """
    No cooldown was added, and none is needed: the order simply keeps failing
    while the obstacle stands, and works the turn after it is gone.
    """
    _beta_walks_in(board, 600)
    gs = board
    for _ in range(3):
        gs, _ = _run(gs, {"beta": [_secure()]})
        assert gs.factions["beta"].secured_city_ids == set()

    gs.characters["aurelia"].location_position = LocationPosition.OUTSIDE
    gs, _ = _run(gs, {"beta": [_secure()]})
    assert gs.factions["beta"].secured_city_ids == {"kitesta"}


# ============================================================================
# 4 -- CLEARING THE GROUND THE ORDINARY WAY
# ============================================================================

def test_capturing_the_last_alpha_character_opens_the_way_in_one_batch(board):
    """CAPTURE is a normal way to stop a garrison qualifying, and it counts."""
    _beta_walks_in(board, 600)
    program = [
        orders.CaptureOrder(
            player_id="beta", actor_id="borin", target_ids=["aurelia"],
            target_names=["Aurelia"]),
        _secure(),
    ]
    gs, _ = _run(board, {"beta": program})
    assert gs.characters["aurelia"].is_prisoner
    assert gs.factions["beta"].secured_city_ids == {"kitesta"}


# ============================================================================
# 5 -- THROUGH THE PARSER, AS A PLAYER WRITES IT
# ============================================================================

def test_invasion_that_clears_the_city_may_then_secure_and_tax(board):
    """
    The whole submission, parsed from text: march, fight, take over, collect.

    SECURE is still a separate order -- winning the battle does not occupy the
    city by itself -- but a player may commit to it in advance and gamble that
    the fighting clears the way. That gamble is meant to be available.
    """
    board.tax_pools["kitesta"] = 400
    gs, log = _run_text(board, {
        "beta": (
            "Have Borin go to Kitesta. "
            "Have Borin definitely attack Regent Aurelia. "
            "Have Borin secure. "
            "Have Borin tax Kitesta."
        ),
    })
    assert not territory.has_competing_qualifying_garrison(gs, "kitesta", "beta")
    assert gs.factions["beta"].secured_city_ids == {"kitesta"}
    assert territory.authority_ids(gs, "kitesta") == {
        "sovereign": "alpha", "occupier": "beta", "administrator": "beta"}
    assert any(event.event_type == "tax_success"
               for event in log.get_player_events("beta"))


def test_invasion_that_leaves_a_second_defender_standing_cannot_secure(board):
    """
    The same submission against a city that was not fully cleared.

    Borin beats Aurelia and holds the field, but Doran's group is still inside
    under arms, so the gamble does not pay and Alpha keeps the administration.
    """
    _add_second_alpha_group(board)
    gs, log = _run_text(board, {
        "beta": (
            "Have Borin go to Kitesta. "
            "Have Borin definitely attack Regent Aurelia. "
            "Have Borin secure."
        ),
    })
    # Beta is otherwise entitled: the one thing stopping it is Doran.
    assert territory.has_qualifying_garrison(gs, gs.characters["borin"], "kitesta")
    assert territory.has_competing_qualifying_garrison(gs, "kitesta", "beta")
    assert gs.factions["beta"].secured_city_ids == set()
    assert territory.administrative_faction_id(gs, "kitesta") == "alpha"
    assert "armed garrison inside" in " ".join(_secure_failures(log, "beta"))


def test_walking_in_beside_the_garrison_and_writing_secure_does_nothing(board):
    """
    The replayed gotcha, start to finish and with no combat ordered.

    One Beta soldier walks into Alpha's sovereign city, which holds 175 of
    Alpha's own and a character to command them, and writes SECURE. Alpha has
    never SECUREd anything. Beta gets nothing.
    """
    board.unit_stacks["beta_army"].count = 1
    gs, log = _run_text(board, {
        "beta": "Have Borin go to Kitesta. Have Borin secure.",
    })
    assert gs.characters["borin"].location_city_id == "kitesta"
    assert territory.has_qualifying_garrison(gs, gs.characters["borin"], "kitesta")
    assert gs.factions["beta"].secured_city_ids == set()
    assert territory.administrative_faction_id(gs, "kitesta") == "alpha"
    assert _secure_failures(log, "beta")


# ============================================================================
# 6 -- HOLDING IS STILL A SEPARATE QUESTION
# ============================================================================

def test_an_existing_occupation_survives_a_rival_marching_in(board):
    """
    Establishment tightened; maintenance did not move.

    Beta holds Kitesta. Alpha arrives in force and stands inside it. That is
    not enough to end Beta's occupation -- Alpha must break Beta's garrison --
    and Beta re-writing SECURE must not talk the engine out of an occupation
    it already validly holds.
    """
    _beta_walks_in(board, 600)
    board.factions["beta"].secured_city_ids.add("kitesta")
    assert territory.is_valid_occupation(board, "beta", "kitesta")

    gs, _ = _run(board, {"beta": [_secure()]})
    assert gs.factions["beta"].secured_city_ids == {"kitesta"}
    assert territory.occupying_faction_id(gs, "kitesta") == "beta"

    # And Alpha, present and armed, still may not take it administratively.
    gs, _ = _run(gs, {"alpha": [_secure(player_id="alpha", actor_id="aurelia")]})
    assert gs.factions["alpha"].secured_city_ids == set()
    assert gs.factions["beta"].secured_city_ids == {"kitesta"}


def test_an_existing_occupation_still_lapses_when_its_own_garrison_goes(board):
    """
    The other half of the same point: reconciliation is untouched.

    A rival being present neither ends the occupation nor props it up. Beta's
    own garrison stops qualifying, so the occupation lapses exactly as before,
    and authority falls back to Alpha's sovereignty.
    """
    _beta_walks_in(board, 600)
    board.factions["beta"].secured_city_ids.add("kitesta")
    board.characters["borin"].location_position = LocationPosition.OUTSIDE

    removed = territory.reconcile_occupations(board)
    assert ("beta", "kitesta") in removed
    assert board.factions["beta"].secured_city_ids == set()
    assert territory.administrative_faction_id(board, "kitesta") == "alpha"


def test_a_persisted_occupation_loads_beside_a_rival_without_being_erased(
        board):
    """
    Old saves keep working: no field was added, and nothing is re-derived.

    A save where Beta occupies Kitesta while Alpha also has a garrison inside
    is a state the new rule would not let a player *create*, but it is a legal
    state to be in, and loading it must not quietly dispossess Beta.
    """
    _beta_walks_in(board, 600)
    board.factions["beta"].secured_city_ids.add("kitesta")
    assert territory.has_competing_qualifying_garrison(board, "kitesta", "beta")

    territory.reconcile_occupations(board)
    assert board.factions["beta"].secured_city_ids == {"kitesta"}
    assert territory.occupying_faction_id(board, "kitesta") == "beta"
