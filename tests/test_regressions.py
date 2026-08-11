"""
Regression tests for defects found in the v0.7.0 engine audit.

Each test here pins down a specific bug that was fixed. They are grouped by the
area of the engine they cover rather than by test style.
"""

import copy
import json
import random
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest

from soe import models, engine, orders, parser, storage, config


# ============================================================================
# FIXTURES
# ============================================================================

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
                                           location_city_id="city1", combat_skill=15)
    gs.characters["c2"] = models.Character(id="c2", name="Tengri", faction_id="p2",
                                           location_city_id="city2", combat_skill=10)
    return gs


# ============================================================================
# PERSISTENCE
# ============================================================================

def test_save_load_preserves_every_field():
    """
    The decoder used to rebuild models field-by-field and silently dropped
    prisoners, diplomacy, religion, resources, summons, fortifications and tax
    pools. Every turn is a save/load cycle, so those all reset each turn.
    """
    gs = models.GameState(turn_number=4)
    gs.world_map.cities["c1"] = models.City(
        id="c1", name="Rome", population_band=models.PopulationBand.LARGE,
        terrain={"plains", "river"}, region="Latium", is_port=True,
        fortification_level=30, resource_richness={"iron": 2.0},
    )
    gs.world_map.roads["r1"] = models.Road(id="r1", from_city_id="c1", to_city_id="c1",
                                           quality=models.RoadQuality.SEA)
    gs.factions["p1"] = models.Faction(
        id="p1", name="Empire", controlled_city_ids={"c1"}, secured_city_ids={"c1"},
        treasury=750, allies={"p2"}, enemies={"p3"},
    )
    gs.characters["ch1"] = models.Character(
        id="ch1", name="Marcus", faction_id="p1", location_city_id="c1",
        is_leader=True, gender="female", title="primate", is_prisoner=True,
        captor_id="ch2", religion_skill=40, religious_power_current=12,
        trading_skill=7, health=55, resources={"wood": 12, "armor": 3},
    )
    gs.unit_stacks["u1"] = models.UnitStack(id="u1", faction_id="p1", location_city_id="c1",
                                            unit_type=models.UnitType.SAILOR, count=30)
    gs.ships["s1"] = models.Ship(id="s1", faction_id="p1", location_city_id="c1",
                                 ship_type=models.ShipType.GALLEY)
    gs.summoned_creatures["sc1"] = models.SummonedCreature(
        id="sc1", summoner_id="ch1", creature_type=models.CreatureType.DRAGON,
        count=2, expires_turn=9,
    )
    gs.tax_pools["c1"] = 133.5
    gs.location_blessings["c1"] = 20
    gs.location_curses["c1"] = 5

    with tempfile.TemporaryDirectory() as tmp:
        storage.save_game_state(gs, Path(tmp))
        restored = storage.load_game_state(Path(tmp))

    assert asdict(restored) == asdict(gs)


def test_load_tolerates_missing_and_unknown_fields():
    """Old saves stay loadable as models gain fields; junk keys are ignored."""
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "state.json"
        state_file.write_text(json.dumps({
            "turn_number": 2,
            "world_map": {"cities": {"c1": {
                "id": "c1", "name": "Rome", "population_band": "1M+",
                "some_future_field": 123,
            }}, "roads": {}},
            "factions": {},
            "characters": {},
        }), encoding="utf-8")

        restored = storage.load_game_state(Path(tmp))

    assert restored.turn_number == 2
    assert restored.world_map.cities["c1"].name == "Rome"
    assert restored.world_map.cities["c1"].fortification_level == 0  # default applied


def test_save_is_atomic(two_faction_state):
    """An interrupted save must not truncate the previous state file."""
    with tempfile.TemporaryDirectory() as tmp:
        game_dir = Path(tmp)
        storage.save_game_state(two_faction_state, game_dir)
        good = (game_dir / "state.json").read_text(encoding="utf-8")

        broken = copy.deepcopy(two_faction_state)
        broken.factions["p1"] = object()  # not serializable

        with pytest.raises(TypeError):
            storage.save_game_state(broken, game_dir)

        # Original still intact, and no temp files left behind
        assert (game_dir / "state.json").read_text(encoding="utf-8") == good
        assert list(game_dir.glob(".state-*.tmp")) == []


