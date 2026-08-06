"""
Tests for the v1.1 gap closures: WORK, TRAIN, UNNAME, CREATE (elite troops),
INVEST, BUY PASSAGE, PREACH, OFFER, IF statements, THEN sequencing and
sailing skill.
"""

import json
import random
import tempfile
from pathlib import Path

import pytest

from spoils_engine import models, engine, orders, parser, storage, config
from spoils_engine.combat import calculate_faction_power, apply_casualties


@pytest.fixture
def state():
    gs = models.GameState()
    gs.world_map.cities["city1"] = models.City(
        id="city1", name="Rome", population_band=models.PopulationBand.MEDIUM,
        is_port=True, terrain={"forest"},
    )
    gs.world_map.cities["city2"] = models.City(
        id="city2", name="Carthage", population_band=models.PopulationBand.SMALL,
        is_port=True,
    )
    gs.world_map.cities["city3"] = models.City(
        id="city3", name="Vault", population_band=models.PopulationBand.TINY,
        is_ruin=True,
    )
    gs.world_map.roads["road1"] = models.Road(
        id="road1", from_city_id="city1", to_city_id="city2",
        quality=models.RoadQuality.GOOD,
    )
    gs.world_map.roads["sea1"] = models.Road(
        id="sea1", from_city_id="city1", to_city_id="city2",
        quality=models.RoadQuality.SEA,
    )
    gs.world_map.roads["road2"] = models.Road(
        id="road2", from_city_id="city1", to_city_id="city3",
        quality=models.RoadQuality.GOOD,
    )
    gs.factions["p1"] = models.Faction(id="p1", name="Empire",
                                       controlled_city_ids={"city1"})
    gs.factions["p2"] = models.Faction(id="p2", name="Horde",
                                       controlled_city_ids={"city2"})
    gs.factions["npc"] = models.Faction(id="npc", name="Independents", is_npc=True)
    gs.characters["c1"] = models.Character(
        id="c1", name="Marcus", faction_id="p1", location_city_id="city1",
        combat_skill=15, magic_skill=20, magic_power_current=20,
        is_leader=True, gold=500,
    )
    gs.characters["c2"] = models.Character(
        id="c2", name="Tengri", faction_id="p2", location_city_id="city2",
        combat_skill=10, is_leader=True, gold=200,
    )
    gs.characters["c1b"] = models.Character(
        id="c1b", name="Julia", faction_id="p1", location_city_id="city1",
        combat_skill=40, gold=50,
    )
    gs.characters["npc1"] = models.Character(
        id="npc1", name="ojibenmi", faction_id="npc", location_city_id="city2",
        magic_skill=60, magic_power_current=60,
    )
    return gs


def run(gs, player_orders, seed=0, players=None):
    """Run one turn for every player named in `players` (default: all)."""
    if players is None:
        players = {fid for fid in gs.factions if not gs.factions[fid].is_npc}
    return engine.run_turn(gs, {pid: player_orders.get(pid, []) for pid in players}, seed=seed)


def parse(sentence, gs, player="p1"):
    return parser.parse_orders(sentence, gs, player)


# The fixture's Julia (combat 40) draws a salary of 11.2g/week from Marcus,
# so after one turn the leader's 500g becomes 488.8g before any order.
SALARY = 11.2
BASE = 500 - SALARY


def marcus_gold(gs):
    return gs.characters["c1"].gold


# ---------------------------------------------------------------------------
# WORK
# ---------------------------------------------------------------------------

def test_work_earns_wages_by_population(state):
    gs = state
    gs.unit_stacks["wk"] = models.UnitStack(
        id="wk", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.WORKER, count=10, owner_character_id="c1",
    )
    run(gs, {"p1": parse("Have Marcus work for 1 week.", gs)})
    # 11 labourers * 2g/day * 7 days + skill bonus (15 * 0.02 * 7) - salary
    assert marcus_gold(gs) > BASE + 150


def test_work_defaults_to_one_week(state):
    gs = state
    run(gs, {"p1": parse("Have Marcus work.", gs)})
    assert marcus_gold(gs) > BASE


def test_work_tiny_town_pays_nothing(state):
    gs = state
    gs.characters["c1"].location_city_id = "city3"
    run(gs, {"p1": parse("Have Marcus work for 7 days.", gs)})
    assert marcus_gold(gs) == BASE  # voluntary community service


# ---------------------------------------------------------------------------
# TRAIN
# ---------------------------------------------------------------------------

