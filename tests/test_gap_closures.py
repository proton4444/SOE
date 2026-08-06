"""
Tests for the known gaps closed in v0.7.2.

These were listed as accepted limitations in docs/audit_2025-11.md rather than
defects: overlapping fortification stores, flat casualty rates, an implicit
faction leader, inert diplomacy and silently-ignored queue orders. They are
closed now, and these tests keep them closed.
"""

import json
import tempfile
from pathlib import Path

import pytest

from spoils_engine import models, engine, orders, parser, storage, config
from spoils_engine.combat import calculate_faction_power, casualty_rates


@pytest.fixture
def two_faction_state():
    """A minimal two-faction world: two port cities joined by road and sea."""
    gs = models.GameState()

    gs.world_map.cities["city1"] = models.City(
        id="city1", name="Rome", population_band=models.PopulationBand.MEDIUM, is_port=True
    )
    gs.world_map.cities["city2"] = models.City(
        id="city2", name="Carthage", population_band=models.PopulationBand.SMALL, is_port=True
    )
    gs.world_map.roads["road1"] = models.Road(
        id="road1", from_city_id="city1", to_city_id="city2", quality=models.RoadQuality.GOOD
    )

    gs.factions["p1"] = models.Faction(id="p1", name="Empire", treasury=1000,
                                       controlled_city_ids={"city1"})
    gs.factions["p2"] = models.Faction(id="p2", name="Horde", treasury=1000,
                                       controlled_city_ids={"city2"})

    gs.characters["c1"] = models.Character(id="c1", name="Marcus", faction_id="p1",
                                           location_city_id="city1", combat_skill=15,
                                           is_leader=True)
    gs.characters["c2"] = models.Character(id="c2", name="Tengri", faction_id="p2",
                                           location_city_id="city2", combat_skill=10,
                                           is_leader=True)
    return gs


# ============================================================================
# ONE FORTIFICATION STORE
# ============================================================================

def test_fortifications_have_a_single_store(two_faction_state):
    """
    Fortification level lived in three places at once -- City.fortification_level,
    Faction.fortifications and GameState.city_fortifications -- and combat read
    only the last, so a level set through one path was invisible to the others.
    """
    assert not hasattr(two_faction_state, "city_fortifications")
    assert not hasattr(two_faction_state.factions["p1"], "fortifications")

    gs = two_faction_state
    gs.characters["c1"].resources["stone"] = 100
    fortify = orders.FortifyOrder(player_id="p1", actor_id="c1", city_id="city1", percent=25)

    engine.run_turn(gs, {"p1": [fortify]}, seed=1)

    assert gs.world_map.cities["city1"].fortification_level == 25


def test_fortifications_reach_combat(two_faction_state):
    """The single store must be the one combat reads."""
    gs = two_faction_state
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=100)

    plain = calculate_faction_power("p1", "city1", gs)
    gs.world_map.cities["city1"].fortification_level = 50
    fortified = calculate_faction_power("p1", "city1", gs)

    assert fortified > plain


def test_legacy_fortification_stores_are_migrated():
    """A save from before the consolidation must not lose its defenses."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "state.json").write_text(json.dumps({
            "turn_number": 3,
            "world_map": {"cities": {
                "c1": {"id": "c1", "name": "Rome", "population_band": "1M+"},
                "c2": {"id": "c2", "name": "Carthage", "population_band": "1M+"},
            }, "roads": {}},
            "factions": {"p1": {"id": "p1", "name": "Empire",
                                "fortifications": {"c2": 40}}},
            "characters": {},
            "city_fortifications": {"c1": 60},
        }), encoding="utf-8")

        restored = storage.load_game_state(Path(tmp))

    assert restored.world_map.cities["c1"].fortification_level == 60
    assert restored.world_map.cities["c2"].fortification_level == 40


# ============================================================================
# CASUALTIES SCALE WITH THE MARGIN
# ============================================================================

def test_casualties_scale_with_the_margin_of_victory():
    """
    Casualty rates were flat -- 10% winner / 30% loser -- so a 10:1 rout cost
    the winner exactly what a coin-flip battle did.
    """
    even_winner, even_loser = casualty_rates(100.0, 100.0)
    rout_winner, rout_loser = casualty_rates(1000.0, 100.0)

    # Parity still matches the configured baselines
    assert even_winner == pytest.approx(config.COMBAT_CASUALTY_RATE_WINNER)
    assert even_loser == pytest.approx(config.COMBAT_CASUALTY_RATE_LOSER)

    assert rout_winner < even_winner
    assert rout_loser > even_loser
    assert rout_winner >= config.COMBAT_CASUALTY_MIN_WINNER
    assert rout_loser <= config.COMBAT_CASUALTY_MAX_LOSER


def test_narrow_win_is_still_costly():
    """An upset victory must not be cheap merely because it was a victory."""
    narrow_winner, _ = casualty_rates(101.0, 100.0)
    assert narrow_winner == pytest.approx(config.COMBAT_CASUALTY_RATE_WINNER, rel=0.05)


def test_margin_is_capped():
    """Overwhelming force stops mattering past the cap rather than diverging."""
    capped, capped_loser = casualty_rates(1e6, 1.0)
    assert capped >= config.COMBAT_CASUALTY_MIN_WINNER
    assert capped_loser <= config.COMBAT_CASUALTY_MAX_LOSER


# ============================================================================
# EXPLICIT LEADER
# ============================================================================

def test_leader_is_explicit_not_iteration_order(two_faction_state):
    """
    The leader -- who draws no salary and receives orders naming no actor -- was
    whichever character iterated first, so adding a character could silently
    move the exemption to someone else.
    """
    gs = two_faction_state
    gs.characters["c1"].is_leader = False
    gs.characters["c0"] = models.Character(
        id="c0", name="Julia", faction_id="p1", location_city_id="city1",
        combat_skill=50, is_leader=True)

    assert parser.get_player_leader(gs, "p1").id == "c0"

    treasury_before = gs.factions["p1"].treasury
    engine.run_turn(gs, {"p1": []}, seed=1)
    paid = treasury_before - gs.factions["p1"].treasury

    # Marcus is salaried; Julia is exempt despite having been added second
    assert paid == pytest.approx(config.calculate_character_salary(15, 0), rel=1e-6)


def test_legacy_save_gets_a_leader():
    """Saves written before the flag existed keep the leader they had."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "state.json").write_text(json.dumps({
            "turn_number": 1,
            "world_map": {"cities": {}, "roads": {}},
            "factions": {"p1": {"id": "p1", "name": "Empire"}},
            "characters": {
                "ch1": {"id": "ch1", "name": "Marcus", "faction_id": "p1",
                        "location_city_id": "c1"},
                "ch2": {"id": "ch2", "name": "Julia", "faction_id": "p1",
                        "location_city_id": "c1"},
            },
        }), encoding="utf-8")

        restored = storage.load_game_state(Path(tmp))

    assert restored.characters["ch1"].is_leader
    assert not restored.characters["ch2"].is_leader