# ============================================================================
# ORDER PARSING & AUTHORIZATION
# ============================================================================

def test_capture_order_parses(two_faction_state):
    """
    parse_capture_order passed enemy_ok= to a resolver that had no such
    parameter, so any CAPTURE order raised TypeError and took the whole turn
    down with it.
    """
    parsed = parser.parse_orders("Have Marcus capture Tengri.", two_faction_state, "p1")

    capture_orders = [o for o in parsed if isinstance(o, orders.CaptureOrder)]
    assert len(capture_orders) == 1
    assert capture_orders[0].actor_id == "c1"
    assert "c2" in capture_orders[0].target_ids


def test_cannot_use_an_enemy_character_as_actor(two_faction_state):
    """
    Actor lookup fell back to searching every faction, so naming an opponent's
    character bound them as your actor and let you act on their behalf.
    """
    parsed = parser.parse_orders("Have Tengri go to Carthage.", two_faction_state, "p1")

    move_orders = [o for o in parsed if isinstance(o, orders.MoveOrder)]
    assert len(move_orders) == 1
    assert move_orders[0].actor_id == ""
    assert move_orders[0].warnings


def test_engine_rejects_order_for_another_factions_character(two_faction_state):
    """Even a hand-built order naming an enemy actor must be refused."""
    order = orders.MoveOrder(player_id="p1", actor_id="c2", destination_city_id="city1")

    engine.run_turn(two_faction_state, {"p1": [order]}, seed=1)

    assert any("does not belong to you" in w for w in order.warnings)
    assert two_faction_state.characters["c2"].location_city_id == "city2"


def test_dead_character_cannot_act(two_faction_state):
    """Only the newer phases checked is_dead; movement and the rest did not."""
    two_faction_state.characters["c1"].is_dead = True
    order = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")

    engine.run_turn(two_faction_state, {"p1": [order]}, seed=1)

    assert any("dead" in w for w in order.warnings)
    assert two_faction_state.characters["c1"].location_city_id == "city1"


def test_prisoner_cannot_act(two_faction_state):
    """A captured character kept issuing orders as if free."""
    two_faction_state.characters["c1"].is_prisoner = True
    two_faction_state.characters["c1"].captor_id = "c2"
    order = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")

    engine.run_turn(two_faction_state, {"p1": [order]}, seed=1)

    assert any("prisoner" in w for w in order.warnings)
    assert two_faction_state.characters["c1"].location_city_id == "city1"


# ============================================================================
# MOVEMENT
# ============================================================================

def test_land_movement_cannot_cross_a_sea_lane(two_faction_state):
    """
    find_shortest_path walked the whole road graph including sea lanes, so
    characters strolled across open water without a ship.
    """
    gs = two_faction_state
    del gs.world_map.roads["road1"]  # leave only a sea connection
    gs.world_map.roads["sea1"] = models.Road(
        id="sea1", from_city_id="city1", to_city_id="city2", quality=models.RoadQuality.SEA
    )

    path, cost = engine.find_shortest_path("city1", "city2", gs)
    assert path == []
    assert cost == float("inf")

    # ...but a ship may use it
    sea_path, sea_cost = engine.find_sea_route("city1", "city2", gs)
    assert sea_path == ["city1", "city2"]
    assert sea_cost < float("inf")