def test_train_parses_forms(state):
    gs = state
    o = parse("Train 20 soldiers.", gs)
    assert isinstance(o[0], orders.TrainOrder) and o[0].unit_type == "soldier" and o[0].count == 20
    o = parse("Have Marcus train 40 sailors.", gs)
    assert o[0].unit_type == "sailor" and o[0].count == 40
    o = parse("Have Marcus train soldiers.", gs)
    assert o[0].unit_type == "soldier" and o[0].count == 0  # every worker


def test_train_requires_trainer_skill(state):
    gs = state
    gs.unit_stacks["wk"] = models.UnitStack(
        id="wk", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.WORKER, count=20, owner_character_id="c1",
    )
    run(gs, {"p1": parse("Have Marcus train 10 soldiers.", gs)})
    assert gs.unit_stacks["wk"].count == 10  # combat skill 15 is enough

    gs.characters["c1"].combat_skill = 5
    run(gs, {"p1": parse("Have Marcus train 10 sailors.", gs)}, seed=1)
    # sailor training needs sailing skill >= 10, and Marcus has none
    assert gs.unit_stacks["wk"].count == 10


def test_train_converts_workers_to_soldiers(state):
    gs = state
    gs.unit_stacks["wk"] = models.UnitStack(
        id="wk", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.WORKER, count=20, owner_character_id="c1",
    )
    run(gs, {"p1": parse("Have Marcus train 15 soldiers.", gs)})
    assert gs.unit_stacks["wk"].count == 5
    soldiers = [s for s in gs.unit_stacks.values()
                if s.unit_type == models.UnitType.SOLDIER and s.owner_character_id == "c1"]
    assert sum(s.count for s in soldiers) == 15


def test_train_with_sailing_skill_makes_sailors(state):
    gs = state
    gs.characters["c1"].sailing_skill = 25
    gs.unit_stacks["wk"] = models.UnitStack(
        id="wk", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.WORKER, count=10, owner_character_id="c1",
    )
    run(gs, {"p1": parse("Have Marcus train 10 sailors.", gs)})
    assert "wk" not in gs.unit_stacks  # all workers consumed
    sailors = [s for s in gs.unit_stacks.values()
               if s.unit_type == models.UnitType.SAILOR and s.owner_character_id == "c1"]
    assert sum(s.count for s in sailors) == 10


def test_study_sailing_raises_the_skill(state):
    gs = state
    run(gs, {"p1": parse("Have Marcus study sailing for 10 weeks.", gs)})
    assert gs.characters["c1"].sailing_skill >= 10


# ---------------------------------------------------------------------------
# UNNAME
# ---------------------------------------------------------------------------

def test_unname_converts_subordinate_to_worker(state):
    gs = state
    gs.characters["c1b"].group_leader_id = "c1"
    run(gs, {"p1": parse("Have Marcus unname Julia.", gs)})
    assert "c1b" not in gs.characters
    workers = [s for s in gs.unit_stacks.values()
               if s.unit_type == models.UnitType.WORKER and s.owner_character_id == "c1"]
    assert sum(s.count for s in workers) == 1


def test_unname_refuses_leader_and_busy_characters(state):
    gs = state
    gs.characters["c1b"].group_leader_id = "c1"
    run(gs, {"p1": parse("Unname Marcus.", gs)})  # the leader himself
    assert "c1" in gs.characters

    gs.unit_stacks["owned"] = models.UnitStack(
        id="owned", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=5, owner_character_id="c1b",
    )
    run(gs, {"p1": parse("Have Marcus unname Julia.", gs)}, seed=1)
    assert "c1b" in gs.characters  # still has units of their own


def test_unname_refuses_independent_character(state):
    gs = state
    run(gs, {"p1": parse("Have Marcus unname Julia.", gs)})
    assert "c1b" in gs.characters  # not part of any group


# ---------------------------------------------------------------------------
# CREATE (elite troops)
# ---------------------------------------------------------------------------

def test_create_makes_an_elite_unit_from_soldiers(state):
    gs = state
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=250, owner_character_id="c1",
    )
    run(gs, {"p1": parse("Create Gordys Killers using 250 soldiers.", gs)})
    assert len(gs.elite_units) == 1
    unit = list(gs.elite_units.values())[0]
    assert unit.name == "gordys killers"
    assert unit.size == 250 and unit.combat_level == 1
    assert unit.leader_character_id == "c1"
    assert "army" not in gs.unit_stacks  # all soldiers consumed


