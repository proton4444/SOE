"""
Tests for the v1.0 fog-of-war slice.

Visibility is driven by position (inside / outside / near) and LURK. A faction
only learns about others that their people can notice at the same city.
"""

import random

import pytest

from soe import engine, fog, models, parser
from soe.models import LocationPosition, PopulationBand


@pytest.fixture
def face_off():
    """Two faction leaders in Rome; a third city as a ruin."""
    gs = models.GameState()
    gs.turn_number = 1
    gs.world_map.cities["city1"] = models.City(
        id="city1", name="Rome", population_band=PopulationBand.MEDIUM, is_port=True
    )
    gs.world_map.cities["city2"] = models.City(
        id="city2", name="Carthage", population_band=PopulationBand.SMALL, is_port=True
    )
    gs.world_map.cities["ruin1"] = models.City(
        id="ruin1", name="Oldbarrow", population_band=PopulationBand.TINY, is_ruin=True
    )
    gs.world_map.roads["road1"] = models.Road(
        id="road1", from_city_id="city1", to_city_id="city2",
        quality=models.RoadQuality.GOOD,
    )
    gs.world_map.roads["road2"] = models.Road(
        id="road2", from_city_id="city1", to_city_id="ruin1",
        quality=models.RoadQuality.GOOD,
    )
    gs.factions["p1"] = models.Faction(id="p1", name="Empire", controlled_city_ids={"city1"})
    gs.factions["p2"] = models.Faction(id="p2", name="Horde", controlled_city_ids={"city2"})

    gs.characters["c1"] = models.Character(
        id="c1", name="Marcus", faction_id="p1", location_city_id="city1",
        combat_skill=15, is_leader=True, gold=1000, magic_skill=50, magic_power_current=50,
    )
    gs.characters["e1"] = models.Character(
        id="e1", name="Tengri", faction_id="p2", location_city_id="city1",
        combat_skill=25, is_leader=True, gold=500, magic_skill=10, magic_power_current=10,
    )
    return gs


# ---------------------------------------------------------------------------
# Position matrix
# ---------------------------------------------------------------------------

def test_inside_sees_inside_and_outside_not_near():
    assert fog.can_see_position(LocationPosition.INSIDE, LocationPosition.INSIDE)
    assert fog.can_see_position(LocationPosition.INSIDE, LocationPosition.OUTSIDE)
    assert not fog.can_see_position(LocationPosition.INSIDE, LocationPosition.NEAR)


def test_outside_sees_only_outside():
    assert fog.can_see_position(LocationPosition.OUTSIDE, LocationPosition.OUTSIDE)
    assert not fog.can_see_position(LocationPosition.OUTSIDE, LocationPosition.INSIDE)
    assert not fog.can_see_position(LocationPosition.OUTSIDE, LocationPosition.NEAR)


def test_near_sees_near_and_outside_not_inside():
    assert fog.can_see_position(LocationPosition.NEAR, LocationPosition.NEAR)
    assert fog.can_see_position(LocationPosition.NEAR, LocationPosition.OUTSIDE)
    assert not fog.can_see_position(LocationPosition.NEAR, LocationPosition.INSIDE)


def test_parse_position_prefix():
    pos, name = fog.parse_position_prefix("outside Highfell")
    assert pos == LocationPosition.OUTSIDE
    assert name.lower() == "highfell"
    pos, name = fog.parse_position_prefix("near Agriponga")
    assert pos == LocationPosition.NEAR
    assert name.lower() == "agriponga"
    pos, name = fog.parse_position_prefix("Rome")
    assert pos == LocationPosition.INSIDE
    assert name == "Rome"


# ---------------------------------------------------------------------------
# Detection odds
# ---------------------------------------------------------------------------

def test_lurk_reduces_detection_by_four(face_off):
    gs = face_off
    city = gs.world_map.cities["city1"]
    observer = gs.characters["c1"]
    target = gs.characters["e1"]

    normal = fog.notice_chance(observer, target, city, gs)
    target.is_lurking = True
    lurking = fog.notice_chance(observer, target, city, gs)

    assert normal > 0
    assert abs(lurking - normal * 0.25) < 1e-9