def test_cheap_roads_still_cost_movement_points(two_faction_state):
    """
    Movement cost was truncated with int(), so an excellent road (cost 0.5)
    deducted zero points and allowed unlimited travel per turn.
    """
    gs = two_faction_state
    gs.world_map.roads["road1"].quality = models.RoadQuality.EXCELLENT
    start_points = gs.characters["c1"].movement_points

    order = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    engine.run_turn(gs, {"p1": [order]}, seed=1)

    char = gs.characters["c1"]
    assert char.location_city_id == "city2"
    # cleanup_turn resets points, so compare against the per-turn allowance
    assert start_points == config.CHARACTER_MOVEMENT_POINTS_PER_TURN

    # Verify the deduction directly, before end-of-turn reset
    gs2 = copy.deepcopy(two_faction_state)
    gs2.world_map.roads["road1"].quality = models.RoadQuality.EXCELLENT
    log = engine.TurnLog()
    order2 = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    engine.process_movement({"p1": [order2]}, gs2, log, __import__("random").Random(1))
    assert gs2.characters["c1"].movement_points < config.CHARACTER_MOVEMENT_POINTS_PER_TURN


def test_sail_respects_ship_capacity(two_faction_state):
    """A single galley used to ferry every unit in the port, capacity ignored."""
    gs = two_faction_state
    gs.world_map.roads["sea1"] = models.Road(
        id="sea1", from_city_id="city1", to_city_id="city2", quality=models.RoadQuality.SEA
    )
    gs.ships["ship1"] = models.Ship(id="ship1", faction_id="p1", location_city_id="city1",
                                    ship_type=models.ShipType.GALLEY, capacity=100)
    gs.unit_stacks["sailors"] = models.UnitStack(
        id="sailors", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SAILOR, count=50)
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=500)

    order = orders.SailOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    engine.run_turn(gs, {"p1": [order]}, seed=1)

    assert gs.ships["ship1"].location_city_id == "city2"
    carried = sum(s.count for s in gs.unit_stacks.values()
                  if s.location_city_id == "city2" and s.faction_id == "p1")
    assert carried == 100  # exactly the galley's capacity, not all 550


def test_sail_requires_a_port_destination(two_faction_state):
    """Ships may only dock where there is a port."""
    gs = two_faction_state
    gs.world_map.cities["city2"].is_port = False
    gs.world_map.roads["sea1"] = models.Road(
        id="sea1", from_city_id="city1", to_city_id="city2", quality=models.RoadQuality.SEA
    )
    gs.ships["ship1"] = models.Ship(id="ship1", faction_id="p1", location_city_id="city1",
                                    ship_type=models.ShipType.GALLEY)

    order = orders.SailOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    engine.run_turn(gs, {"p1": [order]}, seed=1)

    assert any("not a port" in w for w in order.warnings)
    assert gs.ships["ship1"].location_city_id == "city1"


def test_sail_moves_only_the_captains_group_and_unassigned_crew(two_faction_state):
    gs = two_faction_state
    gs.world_map.roads["sea1"] = models.Road(
        id="sea1", from_city_id="city1", to_city_id="city2",
        quality=models.RoadQuality.SEA,
    )
    gs.ships["ship1"] = models.Ship(
        id="ship1", faction_id="p1", location_city_id="city1",
        ship_type=models.ShipType.GALLEY, capacity=100,
        owner_character_id="c1",
    )
    gs.characters["passenger"] = models.Character(
        id="passenger", name="Lucia", faction_id="p1",
        location_city_id="city1", group_leader_id="c1",
    )
    gs.characters["outsider"] = models.Character(
        id="outsider", name="Cassius", faction_id="p1",
        location_city_id="city1",
    )
    for stack_id, unit_type, owner in (
        ("crew", models.UnitType.SAILOR, ""),
        ("captain_unit", models.UnitType.SOLDIER, "c1"),
        ("passenger_unit", models.UnitType.SOLDIER, "passenger"),
        ("outsider_unit", models.UnitType.SOLDIER, "outsider"),
    ):
        gs.unit_stacks[stack_id] = models.UnitStack(
            id=stack_id, faction_id="p1", location_city_id="city1",
            unit_type=unit_type, count=10, owner_character_id=owner,
        )

    order = orders.SailOrder(
        player_id="p1", actor_id="c1", destination_city_id="city2",
        ship_id="ship1",
    )
    engine.run_turn(gs, {"p1": [order]}, seed=1)

    assert gs.ships["ship1"].location_city_id == "city2"
    assert gs.characters["c1"].location_city_id == "city2"
    assert gs.characters["passenger"].location_city_id == "city2"
    assert gs.unit_stacks["crew"].location_city_id == "city2"
    assert gs.unit_stacks["captain_unit"].location_city_id == "city2"
    assert gs.unit_stacks["passenger_unit"].location_city_id == "city2"
    assert gs.characters["outsider"].location_city_id == "city1"
    assert gs.unit_stacks["outsider_unit"].location_city_id == "city1"


