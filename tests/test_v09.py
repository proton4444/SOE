"""
Tests for the v0.9 persistent order queue.

The queue is what makes AWAIT, REPEAT, HALT and STOP mean anything: before it,
they parsed and were rejected. These tests pin down the two properties the rest
of the engine depends on -- an unblocked character still resolves everything
they were given in the turn they were given it, and a blocked one carries the
remainder into later turns intact.
"""

import tempfile
from pathlib import Path

import pytest

from spoils_engine import config, engine, models, order_queue, orders, parser, storage


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
    gs.characters["c1b"] = models.Character(
        id="c1b", name="Julia", faction_id="p1", location_city_id="city2", gold=50,
    )
    gs.characters["c2"] = models.Character(
        id="c2", name="Tengri", faction_id="p2", location_city_id="city2",
        combat_skill=10, is_leader=True, gold=200,
    )
    return gs


def make_woodcutters(gs):
    """Give Marcus a forest and the workers to gather in it, so COLLECT bites."""
    gs.world_map.cities["city1"].terrain = {"forest"}
    gs.world_map.cities["city1"].resource_richness = {"wood": 1.0}
    gs.unit_stacks["workers"] = models.UnitStack(
        id="workers", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.WORKER, count=10)


def queue_events(log, player_id="p1"):
    return [e for e in log.get_player_events(player_id) if e.phase == "queue"]


def event_types(log, player_id="p1"):
    return [e.event_type for e in queue_events(log, player_id)]


# ---------------------------------------------------------------------------
# The queue must not slow down an unblocked character
# ---------------------------------------------------------------------------

def test_orders_with_nothing_in_front_still_run_immediately(two_faction_state):
    """
    rules.md: when the Gamemaster runs on a fixed schedule the computer executes
    orders rather than queueing them. Adding the queue must not turn every order
    into a turn of latency.
    """
    gs = two_faction_state
    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")

    engine.run_turn(gs, {"p1": [move]}, seed=1)

    assert gs.characters["c1"].location_city_id == "city2"
    assert not gs.order_queues


def test_several_orders_for_one_character_all_run_in_one_turn(two_faction_state):
    """One queue pass per turn releases the whole submission, not just its head."""
    gs = two_faction_state
    gs.characters["c1"].resources["stone"] = 100
    fortify = orders.FortifyOrder(player_id="p1", actor_id="c1", city_id="city1", percent=10)
    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")

    engine.run_turn(gs, {"p1": [fortify, move]}, seed=1)

    assert gs.world_map.cities["city1"].fortification_level == 10
    assert gs.characters["c1"].location_city_id == "city2"


# ---------------------------------------------------------------------------
# AWAIT
# ---------------------------------------------------------------------------

def test_wait_holds_the_orders_behind_it_then_releases_them(two_faction_state):
    """A timed wait defers the rest of the queue and then lets it through."""
    gs = two_faction_state
    wait = orders.AwaitOrder(player_id="p1", actor_id="c1",
                             duration_days=2 * config.DAYS_PER_TURN)
    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")

    _, log = engine.run_turn(gs, {"p1": [wait, move]}, seed=1)
    assert "await_started" in event_types(log)
    assert gs.characters["c1"].location_city_id == "city1"
    assert len(gs.order_queues["c1"]) == 2

    _, log = engine.run_turn(gs, {}, seed=1)
    assert "await_waiting" in event_types(log)
    assert gs.characters["c1"].location_city_id == "city1"

    _, log = engine.run_turn(gs, {}, seed=1)
    assert "await_finished" in event_types(log)
    assert gs.characters["c1"].location_city_id == "city2"
    assert not gs.order_queues


def test_a_wait_shorter_than_a_turn_still_costs_a_turn(two_faction_state):
    """
    The queue cannot hold work for less than a turn, so the rules' one-hour
    minimum rounds up. Documented in order_queue.turns_for_days.
    """
    assert order_queue.turns_for_days(1) == 1
    assert order_queue.turns_for_days(config.DAYS_PER_TURN) == 1
    assert order_queue.turns_for_days(config.DAYS_PER_TURN + 1) == 2
    assert order_queue.turns_for_days(0) == 0