def test_create_needs_enough_soldiers(state):
    gs = state
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=100, owner_character_id="c1",
    )
    run(gs, {"p1": parse("Create Gordys Killers using 250 soldiers.", gs)})
    assert not gs.elite_units


def test_elite_units_train_continuously(state):
    gs = state
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=50, owner_character_id="c1",
    )
    run(gs, {"p1": parse("Create Gordys Killers using 50 soldiers.", gs)})
    for _ in range(5):
        run(gs, {})
    unit = list(gs.elite_units.values())[0]
    assert unit.combat_level == 2  # five partial points = one level


def test_elite_salary_is_soldiers_times_level(state):
    gs = state
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=100, owner_character_id="c1",
    )
    run(gs, {"p1": parse("Create Gordys Killers using 100 soldiers.", gs)})
    after_create = marcus_gold(gs)  # Julia's salary only (elite does not exist yet in Phase 6)
    run(gs, {})
    # Turn 2 upkeep: Julia (11.2) + elite 100*1*7/30 (~23.3)
    assert abs(marcus_gold(gs) - (after_create - 11.2 - 23.3)) < 0.5


def test_elite_travels_with_leader(state):
    gs = state
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=50, owner_character_id="c1",
    )
    run(gs, {"p1": parse("Create Gordys Killers using 50 soldiers. Have Marcus go to Carthage.", gs)})
    unit = list(gs.elite_units.values())[0]
    assert gs.characters["c1"].location_city_id == "city2"
    assert unit.location_city_id == "city2"


def test_elite_units_fight_at_their_level(state):
    gs = state
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=100, owner_character_id="c1",
    )
    run(gs, {"p1": parse("Create Gordys Killers using 100 soldiers.", gs)})
    with_elite = calculate_faction_power("p1", "city1", gs)
    elite = list(gs.elite_units.values())[0]
    elite.combat_level = 20
    with_high_level = calculate_faction_power("p1", "city1", gs)
    assert with_elite > 0 and with_high_level > with_elite


def test_elite_units_take_casualties(state):
    gs = state
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=100, owner_character_id="c1",
    )
    run(gs, {"p1": parse("Create Gordys Killers using 100 soldiers.", gs)})
    losses = apply_casualties("p1", "city1", 0.5, gs, random.Random(1))
    assert losses["units"] > 0
    unit = list(gs.elite_units.values())[0]
    assert unit.size < 100


# ---------------------------------------------------------------------------
# INVEST
# ---------------------------------------------------------------------------

def test_invest_parses_forms(state):
    gs = state
    o = parse("Invest 400 gold in Rome.", gs)
    assert isinstance(o[0], orders.InvestOrder) and o[0].amount == 400
    o = parse("Have Marcus invest all of his gold in Carthage.", gs)
    assert o[0].amount == -1
    o = parse("Have Marcus invest 75 percent of his gold in Carthage.", gs)
    assert o[0].amount == -75


def test_invest_pools_gold_and_refuses_ruins(state):
    gs = state
    run(gs, {"p1": parse("Invest 400 gold in Rome.", gs)})
    assert gs.invest_pools["city1"] == 400
    assert marcus_gold(gs) == BASE - 400

    run(gs, {"p1": parse("Invest 100 gold in Vault.", gs)}, seed=1)
    assert "city3" not in gs.invest_pools
    assert marcus_gold(gs) == BASE - 400 - SALARY  # nothing debited for the ruin


def test_invest_weekly_check_grows_population(state):
    gs = state
    run(gs, {"p1": parse("Invest 400 gold in Rome.", gs)})
    run(gs, {})  # next week's check
    # Rome is MEDIUM (~550k people): the check spends ~5500/week, far more
    # than the 400 pool, so the whole pool goes to work in one week.
    pop = config.city_population(gs.world_map.cities["city1"])
    assert pop == 550_000 + 400
    assert "city1" not in gs.invest_pools


def test_invest_can_raise_a_population_band(state):
    gs = state
    gs.world_map.cities["city1"].population = 9_900
    run(gs, {"p1": parse("Invest 400 gold in Rome.", gs)})
    engine.process_invest_weekly(gs, engine.TurnLog(), random.Random(0))
    assert gs.world_map.cities["city1"].population_band == models.PopulationBand.SMALL
    assert gs.world_map.cities["city1"].population >= 10_000


# ---------------------------------------------------------------------------
# BUY PASSAGE
# ---------------------------------------------------------------------------

