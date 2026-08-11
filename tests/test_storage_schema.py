"""
Schema-completeness guard for the root GameState.

Child entities are rebuilt generically by ``rebuild_dataclass``, but the root
``GameState`` is reconstructed by hand in ``decode_game_state``. A field added
to the model but not to that constructor call serialises correctly and then
silently resets to its default on load, so the campaign loses it at the next
turn boundary with nothing in the logs.

These tests are mechanical on purpose: they enumerate the dataclass rather than
naming fields, so adding a field to GameState fails them until the field is
given both round-trip coverage and a decoder line.
"""

import dataclasses

from soe import config, storage
from soe.models import (
    Character,
    City,
    CreatureType,
    EliteUnit,
    Faction,
    GameState,
    ItemType,
    MagicalItem,
    PopulationBand,
    Road,
    RoadQuality,
    Ship,
    ShipType,
    SummonedCreature,
    UnitStack,
    UnitType,
    WorldMap,
)
from soe.orders import QueueEntry, RecruitOrder


def _state_with_every_field_set() -> GameState:
    """A GameState in which no root field is left at its default value."""
    return GameState(
        turn_number=7,
        game_time_hours=7 * config.HOURS_PER_TURN + 3,
        world_map=WorldMap(
            cities={
                "c1": City(id="c1", name="Highfell", population_band=PopulationBand.LARGE),
                "c2": City(id="c2", name="Gullhaven", population_band=PopulationBand.SMALL),
            },
            roads={
                "r1": Road(
                    id="r1",
                    from_city_id="c1",
                    to_city_id="c2",
                    quality=RoadQuality.GOOD,
                )
            },
        ),
        factions={"f1": Faction(id="f1", name="Ravens")},
        characters={
            "ch1": Character(
                id="ch1", name="Vela", faction_id="f1", location_city_id="c1"
            )
        },
        unit_stacks={
            "u1": UnitStack(
                id="u1",
                faction_id="f1",
                location_city_id="c1",
                unit_type=UnitType.SOLDIER,
                count=20,
            )
        },
        ships={
            "s1": Ship(
                id="s1",
                faction_id="f1",
                location_city_id="c1",
                ship_type=ShipType.GALLEY,
            )
        },
        summoned_creatures={
            "sc1": SummonedCreature(
                id="sc1", summoner_id="ch1", creature_type=CreatureType.GRIFFIN, count=2
            )
        },
        magical_items={
            "mi1": MagicalItem(id="mi1", name="Seeing Orb", item_type=ItemType.ORB)
        },
        elite_units={"e1": EliteUnit(id="e1", name="Raven Guard", faction_id="f1")},
        tax_pools={"f1": 12.5},
        invest_pools={"f1": 3.25},
        location_blessings={"c1": 2},
        location_curses={"c2": 1},
        posted_messages={"c1": "The gate stands open."},
        order_queues={
            "ch1": [
                QueueEntry(
                    order=RecruitOrder(
                        player_id="f1",
                        warnings=[],
                        actor_id="ch1",
                        city_id="c1",
                        unit_type="soldiers",
                        count=5,
                    ),
                    order_class="RecruitOrder",
                    release_turn=9,
                    release_hour=4,
                    check_hour=2,
                    repeat_remaining=3,
                )
            ]
        },
    )


def _fields_left_at_default(state: GameState) -> list[str]:
    defaults = GameState()
    return [
        field.name
        for field in dataclasses.fields(GameState)
        if getattr(state, field.name) == getattr(defaults, field.name)
    ]


def test_the_round_trip_fixture_covers_every_root_field():
    """Adding a GameState field without covering it here fails loudly."""
    uncovered = _fields_left_at_default(_state_with_every_field_set())
    assert not uncovered, (
        "these GameState fields are still at their default in the round-trip "
        f"fixture, so the test below cannot detect losing them: {uncovered}. "
        "Give each one a non-default value in _state_with_every_field_set()."
    )


def test_every_root_field_survives_a_save_load_round_trip(tmp_path):
    """No root field may silently reset to its default when a game is loaded."""
    storage.save_game_state(_state_with_every_field_set(), tmp_path)
    loaded = storage.load_game_state(tmp_path)

    assert loaded is not None
    reset = _fields_left_at_default(loaded)
    assert not reset, (
        f"these GameState fields reset to their default on load: {reset}. "
        "decode_game_state builds the root by hand -- every field needs a line "
        "there, or the campaign loses it at the next save."
    )


def test_root_field_values_survive_intact_not_merely_non_default(tmp_path):
    """Guard against a field that reloads as something other than what it was."""
    original = _state_with_every_field_set()
    storage.save_game_state(original, tmp_path)
    loaded = storage.load_game_state(tmp_path)

    assert loaded.turn_number == 7
    assert loaded.game_time_hours == original.game_time_hours
    assert loaded.tax_pools == {"f1": 12.5}
    assert loaded.invest_pools == {"f1": 3.25}
    assert loaded.location_blessings == {"c1": 2}
    assert loaded.location_curses == {"c2": 1}
    assert loaded.posted_messages == {"c1": "The gate stands open."}
    assert loaded.world_map.cities["c1"].population_band is PopulationBand.LARGE
    assert loaded.world_map.roads["r1"].quality is RoadQuality.GOOD
    assert loaded.characters["ch1"].name == "Vela"
    assert loaded.unit_stacks["u1"].count == 20
    assert loaded.unit_stacks["u1"].unit_type is UnitType.SOLDIER
    assert loaded.ships["s1"].ship_type is ShipType.GALLEY
    assert loaded.summoned_creatures["sc1"].count == 2
    assert loaded.magical_items["mi1"].name == "Seeing Orb"
    assert loaded.elite_units["e1"].faction_id == "f1"

    entry = loaded.order_queues["ch1"][0]
    assert entry.order_class == "RecruitOrder"
    assert entry.release_turn == 9
    assert entry.release_hour == 4
    assert entry.check_hour == 2
    assert entry.repeat_remaining == 3
    assert isinstance(entry.order, RecruitOrder)
    assert entry.order.count == 5
    assert entry.order.city_id == "c1"