def test_waiting_for_a_person_ends_when_they_arrive(two_faction_state):
    """rules.md: you may have someone wait for someone else to reach them."""
    gs = two_faction_state
    gs.characters["c1b"].location_city_id = "city2"

    wait = orders.AwaitOrder(player_id="p1", actor_id="c1", target_id="c1b",
                             duration_days=90)
    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")

    _, log = engine.run_turn(gs, {"p1": [wait, move]}, seed=1)
    assert "await_waiting" in event_types(log)
    assert gs.characters["c1"].location_city_id == "city1"

    # Julia walks to Rome; the wait ends and Marcus resumes.
    gs.characters["c1b"].location_city_id = "city1"
    _, log = engine.run_turn(gs, {}, seed=1)

    assert "await_met" in event_types(log)
    assert gs.characters["c1"].location_city_id == "city2"


def test_waiting_for_a_person_gives_up_at_the_deadline(two_faction_state):
    """The duration on a WAIT FOR is the deadline it stops waiting at."""
    gs = two_faction_state
    wait = orders.AwaitOrder(player_id="p1", actor_id="c1", target_id="c1b",
                             duration_days=config.DAYS_PER_TURN)
    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")

    engine.run_turn(gs, {"p1": [wait, move]}, seed=1)
    assert gs.characters["c1"].location_city_id == "city1"

    _, log = engine.run_turn(gs, {}, seed=1)

    assert "await_expired" in event_types(log)
    assert gs.characters["c1"].location_city_id == "city2"


# ---------------------------------------------------------------------------
# REPEAT
# ---------------------------------------------------------------------------

def test_repeat_runs_its_body_once_per_turn(two_faction_state):
    """A finite loop runs exactly the number of passes it was given."""
    gs = two_faction_state
    make_woodcutters(gs)
    repeat = orders.RepeatOrder(player_id="p1", actor_id="c1", times=3)
    collect = orders.CollectOrder(player_id="p1", actor_id="c1",
                                  resource_type="wood", duration_days=7)

    engine.run_turn(gs, {"p1": [repeat, collect]}, seed=1)
    after_first = gs.characters["c1"].resources.get("wood", 0)
    assert after_first > 0

    engine.run_turn(gs, {}, seed=1)
    after_second = gs.characters["c1"].resources.get("wood", 0)
    assert after_second > after_first

    _, log = engine.run_turn(gs, {}, seed=1)
    assert gs.characters["c1"].resources.get("wood", 0) > after_second
    assert "repeat_finished" in event_types(log)
    assert not gs.order_queues


def test_a_loop_with_no_count_runs_until_halted(two_faction_state):
    """rules.md: a repeat loop with no count may be cancelled only by HALT/STOP."""
    gs = two_faction_state
    make_woodcutters(gs)
    repeat = orders.RepeatOrder(player_id="p1", actor_id="c1", times=0)
    collect = orders.CollectOrder(player_id="p1", actor_id="c1",
                                  resource_type="wood", duration_days=7)

    engine.run_turn(gs, {"p1": [repeat, collect]}, seed=1)
    for _ in range(5):
        engine.run_turn(gs, {}, seed=1)
    assert gs.order_queues["c1"]

    halt = orders.HaltOrder(player_id="p1", actor_id="c1")
    _, log = engine.run_turn(gs, {"p1": [halt]}, seed=1)

    assert "halt" in event_types(log)
    assert not gs.order_queues


def test_orders_queued_after_a_running_loop_stay_out_of_reach(two_faction_state):
    """
    rules.md is explicit that a character in an unbounded loop never gets to the
    orders written after it, so a later submission must not jump the loop.
    """
    gs = two_faction_state
    make_woodcutters(gs)
    repeat = orders.RepeatOrder(player_id="p1", actor_id="c1", times=0)
    collect = orders.CollectOrder(player_id="p1", actor_id="c1",
                                  resource_type="wood", duration_days=7)
    engine.run_turn(gs, {"p1": [repeat, collect]}, seed=1)

    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    engine.run_turn(gs, {"p1": [move]}, seed=1)
    engine.run_turn(gs, {}, seed=1)

    assert gs.characters["c1"].location_city_id == "city1"