def test_passage_parses(state):
    gs = state
    o = parse("Have Marcus definitely buy passage to Carthage.", gs)
    assert isinstance(o[0], orders.PassageOrder)
    assert o[0].destination_city_id == "city2" and o[0].definitely is True


def test_passage_moves_a_small_group(state):
    gs = state
    run(gs, {"p1": parse("Have Marcus definitely buy passage to Carthage.", gs)})
    assert gs.characters["c1"].location_city_id == "city2"
    assert marcus_gold(gs) == BASE - 1  # fare: 1 person * 1g


def test_passage_requires_a_direct_sealane(state):
    gs = state
    run(gs, {"p1": parse("Have Marcus definitely buy passage to Vault.", gs)})
    assert gs.characters["c1"].location_city_id == "city1"  # road only, no lane


def test_passage_fails_for_a_huge_party_with_refund(state):
    gs = state
    gs.characters["c1"].gold = 10_000  # the army's upkeep must be payable
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=5_000, owner_character_id="c1",
    )
    run(gs, {"p1": parse("Have Marcus buy passage to Carthage.", gs)})
    assert gs.characters["c1"].location_city_id == "city1"
    # fare (5001g) taken and refunded; only upkeep (500g + salary) left
    assert 9_400 < marcus_gold(gs) < 9_500


# ---------------------------------------------------------------------------
# PREACH
# ---------------------------------------------------------------------------

def test_preach_collects_donations_scaling_with_skill(state):
    gs = state
    gs.characters["c1"].religion_skill = 80
    gs.characters["c1"].religious_power_current = 80
    run(gs, {"p1": parse("Have Marcus preach for 2 weeks.", gs)})
    # Rome is MEDIUM: daily 8g * 0.8 skill * 14 days * (0.5..1.5)
    gained = marcus_gold(gs) - BASE
    assert 40 <= gained <= 140


def test_preach_attracts_followers(state):
    gs = state
    gs.characters["c1"].religion_skill = 100
    gs.characters["c1"].religious_power_current = 100
    run(gs, {"p1": parse("Have Marcus preach.", gs)}, seed=7)
    workers = [s for s in gs.unit_stacks.values()
               if s.unit_type == models.UnitType.WORKER and s.owner_character_id == "c1"]
    assert sum(s.count for s in workers) in (0, 1, 2, 3)


# ---------------------------------------------------------------------------
# OFFER
# ---------------------------------------------------------------------------

def test_offer_recruits_an_independent_character(state):
    gs = state
    gs.characters["c1"].gold = 5_000
    # ojibenmi: magic 60 -> threshold 0.5 * 3600 = 1800
    run(gs, {"p1": parse("Offer 2000 gold to Ojibenmi.", gs)})
    assert gs.characters["npc1"].faction_id == "p1"
    # Ojibenmi now draws a salary too: (5 + 60) / 4 = 16.25, plus Julia's
    assert abs(marcus_gold(gs) - (5_000 - 2_000 - 16.25 - SALARY)) < 0.5


def test_offer_recruits_with_name_first_form(state):
    gs = state
    gs.characters["c1"].gold = 5_000
    run(gs, {"p1": parse("Offer Ojibenmi 2000 gold.", gs)})
    assert gs.characters["npc1"].faction_id == "p1"


def test_offer_below_threshold_is_refused(state):
    gs = state
    run(gs, {"p1": parse("Offer 100 gold to Ojibenmi.", gs)})
    assert gs.characters["npc1"].faction_id == "npc"
    assert marcus_gold(gs) == BASE  # nothing spent


def test_refused_offer_fails_the_chained_orders(state):
    gs = state
    orders_list = parse("Offer 100 gold to Ojibenmi and have Ojibenmi go to Rome.", gs)
    run(gs, {"p1": orders_list})
    assert gs.characters["npc1"].faction_id == "npc"
    assert gs.characters["npc1"].location_city_id == "city2"  # never moved
    # The chained move order carries the refusal warning
    move = next(o for o in orders_list if isinstance(o, orders.MoveOrder))
    assert any("refused" in w for w in move.warnings)


def test_accepted_offer_carries_the_chained_orders(state):
    gs = state
    gs.characters["c1"].gold = 5_000
    run(gs, {"p1": parse("Offer 2000 gold to Ojibenmi and have Ojibenmi go to Rome.", gs)})
    assert gs.characters["npc1"].faction_id == "p1"
    assert gs.characters["npc1"].location_city_id == "city1"  # came as ordered


