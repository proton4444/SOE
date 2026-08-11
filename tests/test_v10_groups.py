"""
Tests for the v1.0 group model.

the design builds the command language on groups: an order given to a character
applies to everyone assigned to them, and a character given a direct order
becomes independent. Before this, characters were loose atoms -- ASSIGN moved
counts between location-scoped pools and UNLOAD only wrote a log line.
"""

import tempfile
from pathlib import Path

import pytest

from soe import config, engine, groups, models, orders, parser, storage


@pytest.fixture
def warband():
    """A leader with two subordinates in Rome, and a rival in Carthage."""
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
        combat_skill=15, is_leader=True, gold=1000,
    )
    gs.characters["c2"] = models.Character(
        id="c2", name="Julia", faction_id="p1", location_city_id="city1",
        combat_skill=20, gold=100, group_leader_id="c1",
    )
    gs.characters["c3"] = models.Character(
        id="c3", name="Gaius", faction_id="p1", location_city_id="city1",
        combat_skill=10, gold=50, group_leader_id="c2",
    )
    gs.characters["e1"] = models.Character(
        id="e1", name="Tengri", faction_id="p2", location_city_id="city2",
        combat_skill=25, is_leader=True, gold=500,
    )
    return gs


def group_events(log, player_id="p1"):
    return [e.event_type for e in log.get_player_events(player_id) if e.phase == "groups"]


# ---------------------------------------------------------------------------
# Reading the tree
# ---------------------------------------------------------------------------

def test_the_chain_of_command_is_transitive(warband):
    """Gaius answers to Julia, who answers to Marcus."""
    gs = warband

    assert groups.leader_of(gs.characters["c3"], gs).id == "c1"
    assert groups.leader_of(gs.characters["c1"], gs).id == "c1"
    assert [c.id for c in groups.group_members("c1", gs)] == ["c2", "c3"]
    assert [c.id for c in groups.group_members("c2", gs)] == ["c3"]
    assert groups.group_members("c3", gs) == []


def test_a_corrupt_cycle_does_not_hang_the_turn(warband):
    """
    A save with a cycle in the chain of command must not spin forever. attach()
    refuses to build one, so this can only arrive from a hand-edited file.
    """
    gs = warband
    gs.characters["c1"].group_leader_id = "c3"  # c1 -> c3 -> c2 -> c1

    assert groups.leader_of(gs.characters["c1"], gs) is not None
    assert len(groups.group_members("c1", gs)) < 10


def test_you_cannot_join_your_own_subordinate(warband):
    """That would make the chain of command a circle."""
    gs = warband
    refusal = groups.attach(gs.characters["c1"], gs.characters["c3"], gs)

    assert refusal
    assert gs.characters["c1"].group_leader_id == ""


# ---------------------------------------------------------------------------
# A group travels together
# ---------------------------------------------------------------------------

def test_a_group_moves_with_its_leader(warband):
    """Design: order the leader to go, and the whole group goes."""
    gs = warband
    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")

    engine.run_turn(gs, {"p1": [move]}, seed=1)

    assert gs.characters["c1"].location_city_id == "city2"
    assert gs.characters["c2"].location_city_id == "city2"
    assert gs.characters["c3"].location_city_id == "city2"  # via Julia


def test_units_march_with_the_character_they_belong_to(warband):
    """Recruits belong to whoever raised them, so they are not left behind."""
    gs = warband
    recruit = orders.RecruitOrder(player_id="p1", actor_id="c1", city_id="city1",
                                  unit_type="soldier", count=50)
    engine.run_turn(gs, {"p1": [recruit]}, seed=1)

    stack = next(s for s in gs.unit_stacks.values() if s.count == 50)
    assert stack.owner_character_id == "c1"

    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    engine.run_turn(gs, {"p1": [move]}, seed=1)

    assert stack.location_city_id == "city2"


def test_a_member_left_elsewhere_does_not_teleport_to_the_leader(warband):
    """Only the people standing with the leader travel with them."""
    gs = warband
    gs.characters["c3"].location_city_id = "city2"
    gs.characters["c3"].group_leader_id = "c1"

    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    engine.run_turn(gs, {"p1": [move]}, seed=1)

    assert gs.characters["c2"].location_city_id == "city2"  # came along
    assert gs.characters["c3"].location_city_id == "city2"  # was already there