def test_a_nested_repeat_is_folded_into_the_outer_loop(two_faction_state):
    """rules.md: nested orders run in sequence as part of the outermost loop."""
    gs = two_faction_state
    outer = orders.RepeatOrder(player_id="p1", actor_id="c1", times=2)
    inner = orders.RepeatOrder(player_id="p1", actor_id="c1", times=2)
    tax = orders.TaxOrder(player_id="p1", actor_id="c1", city_id="city1")

    engine.run_turn(gs, {"p1": [outer, inner, tax]}, seed=1)

    assert inner.warnings
    assert not outer.warnings
    assert len(gs.order_queues["c1"]) == 2  # the tax, and the loop marker


def test_a_repeat_with_nothing_to_repeat_says_so(two_faction_state):
    gs = two_faction_state
    repeat = orders.RepeatOrder(player_id="p1", actor_id="c1", times=3)

    _, log = engine.run_turn(gs, {"p1": [repeat]}, seed=1)

    assert repeat.warnings
    assert "repeat_empty" in event_types(log)


# ---------------------------------------------------------------------------
# HALT and STOP
# ---------------------------------------------------------------------------

def test_halt_clears_the_backlog(two_faction_state):
    gs = two_faction_state
    wait = orders.AwaitOrder(player_id="p1", actor_id="c1",
                             duration_days=5 * config.DAYS_PER_TURN)
    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    engine.run_turn(gs, {"p1": [wait, move]}, seed=1)

    halt = orders.HaltOrder(player_id="p1", actor_id="c1", immediate=True)
    engine.run_turn(gs, {"p1": [halt]}, seed=1)

    assert not gs.order_queues
    assert gs.characters["c1"].location_city_id == "city1"


def test_a_plain_halt_leaves_a_wait_already_under_way_standing(two_faction_state):
    """
    rules.md: without "immediately", the order already in progress finishes and
    only the queue behind it is cancelled.
    """
    gs = two_faction_state
    wait = orders.AwaitOrder(player_id="p1", actor_id="c1",
                             duration_days=2 * config.DAYS_PER_TURN)
    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    engine.run_turn(gs, {"p1": [wait, move]}, seed=1)

    halt = orders.HaltOrder(player_id="p1", actor_id="c1", immediate=False)
    engine.run_turn(gs, {"p1": [halt]}, seed=1)

    assert len(gs.order_queues["c1"]) == 1  # the wait survived, the move did not

    engine.run_turn(gs, {}, seed=1)
    assert gs.characters["c1"].location_city_id == "city1"
    assert not gs.order_queues


def test_stop_waits_its_turn_and_then_clears_what_is_behind_it(two_faction_state):
    """
    A planned STOP is queued in sequence, so the orders in front of it still run
    and only the ones behind it are cancelled.
    """
    gs = two_faction_state
    gs.characters["c1"].resources["stone"] = 100
    fortify = orders.FortifyOrder(player_id="p1", actor_id="c1", city_id="city1", percent=10)
    stop = orders.StopOrder(player_id="p1", actor_id="c1")
    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")

    _, log = engine.run_turn(gs, {"p1": [fortify, stop, move]}, seed=1)

    assert gs.world_map.cities["city1"].fortification_level == 10  # ran, it was in front
    assert gs.characters["c1"].location_city_id == "city1"  # cancelled, it was behind
    assert "stop" in event_types(log)
    assert not gs.order_queues


# ---------------------------------------------------------------------------
# Ownership, death and validation
# ---------------------------------------------------------------------------

def test_you_cannot_queue_orders_for_another_players_character(two_faction_state):
    gs = two_faction_state
    move = orders.MoveOrder(player_id="p1", actor_id="c2", destination_city_id="city1")

    engine.run_turn(gs, {"p1": [move]}, seed=1)

    assert any("belong" in w for w in move.warnings)
    assert "c2" not in gs.order_queues