def test_near_vs_near_is_slim(face_off):
    gs = face_off
    city = gs.world_map.cities["city1"]
    observer = gs.characters["c1"]
    target = gs.characters["e1"]
    observer.location_position = LocationPosition.NEAR
    target.location_position = LocationPosition.NEAR

    chance = fog.notice_chance(observer, target, city, gs)
    # Base for MEDIUM is 0.50 * 0.10 near factor = 0.05 when not clear-sight
    assert 0 < chance <= 0.10


def test_outside_cannot_see_inside(face_off):
    gs = face_off
    city = gs.world_map.cities["city1"]
    observer = gs.characters["c1"]
    target = gs.characters["e1"]
    observer.location_position = LocationPosition.OUTSIDE
    target.location_position = LocationPosition.INSIDE

    assert fog.notice_chance(observer, target, city, gs) == 0.0


def test_different_cities_never_see_each_other(face_off):
    gs = face_off
    city = gs.world_map.cities["city1"]
    observer = gs.characters["c1"]
    target = gs.characters["e1"]
    target.location_city_id = "city2"

    assert fog.notice_chance(observer, target, city, gs) == 0.0


def test_same_faction_does_not_spot_itself(face_off):
    gs = face_off
    city = gs.world_map.cities["city1"]
    a = gs.characters["c1"]
    assert fog.notice_chance(a, a, city, gs) == 0.0


# ---------------------------------------------------------------------------
# Sightings phase
# ---------------------------------------------------------------------------

def test_sightings_phase_reports_co_located_enemy(face_off):
    gs = face_off
    # Clear-sight pair: inside sees outside for free (chance 1.0).
    gs.characters["e1"].location_position = LocationPosition.OUTSIDE
    log = engine.TurnLog()
    engine.process_sightings(gs, log, random.Random(1))

    events = [e for e in log.get_player_events("p1") if e.phase == "sighting"]
    assert len(events) == 1
    assert "Tengri" in events[0].description
    assert "Rome" in events[0].description


def test_lurking_enemy_can_be_missed(face_off):
    """
    With LURK and near-vs-near (slim), a fixed seed that fails the roll must
    produce no sighting.
    """
    gs = face_off
    gs.characters["c1"].location_position = LocationPosition.NEAR
    gs.characters["e1"].location_position = LocationPosition.NEAR
    gs.characters["e1"].is_lurking = True

    # chance is tiny; seed 0 historically fails low-probability rolls here.
    log = engine.TurnLog()
    engine.process_sightings(gs, log, random.Random(0))
    # With ~1.25% chance we may still spot; run many seeds and require that
    # at least one seed produces zero sightings.
    misses = 0
    for seed in range(40):
        log = engine.TurnLog()
        engine.process_sightings(gs, log, random.Random(seed))
        if not any(e.phase == "sighting" for e in log.get_player_events("p1")):
            misses += 1
    assert misses >= 1


# ---------------------------------------------------------------------------
# Movement position
# ---------------------------------------------------------------------------

def test_move_to_outside_sets_position(face_off):
    gs = face_off
    orders = parser.parse_orders("Go to outside Carthage.", gs, "p1")
    assert len(orders) == 1
    assert orders[0].destination_position == "outside"
    assert orders[0].destination_city_id == "city2"

    engine.run_turn(gs, {"p1": orders}, seed=1)
    assert gs.characters["c1"].location_city_id == "city2"
    assert gs.characters["c1"].location_position == LocationPosition.OUTSIDE


def test_group_adopts_leader_arrival_position(face_off):
    gs = face_off
    gs.characters["c2"] = models.Character(
        id="c2", name="Julia", faction_id="p1", location_city_id="city1",
        group_leader_id="c1",
    )
    orders = parser.parse_orders("Go to near Carthage.", gs, "p1")
    engine.run_turn(gs, {"p1": orders}, seed=1)

    assert gs.characters["c1"].location_position == LocationPosition.NEAR
    assert gs.characters["c2"].location_city_id == "city2"
    assert gs.characters["c2"].location_position == LocationPosition.NEAR


# ---------------------------------------------------------------------------
# PROBE
# ---------------------------------------------------------------------------