def test_same_turn_secure_contention_gives_the_city_to_nobody(two_faction_state):
    """
    Occupation used to fall to whichever faction the loop reached first.

    Two armed factions inside one city is a military question, and a player
    could settle it administratively by writing SECURE before the other did --
    with one soldier, against any number. Now neither establishes anything
    until one of them is actually put out.
    """
    gs = two_faction_state
    gs.characters["c2"].location_city_id = "city1"
    for faction_id, owner_id in (("p1", "c1"), ("p2", "c2")):
        gs.unit_stacks[f"{faction_id}_garrison"] = models.UnitStack(
            id=f"{faction_id}_garrison", faction_id=faction_id,
            location_city_id="city1", unit_type=models.UnitType.SOLDIER,
            count=1, owner_character_id=owner_id,
        )
    first = orders.SecureOrder(player_id="p1", actor_id="c1", city_id="city1")
    second = orders.SecureOrder(player_id="p2", actor_id="c2", city_id="city1")

    log = engine.TurnLog()
    engine.process_secure({"p1": [first], "p2": [second]}, gs, log)

    assert "city1" not in gs.factions["p1"].secured_city_ids
    assert "city1" not in gs.factions["p2"].secured_city_ids
    failures = [event for event in log.events if event.event_type == "secure_failed"]
    assert {event.player_id for event in failures} == {"p1", "p2"}


def test_heal_restores_a_living_injured_character(two_faction_state):
    gs = two_faction_state
    healer = gs.characters["c1"]
    healer.religion_skill = healer.religious_power_current = 100
    target = gs.characters["c2"]
    target.location_city_id = "city1"
    target.health = 25
    order = orders.HealOrder(
        player_id="p1", actor_id="c1", target_character_ids=["c2"],
        heal_amounts={"c2": 30},
    )

    engine.process_magic({"p1": [order]}, gs, engine.TurnLog(), random.Random(1))

    assert target.health == 55
    assert target.is_dead is False


def test_heal_does_not_revive_or_spend_power_on_a_dead_character(two_faction_state):
    gs = two_faction_state
    healer = gs.characters["c1"]
    healer.religion_skill = healer.religious_power_current = 100
    target = gs.characters["c2"]
    target.location_city_id = "city1"
    target.health = 0
    target.is_dead = True
    order = orders.HealOrder(
        player_id="p1", actor_id="c1", target_character_ids=["c2"],
    )
    log = engine.TurnLog()

    engine.process_magic({"p1": [order]}, gs, log, random.Random(1))

    assert target.health == 0
    assert target.is_dead is True
    assert healer.religious_power_current == 100
    assert [event.event_type for event in log.events] == ["heal_failed"]


def test_heal_can_restore_zero_health_when_character_is_not_dead(two_faction_state):
    gs = two_faction_state
    healer = gs.characters["c1"]
    healer.religion_skill = healer.religious_power_current = 100
    target = gs.characters["c2"]
    target.location_city_id = "city1"
    target.health = 0
    target.is_dead = False
    order = orders.HealOrder(
        player_id="p1", actor_id="c1", target_character_ids=["c2"],
        heal_amounts={"c2": 20},
    )

    engine.process_magic({"p1": [order]}, gs, engine.TurnLog(), random.Random(1))

    assert target.health == 20
    assert target.is_dead is False