def test_you_cannot_halt_another_players_character(two_faction_state):
    gs = two_faction_state
    wait = orders.AwaitOrder(player_id="p2", actor_id="c2",
                             duration_days=3 * config.DAYS_PER_TURN)
    engine.run_turn(gs, {"p2": [wait]}, seed=1)
    assert gs.order_queues["c2"]

    halt = orders.HaltOrder(player_id="p1", actor_id="c2")
    engine.run_turn(gs, {"p1": [halt]}, seed=1)

    assert halt.warnings
    assert gs.order_queues["c2"]


def test_a_dead_characters_queue_is_dropped(two_faction_state):
    gs = two_faction_state
    wait = orders.AwaitOrder(player_id="p1", actor_id="c1",
                             duration_days=3 * config.DAYS_PER_TURN)
    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    engine.run_turn(gs, {"p1": [wait, move]}, seed=1)

    gs.characters["c1"].is_dead = True
    _, log = engine.run_turn(gs, {}, seed=1)

    assert "queue_lost" in event_types(log)
    assert not gs.order_queues


def test_a_queued_order_is_validated_when_it_executes_not_when_it_was_written(
    two_faction_state
):
    """
    An order that waits three turns must be judged against the world it lands
    in. Here its destination stops existing while it sits in the queue.
    """
    gs = two_faction_state
    wait = orders.AwaitOrder(player_id="p1", actor_id="c1",
                             duration_days=config.DAYS_PER_TURN)
    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    engine.run_turn(gs, {"p1": [wait, move]}, seed=1)

    assert not move.warnings
    del gs.world_map.cities["city2"]
    engine.run_turn(gs, {}, seed=1)

    assert any("Destination" in w for w in move.warnings)


def test_an_unparseable_order_is_rejected_now_not_three_turns_from_now(
    two_faction_state
):
    """An order that already failed parsing bypasses the queue entirely."""
    gs = two_faction_state
    wait = orders.AwaitOrder(player_id="p1", actor_id="c1",
                             duration_days=3 * config.DAYS_PER_TURN)
    engine.run_turn(gs, {"p1": [wait]}, seed=1)

    broken = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="nowhere")
    broken.warnings.append("Could not parse order")
    engine.run_turn(gs, {"p1": [broken]}, seed=1)

    # It was reported at once rather than joining the queue behind the wait.
    assert len(gs.order_queues["c1"]) == 1


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_the_queue_survives_a_save_and_load(two_faction_state):
    """
    Every turn is a save/load cycle in a PBEM game, so a queue that does not
    round-trip is a queue that silently empties itself between turns.
    """
    gs = two_faction_state
    make_woodcutters(gs)
    wait = orders.AwaitOrder(player_id="p1", actor_id="c1",
                             duration_days=2 * config.DAYS_PER_TURN)
    repeat = orders.RepeatOrder(player_id="p1", actor_id="c1", times=2)
    collect = orders.CollectOrder(player_id="p1", actor_id="c1",
                                  resource_type="wood", duration_days=7)
    engine.run_turn(gs, {"p1": [wait, repeat, collect]}, seed=1)

    with tempfile.TemporaryDirectory() as tmp:
        storage.save_game_state(gs, Path(tmp))
        reloaded = storage.load_game_state(Path(tmp))

    before = gs.order_queues["c1"]
    after = reloaded.order_queues["c1"]

    assert len(after) == len(before)
    assert [type(e.order) for e in after] == [type(e.order) for e in before]
    assert after[0].release_turn == before[0].release_turn
    marker = next(e for e in after if isinstance(e.order, orders.RepeatOrder))
    assert marker.repeat_remaining == 1
    assert [type(e.order) for e in marker.block] == [orders.CollectOrder]


def test_a_reloaded_queue_keeps_running(two_faction_state):
    """The round-trip has to preserve behaviour, not just shape."""
    gs = two_faction_state
    wait = orders.AwaitOrder(player_id="p1", actor_id="c1",
                             duration_days=2 * config.DAYS_PER_TURN)
    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    engine.run_turn(gs, {"p1": [wait, move]}, seed=1)

    with tempfile.TemporaryDirectory() as tmp:
        storage.save_game_state(gs, Path(tmp))
        gs = storage.load_game_state(Path(tmp))

    engine.run_turn(gs, {}, seed=1)
    assert gs.characters["c1"].location_city_id == "city1"

    engine.run_turn(gs, {}, seed=1)
    assert gs.characters["c1"].location_city_id == "city2"