def test_moving_a_subordinate_does_not_drag_their_former_leader(warband):
    """
    An order to a subordinate detaches them first, so the group they are
    leaving stays put.
    """
    gs = warband
    parsed = parser.parse_orders("Have Julia go to Carthage.", gs, "p1")

    engine.run_turn(gs, {"p1": parsed}, seed=1)

    assert gs.characters["c1"].location_city_id == "city1"  # Marcus stayed
    assert gs.characters["c2"].location_city_id == "city2"
    assert gs.characters["c3"].location_city_id == "city2"  # Gaius is Julia's


# ---------------------------------------------------------------------------
# Becoming a leader
# ---------------------------------------------------------------------------

def test_a_direct_order_makes_a_character_a_group_leader(warband):
    """
    Design: "Whenever you use the HAVE command, the character named in the
    command will automatically become a group leader if he was not already one."
    """
    gs = warband
    parsed = parser.parse_orders("Have Julia tax.", gs, "p1")

    _, log = engine.run_turn(gs, {"p1": parsed}, seed=1)

    assert gs.characters["c2"].group_leader_id == ""
    assert "became_leader" in group_events(log)


def test_an_order_that_names_nobody_leaves_the_group_alone(warband):
    """An order with no HAVE goes to the leader and detaches nobody."""
    gs = warband
    parsed = parser.parse_orders("Tax.", gs, "p1")

    engine.run_turn(gs, {"p1": parsed}, seed=1)

    assert gs.characters["c2"].group_leader_id == "c1"
    assert gs.characters["c3"].group_leader_id == "c2"


def test_unload_makes_a_character_independent_without_ordering_them_about(warband):
    """
    Design: UNLOAD is for when "you simply want a character to become a group
    leader and not do anything else". It used to only write a log line.
    """
    gs = warband
    unload = orders.UnloadOrder(player_id="p1", actor_id="c1",
                                target_ids=["c2"], target_names=["Julia"])

    engine.run_turn(gs, {"p1": [unload]}, seed=1)

    assert gs.characters["c2"].group_leader_id == ""
    assert gs.characters["c3"].group_leader_id == "c2"  # Gaius stays hers

    move = orders.MoveOrder(player_id="p1", actor_id="c1", destination_city_id="city2")
    engine.run_turn(gs, {"p1": [move]}, seed=1)
    assert gs.characters["c2"].location_city_id == "city1"  # no longer follows


# ---------------------------------------------------------------------------
# JOIN and ASSIGN
# ---------------------------------------------------------------------------

def test_join_puts_a_character_into_another_group(warband):
    gs = warband
    groups.detach(gs.characters["c2"])
    join = orders.JoinOrder(player_id="p1", actor_id="c2", target_id="c1",
                            target_name="Marcus")

    _, log = engine.run_turn(gs, {"p1": [join]}, seed=1)

    assert gs.characters["c2"].group_leader_id == "c1"
    assert "join" in group_events(log)


def test_join_brings_your_own_subordinates_with_you(warband):
    """Design: an assigned character keeps whoever was assigned to them."""
    gs = warband
    groups.detach(gs.characters["c2"])
    join = orders.JoinOrder(player_id="p1", actor_id="c2", target_id="c1",
                            target_name="Marcus")
    engine.run_turn(gs, {"p1": [join]}, seed=1)

    assert [c.id for c in groups.group_members("c1", gs)] == ["c2", "c3"]


def test_join_fails_across_locations(warband):
    gs = warband
    gs.characters["c2"].location_city_id = "city2"
    groups.detach(gs.characters["c2"])
    join = orders.JoinOrder(player_id="p1", actor_id="c2", target_id="c1",
                            target_name="Marcus")

    _, log = engine.run_turn(gs, {"p1": [join]}, seed=1)

    assert gs.characters["c2"].group_leader_id == ""
    assert "join_failed" in group_events(log)


def test_assign_moves_a_named_character_into_a_group(warband):
    """ASSIGN is JOIN given from the other end."""
    gs = warband
    assign = orders.AssignOrder(player_id="p1", donor_id="c1", recipient_id="c1",
                                character_ids=["c3"], character_names=["Gaius"])

    engine.run_turn(gs, {"p1": [assign]}, seed=1)

    assert gs.characters["c3"].group_leader_id == "c1"  # was Julia's


def test_assign_refuses_to_make_a_loop_in_the_chain_of_command(warband):
    """Julia cannot be assigned to Gaius, who already answers to her."""
    gs = warband
    groups.detach(gs.characters["c2"])
    assign = orders.AssignOrder(player_id="p1", donor_id="c1", recipient_id="c3",
                                character_ids=["c2"], character_names=["Julia"])

    engine.run_turn(gs, {"p1": [assign]}, seed=1)

    assert gs.characters["c2"].group_leader_id == ""