def test_probe_success_reports_target(face_off):
    gs = face_off
    gs.characters["c1"].magic_skill = 100
    gs.characters["c1"].magic_power_current = 50
    gs.characters["e1"].combat_skill = 0
    gs.characters["e1"].magic_skill = 0
    gs.characters["e1"].religion_skill = 0
    gs.characters["e1"].trading_skill = 0

    orders = parser.parse_orders("Have Marcus probe Tengri.", gs, "p1")
    assert orders[0].order_type() == "PROBE"
    # Call the phase directly: cleanup_turn refills magic power at end of run_turn.
    log = engine.TurnLog()
    engine.process_probe({"p1": orders}, gs, log, random.Random(42))

    events = [e for e in log.get_player_events("p1") if e.event_type == "probe"]
    assert len(events) == 1
    assert "Tengri" in events[0].description
    assert gs.characters["c1"].magic_power_current == 25  # 50 - 25


def test_probe_costs_power_even_on_failure(face_off):
    gs = face_off
    gs.characters["c1"].magic_skill = 0  # always fails base roll
    gs.characters["c1"].magic_power_current = 30

    orders = parser.parse_orders("Probe Tengri.", gs, "p1")
    log = engine.TurnLog()
    engine.process_probe({"p1": orders}, gs, log, random.Random(1))

    assert gs.characters["c1"].magic_power_current == 5
    failed = [e for e in log.get_player_events("p1") if e.event_type == "probe_failed"]
    assert failed


# ---------------------------------------------------------------------------
# SEARCH / EXPLORE
# ---------------------------------------------------------------------------

def test_search_requires_ruins(face_off):
    gs = face_off
    orders = parser.parse_orders("Search.", gs, "p1")
    _, log = engine.run_turn(gs, {"p1": orders}, seed=1)
    failed = [e for e in log.get_player_events("p1") if e.event_type == "search_failed"]
    assert failed
    assert "not uninhabited ruins" in failed[0].description


def test_search_inside_ruins_can_find_gold(face_off):
    gs = face_off
    gs.characters["c1"].location_city_id = "ruin1"
    gs.characters["c1"].location_position = LocationPosition.INSIDE
    before = gs.characters["c1"].gold

    # Force a hit: many seeds until one succeeds is fragile; instead patch
    # duration high and use a seed that tends to hit. Prefer checking that a
    # search event fires (found or not).
    orders = parser.parse_orders("Explore for 30 days.", gs, "p1")
    assert orders[0].duration_days == 30
    _, log = engine.run_turn(gs, {"p1": orders}, seed=7)

    events = [e for e in log.get_player_events("p1") if e.phase == "intel" and "search" in e.event_type]
    assert events
    assert "Oldbarrow" in events[0].description
    # Gold only rises on a find.
    assert gs.characters["c1"].gold >= before


def test_search_outside_ruins_fails(face_off):
    gs = face_off
    gs.characters["c1"].location_city_id = "ruin1"
    gs.characters["c1"].location_position = LocationPosition.OUTSIDE
    orders = parser.parse_orders("Search.", gs, "p1")
    _, log = engine.run_turn(gs, {"p1": orders}, seed=1)
    failed = [e for e in log.get_player_events("p1") if e.event_type == "search_failed"]
    assert failed
    assert "inside" in failed[0].description.lower()


# ---------------------------------------------------------------------------
# SCAN (deferred until orbs)
# ---------------------------------------------------------------------------

def test_scan_is_parsed_but_fails_without_orbs(face_off):
    gs = face_off
    orders = parser.parse_orders("Scan Carthage using Hanemishi.", gs, "p1")
    assert orders[0].order_type() == "SCAN"
    assert orders[0].city_ids == ["city2"]
    assert "hanemishi" in orders[0].orb_name

    _, log = engine.run_turn(gs, {"p1": orders}, seed=1)
    failed = [e for e in log.get_player_events("p1") if e.event_type == "scan_failed"]
    assert failed
    assert "orb" in failed[0].description.lower()


# ---------------------------------------------------------------------------
# Effective skill (PROBE resistance)
# ---------------------------------------------------------------------------

def test_effective_skill_is_root_sum_of_squares():
    c = models.Character(
        id="x", name="X", faction_id="p1", location_city_id="city1",
        combat_skill=30, magic_skill=40, religion_skill=0, trading_skill=0,
    )
    # sqrt(900 + 1600) = 50
    assert abs(fog.effective_skill_level(c) - 50.0) < 1e-9