def test_a_save_without_queues_still_loads(two_faction_state):
    """Pre-v0.9 saves have no order_queues key at all."""
    with tempfile.TemporaryDirectory() as tmp:
        storage.save_game_state(two_faction_state, Path(tmp))
        state_file = Path(tmp) / "state.json"
        import json
        data = json.loads(state_file.read_text(encoding="utf-8"))
        del data["order_queues"]
        state_file.write_text(json.dumps(data), encoding="utf-8")

        reloaded = storage.load_game_state(Path(tmp))

    assert reloaded.order_queues == {}


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_wait_for_a_duration(two_faction_state):
    parsed = parser.parse_orders("Have Marcus wait for 2 weeks.", two_faction_state, "p1")

    assert len(parsed) == 1
    assert isinstance(parsed[0], orders.AwaitOrder)
    assert parsed[0].actor_id == "c1"
    assert parsed[0].duration_days == 14


def test_parse_wait_names_the_right_character(two_faction_state):
    """"Have <name> wait" used to bind the wait to the faction leader."""
    parsed = parser.parse_orders("Have Julia await 3 days.", two_faction_state, "p1")

    assert parsed[0].actor_id == "c1b"
    assert parsed[0].duration_days == 3


def test_parse_wait_for_a_person(two_faction_state):
    parsed = parser.parse_orders("Have Marcus wait for Julia.", two_faction_state, "p1")

    assert isinstance(parsed[0], orders.AwaitOrder)
    assert parsed[0].target_id == "c1b"


def test_parse_wait_until_a_turn(two_faction_state):
    two_faction_state.turn_number = 4
    parsed = parser.parse_orders("Wait until turn 7.", two_faction_state, "p1")

    assert parsed[0].duration_days == 3 * config.DAYS_PER_TURN


def test_parse_time_units_do_not_mix(two_faction_state):
    """rules.md fixes a month at 30 days and forbids combining units."""
    assert parser.parse_duration_days("wait 1 month") == 30
    assert parser.parse_duration_days("wait 90 minutes") == 1
    assert parser.parse_duration_days("wait 27 hours") == 2
    assert parser.parse_duration_days("wait for julia") is None


def test_parse_repeatedly_wraps_the_command_it_governs(two_faction_state):
    parsed = parser.parse_orders(
        "Have Marcus repeatedly tax 5 times.", two_faction_state, "p1"
    )

    assert isinstance(parsed[0], orders.RepeatOrder)
    assert parsed[0].times == 5
    assert parsed[0].actor_id == "c1"
    assert isinstance(parsed[1], orders.TaxOrder)
    assert parsed[1].actor_id == "c1"


def test_parse_repeatedly_without_a_count_is_unbounded(two_faction_state):
    parsed = parser.parse_orders("Have Marcus repeatedly tax.", two_faction_state, "p1")

    assert isinstance(parsed[0], orders.RepeatOrder)
    assert parsed[0].times == 0


def test_parse_halt_and_stop(two_faction_state):
    halt = parser.parse_orders("Have Marcus immediately halt.", two_faction_state, "p1")[0]
    stop = parser.parse_orders("Have Julia stop.", two_faction_state, "p1")[0]

    assert isinstance(halt, orders.HaltOrder)
    assert halt.actor_id == "c1"
    assert halt.immediate

    assert isinstance(stop, orders.StopOrder)
    assert stop.actor_id == "c1b"
    assert not stop.immediate


def test_parsed_repeatedly_runs_end_to_end(two_faction_state):
    """The parser's output has to drive the queue, not just look right."""
    gs = two_faction_state
    parsed = parser.parse_orders("Have Marcus repeatedly tax 2 times.", gs, "p1")

    engine.run_turn(gs, {"p1": parsed}, seed=1)
    assert gs.order_queues["c1"]

    _, log = engine.run_turn(gs, {}, seed=1)
    assert "repeat_finished" in event_types(log)