def test_a_character_cannot_be_given_to_another_faction(warband):
    """Units may cross faction lines; people may not. That is CAPTURE."""
    gs = warband
    gs.characters["e1"].location_city_id = "city1"
    assign = orders.AssignOrder(player_id="p1", donor_id="c1", recipient_id="e1",
                                character_ids=["c2"], character_names=["Julia"])

    engine.run_turn(gs, {"p1": [assign]}, seed=1)

    assert gs.characters["c2"].group_leader_id == "c1"


def test_assigned_units_become_the_recipients_and_travel_with_them(warband):
    gs = warband
    gs.unit_stacks["pool"] = models.UnitStack(
        id="pool", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=100)

    assign = orders.AssignOrder(player_id="p1", donor_id="c1", recipient_id="c2",
                                unit_type="SOLDIER", unit_count=40)
    engine.run_turn(gs, {"p1": [assign]}, seed=1)

    julias = [s for s in gs.unit_stacks.values() if s.owner_character_id == "c2"]
    assert sum(s.count for s in julias) == 40

    parsed = parser.parse_orders("Have Julia go to Carthage.", gs, "p1")
    engine.run_turn(gs, {"p1": parsed}, seed=1)

    assert all(s.location_city_id == "city2" for s in julias)
    assert gs.unit_stacks["pool"].location_city_id == "city1"  # the rest stayed


# ---------------------------------------------------------------------------
# Group-wide effects
# ---------------------------------------------------------------------------

def test_lurking_covers_the_whole_group(warband):
    """
    Design: "The LURK command should only be used on the leader of a group.
    Everyone in the group will automatically be included."
    """
    gs = warband
    lurk = orders.LurkOrder(player_id="p1", actor_id="c1", set_lurking=True)

    engine.run_turn(gs, {"p1": [lurk]}, seed=1)

    assert gs.characters["c1"].is_lurking
    assert gs.characters["c2"].is_lurking
    assert gs.characters["c3"].is_lurking


def test_someone_who_breaks_away_stops_lurking_with_the_group(warband):
    """
    Design: members who "break off to start their own group ... will not
    continue to lurk unless their new leader is explicitly given a LURK order."
    """
    gs = warband
    engine.run_turn(gs, {"p1": [orders.LurkOrder(player_id="p1", actor_id="c1",
                                                 set_lurking=True)]}, seed=1)
    engine.run_turn(gs, {"p1": [orders.LurkOrder(player_id="p1", actor_id="c1",
                                                 set_lurking=False)]}, seed=1)

    assert not gs.characters["c2"].is_lurking


def test_group_soldier_count_includes_subordinates_units(warband):
    gs = warband
    gs.unit_stacks["s1"] = models.UnitStack(
        id="s1", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=30, owner_character_id="c1")
    gs.unit_stacks["s2"] = models.UnitStack(
        id="s2", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=20, owner_character_id="c3")

    total = groups.group_soldier_count(gs.characters["c1"], gs,
                                       models.UnitType.SOLDIER)
    assert total == 50


# ---------------------------------------------------------------------------
# SUPPORT
# ---------------------------------------------------------------------------

def test_a_supporter_fights_on_the_attackers_side(warband):
    """
    Design: the supporter joins "as if they had given the same ATTACK order
    at exactly the same time".
    """
    gs = warband
    gs.factions["p3"] = models.Faction(id="p3", name="Gauls")
    gs.characters["a1"] = models.Character(
        id="a1", name="Vercingetorix", faction_id="p3", location_city_id="city2",
        combat_skill=30, is_leader=True)
    gs.unit_stacks["ally"] = models.UnitStack(
        id="ally", faction_id="p3", location_city_id="city2",
        unit_type=models.UnitType.SOLDIER, count=80, owner_character_id="a1")
    gs.unit_stacks["foe"] = models.UnitStack(
        id="foe", faction_id="p2", location_city_id="city2",
        unit_type=models.UnitType.SOLDIER, count=60, owner_character_id="e1")
    gs.characters["c1"].location_city_id = "city2"

    support = orders.SupportOrder(player_id="p3", actor_id="a1",
                                  target_ids=["c1"], target_names=["Marcus"],
                                  duration_days=30)
    engine.run_turn(gs, {"p3": [support]}, seed=1)
    assert gs.characters["a1"].supporting_id == "c1"

    assert engine.supporting_side(gs.characters["c1"], "city2", gs) == ["p3"]


