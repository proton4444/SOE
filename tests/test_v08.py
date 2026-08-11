"""
Tests for the v0.8 cheap-gap commands and per-character gold.
"""

import json
import tempfile
from pathlib import Path

import pytest

from soe import models, engine, orders, parser, storage, config
from soe.combat import calculate_faction_power


@pytest.fixture
def two_faction_state():
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
    gs.factions["p1"] = models.Faction(id="p1", name="Empire", controlled_city_ids={"city1"})
    gs.factions["p2"] = models.Faction(id="p2", name="Horde", controlled_city_ids={"city2"})
    gs.characters["c1"] = models.Character(
        id="c1", name="Marcus", faction_id="p1", location_city_id="city1",
        combat_skill=15, is_leader=True, gold=500,
    )
    gs.characters["c2"] = models.Character(
        id="c2", name="Tengri", faction_id="p2", location_city_id="city2",
        combat_skill=10, is_leader=True, gold=200,
    )
    gs.characters["c1b"] = models.Character(
        id="c1b", name="Julia", faction_id="p1", location_city_id="city1",
        combat_skill=40, gold=50,
    )
    return gs


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def test_hire_is_recruit_synonym(two_faction_state):
    gs = two_faction_state
    parsed = parser.parse_orders("Hire 5 soldiers.", gs, "p1")
    assert len(parsed) == 1
    assert isinstance(parsed[0], orders.RecruitOrder)
    assert parsed[0].count == 5
    assert parsed[0].unit_type == "soldier"


def test_noncom_excludes_skill_from_combat(two_faction_state):
    gs = two_faction_state
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=20,
    )
    with_julia = calculate_faction_power("p1", "city1", gs)
    gs.characters["c1b"].is_noncom = True
    without_julia = calculate_faction_power("p1", "city1", gs)
    assert with_julia > without_julia


def test_noncom_and_lurk_orders(two_faction_state):
    gs = two_faction_state
    noncom = orders.NoncomOrder(
        player_id="p1", character_ids=["c1b"], character_names=["Julia"], set_noncom=True
    )
    lurk = orders.LurkOrder(player_id="p1", actor_id="c1", set_lurking=True)
    engine.run_turn(gs, {"p1": [noncom, lurk]}, seed=1)
    assert gs.characters["c1b"].is_noncom is True
    assert gs.characters["c1"].is_lurking is True

    combatant = orders.NoncomOrder(
        player_id="p1", character_ids=["c1b"], character_names=["Julia"], set_noncom=False
    )
    unlurk = orders.LurkOrder(player_id="p1", actor_id="c1", set_lurking=False)
    engine.run_turn(gs, {"p1": [combatant, unlurk]}, seed=2)
    assert gs.characters["c1b"].is_noncom is False
    assert gs.characters["c1"].is_lurking is False


# ---------------------------------------------------------------------------
# Prisoners
# ---------------------------------------------------------------------------

def test_kill_prisoner(two_faction_state):
    gs = two_faction_state
    gs.characters["c2"].location_city_id = "city1"
    gs.characters["c2"].is_prisoner = True
    gs.characters["c2"].captor_id = "c1"

    order = orders.KillOrder(player_id="p1", actor_id="c1",
                             prisoner_ids=["c2"], prisoner_names=["Tengri"])
    engine.run_turn(gs, {"p1": [order]}, seed=1)
    assert gs.characters["c2"].is_dead is True
    assert gs.characters["c2"].is_prisoner is False


def test_enslave_prisoner(two_faction_state):
    gs = two_faction_state
    gs.characters["c2"].location_city_id = "city1"
    gs.characters["c2"].is_prisoner = True
    gs.characters["c2"].captor_id = "c1"
    gs.characters["c2"].gold = 30

    order = orders.EnslaveOrder(player_id="p1", actor_id="c1",
                                prisoner_ids=["c2"], prisoner_names=["Tengri"])
    engine.run_turn(gs, {"p1": [order]}, seed=1)

    assert "c2" not in gs.characters
    slaves = [s for s in gs.unit_stacks.values() if s.unit_type == models.UnitType.SLAVE]
    assert len(slaves) == 1 and slaves[0].count == 1


def test_interrogate_reveals_or_fails(two_faction_state):
    gs = two_faction_state
    gs.characters["c2"].location_city_id = "city1"
    gs.characters["c2"].is_prisoner = True
    gs.characters["c2"].captor_id = "c1"
    gs.characters["c1"].combat_skill = 80
    gs.characters["c2"].combat_skill = 1

    order = orders.InterrogateOrder(
        player_id="p1", actor_id="c1", prisoner_ids=["c2"], prisoner_names=["Tengri"]
    )
    _, log = engine.run_turn(gs, {"p1": [order]}, seed=7)
    events = [e.event_type for e in log.get_player_events("p1")
              if e.event_type.startswith("interrogate")]
    assert events  # success, fail, or killed


# ---------------------------------------------------------------------------
# Inventory / finance
# ---------------------------------------------------------------------------