def test_resurrection_remains_the_only_path_back_from_death(two_faction_state):
    gs = two_faction_state
    priest = gs.characters["c1"]
    priest.religion_skill = 100
    target = gs.characters["c2"]
    target.location_city_id = "city1"
    target.health = 0
    target.is_dead = True
    order = orders.ResurrectOrder(
        player_id="p1", actor_id="c1", target_id="c2",
    )

    engine.process_religion(
        {"p1": [order]}, gs, engine.TurnLog(), random.Random(1)
    )

    assert target.is_dead is False
    assert target.health == 50


# ============================================================================
# ECONOMY
# ============================================================================

def test_tax_blocked_in_city_secured_by_another_faction(two_faction_state):
    """
    The secured-city guard used `continue` inside the faction loop, which only
    advanced that inner loop -- the order then went on to collect anyway.
    """
    gs = two_faction_state
    gs.factions["p2"].secured_city_ids.add("city1")
    gs.characters["c2"].location_city_id = "city1"
    gs.tax_pools["city1"] = 500
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=40)
    gs.unit_stacks["occupiers"] = models.UnitStack(
        id="occupiers", faction_id="p2", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=10, owner_character_id="c2")

    treasury_before = gs.factions["p1"].treasury
    order = orders.TaxOrder(player_id="p1", actor_id="c1", city_id="city1", duration_days=7)
    _, log = engine.run_turn(gs, {"p1": [order]}, seed=1)

    assert any(e.event_type == "tax_failed" for e in log.get_player_events("p1"))
    # Pool untouched by collection (income still accrues normally)
    assert gs.tax_pools["city1"] >= 500
    # Treasury only moved by upkeep, never gained tax
    assert gs.factions["p1"].treasury <= treasury_before


def test_give_gold_credits_the_recipient(two_faction_state):
    """Gold moves between character purses (was once destroyed on transfer)."""
    gs = two_faction_state
    gs.characters["c2"].location_city_id = "city1"  # same location required
    gs.characters["c1"].gold = 200
    gs.characters["c2"].gold = 0

    order = orders.AssignOrder(player_id="p1", donor_id="c1", recipient_id="c2",
                               gold_amount=100)
    engine.run_turn(gs, {"p1": [order]}, seed=1)

    assert gs.characters["c1"].gold == 100
    assert gs.characters["c2"].gold == 100


def test_trade_prices_come_from_config_not_the_order(two_faction_state):
    """
    TradeOrder used to carry a `price` the engine trusted. Prices are now set
    by config, so an order cannot name what its goods are worth.
    """
    gs = two_faction_state
    gs.characters["c1"].resources["gems"] = 10
    gold_before = gs.characters["c1"].gold

    order = orders.TradeOrder(player_id="p1", actor_id="c1", city_id="city1",
                              resource_type="gems", amount=10, action="sell")
    assert not hasattr(order, "price")

    engine.run_turn(gs, {"p1": [order]}, seed=1)

    # Sold at the configured gems price (minus spread), not an arbitrary one
    gained = gs.characters["c1"].gold - gold_before
    assert 0 < gained <= config.get_resource_price("gems") * 10
    assert gs.characters["c1"].resources["gems"] == 0


def test_trading_the_same_goods_back_is_not_profitable(two_faction_state):
    """Buying then selling in one place must never mint gold, at any skill."""
    for skill in (0, 50, 100):
        gs = copy.deepcopy(two_faction_state)
        gs.characters["c1"].trading_skill = skill
        gs.characters["c1"].gold = 1000
        start = gs.characters["c1"].gold

        buy = orders.TradeOrder(player_id="p1", actor_id="c1", city_id="city1",
                                resource_type="iron", amount=10, action="buy")
        sell = orders.TradeOrder(player_id="p1", actor_id="c1", city_id="city1",
                                 resource_type="iron", amount=10, action="sell")
        engine.run_turn(gs, {"p1": [buy, sell]}, seed=1)

        assert gs.characters["c1"].gold <= start, f"arbitrage at skill {skill}"


# ============================================================================
# ENTITY IDS
# ============================================================================