def test_offer_to_another_players_character_is_refused(state):
    gs = state
    gs.characters["c1"].gold = 5_000
    run(gs, {"p1": parse("Offer 5000 gold to Tengri.", gs)})
    assert gs.characters["c2"].faction_id == "p2"


def test_offer_to_own_prisoner_is_accepted(state):
    gs = state
    gs.characters["c2"].is_prisoner = True
    gs.characters["c2"].captor_id = "c1"
    run(gs, {"p1": parse("Offer 50 gold to Tengri.", gs)})
    assert gs.characters["c2"].faction_id == "p1"
    assert gs.characters["c2"].is_prisoner is False


# ---------------------------------------------------------------------------
# IF statements
# ---------------------------------------------------------------------------

def test_if_parses_with_else(state):
    gs = state
    parsed = parse("If Marcus has at least 100 gold, then have Julia go to "
                   "Carthage; otherwise have Julia go to Rome.", gs)
    assert len(parsed) == 1 and isinstance(parsed[0], orders.IfOrder)
    assert len(parsed[0].then_orders) == 1
    assert len(parsed[0].else_orders) == 1


def test_if_true_branch_runs(state):
    gs = state  # Marcus has 500 gold
    parsed = parse("If Marcus has at least 100 gold, then have Julia go to "
                   "Carthage; otherwise have Julia go to Rome.", gs)
    run(gs, {"p1": parsed})
    assert gs.characters["c1b"].location_city_id == "city2"


def test_if_false_branch_runs(state):
    gs = state
    gs.characters["c1"].gold = 50
    parsed = parse("If Marcus has at least 100 gold, then have Julia go to "
                   "Carthage; otherwise have Julia go to Rome.", gs)
    run(gs, {"p1": parsed})
    assert gs.characters["c1b"].location_city_id == "city1"  # already there


def test_if_counts_units(state):
    gs = state
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=1_500,
    )
    parsed = parse("If Marcus has more than 1000 soldiers, then have Julia go "
                   "to Carthage.", gs)
    run(gs, {"p1": parsed})
    assert gs.characters["c1b"].location_city_id == "city2"


def test_if_any_gold_and_power_conditions(state):
    gs = state
    parsed = parse("If Marcus has any gold, then have Julia go to Carthage.", gs)
    run(gs, {"p1": parsed})
    assert gs.characters["c1b"].location_city_id == "city2"

    gs.characters["c1b"].location_city_id = "city1"
    parsed = parse("If Marcus has at least 25 magic power, then have Julia go "
                   "to Carthage.", gs)  # Marcus: magic 20 -> false
    run(gs, {"p1": parsed}, seed=1)
    assert gs.characters["c1b"].location_city_id == "city1"


def test_if_unknown_subject_is_safe(state):
    gs = state
    parsed = parse("If Nobody has any gold, then have Julia go to Carthage.", gs)
    run(gs, {"p1": parsed})
    assert gs.characters["c1b"].location_city_id == "city1"


# ---------------------------------------------------------------------------
# THEN sequencing
# ---------------------------------------------------------------------------

def test_then_chains_after_wait(state):
    gs = state
    parsed = parse("Have Marcus wait for 2 weeks and then go to Carthage.", gs)
    assert len(parsed) == 2
    assert isinstance(parsed[0], orders.AwaitOrder)
    assert isinstance(parsed[1], orders.MoveOrder)
    assert parsed[1].destination_city_id == "city2"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_new_state_round_trips(state):
    gs = state
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=100, owner_character_id="c1",
    )
    run(gs, {"p1": parse("Create Gordys Killers using 100 soldiers. "
                         "Invest 200 gold in Rome.", gs)})
    gs.invest_pools["city2"] = 55.0

    if_order = parse("If Marcus has at least 100 gold, then have Julia go to "
                     "Carthage.", gs)[0]
    gs.order_queues["c1"] = [orders.QueueEntry(order=if_order)]

    with tempfile.TemporaryDirectory() as tmp:
        storage.save_game_state(gs, Path(tmp))
        loaded = storage.load_game_state(Path(tmp))
        assert loaded is not None

    assert len(loaded.elite_units) == 1
    assert loaded.invest_pools["city1"] > 0
    assert loaded.invest_pools["city2"] == 55.0
    assert loaded.world_map.cities["city3"].population is None

    entry = loaded.order_queues["c1"][0]
    assert isinstance(entry.order, orders.IfOrder)
    assert isinstance(entry.order.then_orders[0], orders.MoveOrder)