# ============================================================================
# DIPLOMACY AFFECTS COMBAT
# ============================================================================

def test_allies_cannot_be_attacked(two_faction_state):
    """Diplomatic stance was recorded but had no effect on combat."""
    gs = two_faction_state
    gs.factions["p1"].allies.add("p2")

    attack = orders.AttackOrder(player_id="p1", actor_id="c1", location_city_id="city1",
                                target_faction_id="p2", target_name="Horde")
    engine.run_turn(gs, {"p1": [attack]}, seed=1)

    assert any("ally" in w for w in attack.warnings)


def test_allies_join_the_defense(two_faction_state):
    """A defender's allies present at the battle fight and share the losses."""
    gs = two_faction_state
    gs.factions["p3"] = models.Faction(id="p3", name="League", treasury=100)
    gs.factions["p2"].allies.add("p3")

    # Attacker and both defenders meet at Carthage
    gs.characters["c1"].location_city_id = "city2"
    gs.unit_stacks["attackers"] = models.UnitStack(
        id="attackers", faction_id="p1", location_city_id="city2",
        unit_type=models.UnitType.SOLDIER, count=60)
    gs.unit_stacks["defenders"] = models.UnitStack(
        id="defenders", faction_id="p2", location_city_id="city2",
        unit_type=models.UnitType.SOLDIER, count=30)
    gs.unit_stacks["allied"] = models.UnitStack(
        id="allied", faction_id="p3", location_city_id="city2",
        unit_type=models.UnitType.SOLDIER, count=30)

    assert engine.defending_side("p2", "p1", "city2", gs) == ["p2", "p3"]

    attack = orders.AttackOrder(player_id="p1", actor_id="c1", location_city_id="city2",
                                target_faction_id="p2", target_name="Horde")
    engine.run_turn(gs, {"p1": [attack]}, seed=7)

    assert gs.unit_stacks["allied"].count < 30, "ally took no casualties"


def test_ally_with_no_forces_present_stays_home(two_faction_state):
    """An ally with nothing at the location is not dragged into the battle."""
    gs = two_faction_state
    gs.factions["p3"] = models.Faction(id="p3", name="League", treasury=100)
    gs.factions["p2"].allies.add("p3")

    assert engine.defending_side("p2", "p1", "city2", gs) == ["p2"]


def test_ally_of_both_sides_stays_out(two_faction_state):
    """A faction allied to both combatants must not end up fighting itself."""
    gs = two_faction_state
    gs.factions["p3"] = models.Faction(id="p3", name="League", treasury=100)
    gs.factions["p2"].allies.add("p3")
    gs.factions["p3"].allies.update({"p1", "p2"})
    gs.unit_stacks["allied"] = models.UnitStack(
        id="allied", faction_id="p3", location_city_id="city2",
        unit_type=models.UnitType.SOLDIER, count=30)

    assert engine.defending_side("p2", "p1", "city2", gs) == ["p2"]


# ============================================================================
# QUEUE ORDERS ARE HONEST
# ============================================================================

def test_queued_orders_are_executed_not_just_logged(two_faction_state):
    """
    AWAIT and REPEAT used to log a success no cross-turn queue ever delivered,
    so v0.7.2 made them warn instead. v0.9 built the queue, and the standard is
    now the original one: a wait must actually hold the character's orders back.
    """
    gs = two_faction_state
    await_order = orders.AwaitOrder(player_id="p1", actor_id="c1", duration_days=7)
    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")

    _, log = engine.run_turn(gs, {"p1": [await_order, move]}, seed=1)

    assert not await_order.warnings
    assert [e for e in log.get_player_events("p1") if e.phase == "queue"]
    # The move is behind the wait, so the character has not gone anywhere.
    assert gs.characters["c1"].location_city_id == "city1"