def test_allocate_id_skips_used_ids():
    """
    Ids derived from len(registry) collided after any removal -- a stack wiped
    out in combat freed its number and the next allocation overwrote a live one.
    """
    registry = {"stack_1": object(), "stack_2": object(), "stack_3": object()}
    del registry["stack_2"]  # len is now 2, so len+1 == "stack_3" (taken)

    new_id = engine.allocate_id(registry, "stack")

    assert new_id not in registry


def test_assign_does_not_overwrite_an_existing_stack(two_faction_state):
    """Transferring units must not clobber a stack that already holds troops."""
    gs = two_faction_state
    gs.characters["c2"].location_city_id = "city1"
    gs.unit_stacks["stack_1"] = models.UnitStack(
        id="stack_1", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=50)
    gs.unit_stacks["stack_2"] = models.UnitStack(
        id="stack_2", faction_id="p2", location_city_id="city2",
        unit_type=models.UnitType.WORKER, count=7)

    order = orders.AssignOrder(player_id="p1", donor_id="c1", recipient_id="c2",
                               unit_type="SOLDIER", unit_count=20)
    engine.run_turn(gs, {"p1": [order]}, seed=1)

    # The unrelated stack survives untouched
    assert gs.unit_stacks["stack_2"].count == 7
    assert gs.unit_stacks["stack_2"].unit_type == models.UnitType.WORKER
    # And the recipient's faction received the soldiers
    received = sum(s.count for s in gs.unit_stacks.values()
                   if s.faction_id == "p2" and s.unit_type == models.UnitType.SOLDIER)
    assert received == 20


def test_every_phase_skips_orders_that_failed_validation(two_faction_state):
    """
    Some phases acted on orders regardless of their warnings, so an order the
    validator had already rejected still took effect.
    """
    gs = two_faction_state
    gs.characters["c1"].religion_skill = 50
    gs.characters["c1"].resources["stone"] = 100
    treasury_before = gs.factions["p1"].treasury
    forts_before = {c.id: c.fortification_level for c in gs.world_map.cities.values()}

    # Orders naming another faction's character -- all must be refused
    pray = orders.PrayOrder(player_id="p1", actor_id="c2")
    fortify = orders.FortifyOrder(player_id="p1", actor_id="c2", city_id="city1", percent=10)
    trade = orders.TradeOrder(player_id="p1", actor_id="c2", city_id="city1",
                              resource_type="iron", amount=5, action="buy")

    engine.run_turn(gs, {"p1": [pray, fortify, trade]}, seed=1)

    for order in (pray, fortify, trade):
        assert order.warnings, f"{type(order).__name__} was not rejected"

    # No PRAY tithe, no trade spend: treasury moved only by upkeep (none here)
    assert gs.factions["p1"].treasury == treasury_before
    assert {c.id: c.fortification_level for c in gs.world_map.cities.values()} == forts_before


# ============================================================================
# REPORTING
# ============================================================================

def test_report_shows_events_from_every_phase(two_faction_state):
    """
    The report rendered a hardcoded list of six phases, so results from tax,
    trade, construction, religion and most other phases never reached players.
    """
    from soe import reporting

    gs = two_faction_state
    gs.tax_pools["city1"] = 500
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=40)

    tax_order = orders.TaxOrder(player_id="p1", actor_id="c1", city_id="city1",
                                duration_days=7)
    state, log = engine.run_turn(gs, {"p1": [tax_order]}, seed=1)

    assert any(e.phase == "tax" and e.success for e in log.get_player_events("p1"))

    reports = reporting.generate_player_reports(state, log, {"p1": [tax_order]})
    assert "collected" in reports["p1"], "tax result missing from the player report"


# ============================================================================
# DETERMINISM
# ============================================================================

def test_same_seed_same_outcome(two_faction_state):
    """Turn processing must be reproducible for a given seed."""
    order_a = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    order_b = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")

    state_a, _ = engine.run_turn(copy.deepcopy(two_faction_state), {"p1": [order_a]}, seed=99)
    state_b, _ = engine.run_turn(copy.deepcopy(two_faction_state), {"p1": [order_b]}, seed=99)

    assert asdict(state_a) == asdict(state_b)