def test_support_lapses_when_its_time_runs_out(warband):
    gs = warband
    gs.characters["e1"].location_city_id = "city1"
    support = orders.SupportOrder(player_id="p1", actor_id="c1",
                                  target_ids=["e1"], target_names=["Tengri"],
                                  duration_days=config.DAYS_PER_TURN)

    engine.run_turn(gs, {"p1": [support]}, seed=1)
    assert gs.characters["c1"].supporting_id == "e1"

    engine.run_turn(gs, {}, seed=1)
    assert gs.characters["c1"].supporting_id == ""


def test_support_without_a_deadline_stands(warband):
    gs = warband
    gs.characters["e1"].location_city_id = "city1"
    support = orders.SupportOrder(player_id="p1", actor_id="c1",
                                  target_ids=["e1"], target_names=["Tengri"])

    engine.run_turn(gs, {"p1": [support]}, seed=1)
    for _ in range(4):
        engine.run_turn(gs, {}, seed=1)

    assert gs.characters["c1"].supporting_id == "e1"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_join(warband):
    parsed = parser.parse_orders("Have Julia join Marcus.", warband, "p1")

    assert isinstance(parsed[0], orders.JoinOrder)
    assert parsed[0].actor_id == "c2"
    assert parsed[0].target_id == "c1"


def test_parse_come_is_go(warband):
    """Design: "COME -- see the GO command"."""
    parsed = parser.parse_orders("Have Julia come to Carthage.", warband, "p1")

    assert isinstance(parsed[0], orders.MoveOrder)
    assert parsed[0].destination_city_id == "city2"


def test_parse_assign_a_named_character(warband):
    parsed = parser.parse_orders("Have Marcus assign Gaius to Julia.", warband, "p1")

    assert isinstance(parsed[0], orders.AssignOrder)
    assert parsed[0].donor_id == "c1"
    assert parsed[0].recipient_id == "c2"
    assert parsed[0].character_ids == ["c3"]


def test_parse_assign_units_still_works(warband):
    """The named-character form must not swallow the quantity form."""
    parsed = parser.parse_orders("Have Marcus give 100 soldiers to Julia.", warband, "p1")

    assert parsed[0].unit_count == 100
    assert parsed[0].unit_type == "SOLDIER"
    assert parsed[0].character_ids == []


def test_parse_support_with_a_duration(warband):
    parsed = parser.parse_orders("Have Marcus support Tengri for 2 weeks.", warband, "p1")

    assert isinstance(parsed[0], orders.SupportOrder)
    assert parsed[0].target_ids == ["e1"]
    assert parsed[0].duration_days == 14


def test_an_explicitly_named_actor_is_recorded(warband):
    """The engine needs to know a HAVE was used to apply the leadership rule."""
    named = parser.parse_orders("Have Julia tax.", warband, "p1")[0]
    implicit = parser.parse_orders("Tax.", warband, "p1")[0]

    assert named.explicit_actor
    assert not implicit.explicit_actor


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_group_membership_and_unit_ownership_survive_a_save(warband):
    gs = warband
    gs.unit_stacks["s1"] = models.UnitStack(
        id="s1", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=30, owner_character_id="c2")
    gs.characters["c1"].supporting_id = "e1"
    gs.characters["c1"].support_until_turn = 9

    with tempfile.TemporaryDirectory() as tmp:
        storage.save_game_state(gs, Path(tmp))
        reloaded = storage.load_game_state(Path(tmp))

    assert reloaded.characters["c2"].group_leader_id == "c1"
    assert reloaded.characters["c3"].group_leader_id == "c2"
    assert reloaded.unit_stacks["s1"].owner_character_id == "c2"
    assert reloaded.characters["c1"].supporting_id == "e1"
    assert reloaded.characters["c1"].support_until_turn == 9


def test_a_pre_v10_save_loads_with_everyone_independent(warband):
    """Old saves have no group fields; nobody should end up with a phantom leader."""
    import json

    with tempfile.TemporaryDirectory() as tmp:
        storage.save_game_state(warband, Path(tmp))
        state_file = Path(tmp) / "state.json"
        data = json.loads(state_file.read_text(encoding="utf-8"))
        for char in data["characters"].values():
            char.pop("group_leader_id", None)
            char.pop("supporting_id", None)
        for stack in data["unit_stacks"].values():
            stack.pop("owner_character_id", None)
        state_file.write_text(json.dumps(data), encoding="utf-8")

        reloaded = storage.load_game_state(Path(tmp))

    assert all(c.group_leader_id == "" for c in reloaded.characters.values())