def test_get_takes_gold_from_ally(two_faction_state):
    gs = two_faction_state
    # Solo character so upkeep does not cloud the assertion
    del gs.characters["c1b"]
    gs.factions["p1"].controlled_city_ids = set()
    gs.characters["c1"].gold = 100
    gs.characters["c_helper"] = models.Character(
        id="c_helper", name="Helper", faction_id="p1", location_city_id="city1",
        is_leader=False, gold=80, combat_skill=0, magic_skill=0,
    )
    # Helper is salaried — zero skills still pays base salary; make them leader-exempt
    # by using process_get path: give helper is_leader False and skill 0 is still paid.
    # Avoid salary noise by marking helper as leader too (only first leader counts for pay)
    # Actually only one non-leader pays. Set gold transfer then check donor.
    order = orders.GetOrder(player_id="p1", actor_id="c1", donor_id="c_helper", gold_amount=30)
    engine.run_turn(gs, {"p1": [order]}, seed=1)
    assert gs.characters["c_helper"].gold == 50
    # Recipient gained 30 before any upkeep; after base salary for helper, still +30 net of salary
    assert gs.characters["c1"].gold == pytest.approx(100 + 30 - config.calculate_character_salary(0, 0), abs=0.1)


def test_get_cannot_take_from_enemy(two_faction_state):
    gs = two_faction_state
    gs.characters["c2"].location_city_id = "city1"
    gs.characters["c2"].gold = 100
    order = orders.GetOrder(player_id="p1", actor_id="c1", donor_id="c2", gold_amount=10)
    _, log = engine.run_turn(gs, {"p1": [order]}, seed=1)
    assert any(e.event_type == "get_failed" for e in log.get_player_events("p1"))
    assert gs.characters["c2"].gold == 100


def test_transfer_charges_fee(two_faction_state):
    gs = two_faction_state
    del gs.characters["c1b"]
    gs.factions["p1"].controlled_city_ids = set()
    gs.characters["c1"].gold = 200
    gs.characters["c2"].gold = 0
    order = orders.TransferOrder(
        player_id="p1", actor_id="c1", recipient_id="c2", gold_amount=100
    )
    engine.run_turn(gs, {"p1": [order]}, seed=1)
    fee = config.transfer_fee(100)
    assert gs.characters["c2"].gold == 100
    assert gs.characters["c1"].gold == pytest.approx(200 - 100 - fee, abs=0.1)


def test_pay_reduces_wage_debt(two_faction_state):
    gs = two_faction_state
    gs.factions["p1"].wage_debt = 40
    gs.characters["c1"].gold = 100
    order = orders.PayOrder(player_id="p1", actor_id="c1", gold_amount=25)
    engine.run_turn(gs, {"p1": [order]}, seed=1)
    # Upkeep may also run this turn; debt should still drop by the payment first
    # then possibly rise from unpaid wages. Check gold moved and debt < 40+upkeep.
    assert gs.characters["c1"].gold < 100
    assert gs.factions["p1"].wage_debt < 40 or gs.factions["p1"].wage_debt == pytest.approx(15, abs=5)


def test_borrow_and_repay(two_faction_state):
    gs = two_faction_state
    gs.characters["c1"].gold = 0
    # High skill + medium city + seed should often succeed; force via many seeds
    succeeded = False
    for seed in range(50):
        gs2 = models.GameState()
        gs2.world_map = gs.world_map
        gs2.factions = {
            "p1": models.Faction(id="p1", name="Empire", controlled_city_ids={"city1"}),
        }
        gs2.characters["c1"] = models.Character(
            id="c1", name="Marcus", faction_id="p1", location_city_id="city1",
            combat_skill=50, magic_skill=50, trading_skill=50, is_leader=True, gold=0,
        )
        engine.run_turn(gs2, {"p1": [orders.BorrowOrder(
            player_id="p1", actor_id="c1", gold_amount=100)]}, seed=seed)
        if gs2.factions["p1"].loan_balance >= 100:
            succeeded = True
            assert gs2.characters["c1"].gold >= 100
            repay = orders.RepayOrder(player_id="p1", actor_id="c1", gold_amount=50)
            # Credit enough for repay after interest/upkeep noise
            gs2.characters["c1"].gold = 200
            engine.run_turn(gs2, {"p1": [repay]}, seed=seed + 1)
            assert gs2.factions["p1"].loan_balance < 100
            break
    assert succeeded, "BORROW never succeeded across seeds — check odds"


def test_legacy_treasury_migrates_to_leader_gold():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "state.json").write_text(json.dumps({
            "turn_number": 1,
            "world_map": {"cities": {}, "roads": {}},
            "factions": {"p1": {"id": "p1", "name": "Empire", "treasury": 400}},
            "characters": {
                "ch1": {"id": "ch1", "name": "Marcus", "faction_id": "p1",
                        "location_city_id": "c1", "is_leader": True},
            },
        }), encoding="utf-8")
        restored = storage.load_game_state(Path(tmp))

    assert restored.characters["ch1"].gold == 400
    assert restored.factions["p1"].treasury == 0


def test_parse_v08_verbs(two_faction_state):
    gs = two_faction_state
    gs.characters["c2"].location_city_id = "city1"
    gs.characters["c2"].is_prisoner = True
    gs.characters["c2"].captor_id = "c1"

    text = (
        "Noncom Julia. Lurk. Take 20 gold from Julia. "
        "Transfer 50 gold to Tengri. Pay 10. Borrow 25. "
        "Execute Tengri."
    )
    # Tengri is prisoner — kill may parse; transfer to prisoner ok
    parsed = parser.parse_orders(text, gs, "p1")
    types = {o.order_type() for o in parsed if not o.warnings or o.order_type() != "MOVE"}
    assert "NONCOM" in types
    assert "LURK" in types
    assert "GET" in types
    assert "TRANSFER" in types
    assert "PAY" in types
    assert "BORROW" in types
    assert "KILL" in types
