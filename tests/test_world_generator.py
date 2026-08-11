"""
The seeded world generator.

Two properties are worth defending in tests. *Determinism*, because a
benchmark that cannot reproduce its own map cannot reproduce its results. And
*playability*, because a world the engine cannot route across is not a world:
a faction stranded on an island it cannot leave loses to the map rather than
to an opponent.

The distribution checks are deliberately loose. They exist to catch a
generator that has drifted into producing a desert with four cities or an
archipelago with no roads, not to pin down exact counts.
"""

from __future__ import annotations

import json

import pytest

from soe import map_loader
from scripts.generate_world import DEFAULT_TOWNS, generate

SEEDS = [1, 7, 42]


@pytest.fixture(scope="module")
def worlds():
    return {seed: generate(seed) for seed in SEEDS}


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_same_seed_gives_identical_world():
    assert json.dumps(generate(3), sort_keys=True) == json.dumps(
        generate(3), sort_keys=True
    )


def test_different_seeds_give_different_worlds():
    a = {c["name"] for c in generate(1)["cities"]}
    b = {c["name"] for c in generate(2)["cities"]}
    # A little overlap is possible from a shared syllable stock; wholesale
    # agreement would mean the seed is not reaching the name generator.
    assert len(a & b) < len(a) * 0.2


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_town_count_and_unique_ids(worlds, seed):
    cities = worlds[seed]["cities"]
    assert len(cities) == DEFAULT_TOWNS
    assert len({c["id"] for c in cities}) == len(cities)
    assert len({c["name"] for c in cities}) == len(cities)


@pytest.mark.parametrize("seed", SEEDS)
def test_routes_reference_real_towns(worlds, seed):
    world = worlds[seed]
    ids = {c["id"] for c in world["cities"]}
    for road in world["roads"]:
        assert road["from"] in ids
        assert road["to"] in ids
        assert road["from"] != road["to"]
        assert road["distance_miles"] > 0


@pytest.mark.parametrize("seed", SEEDS)
def test_sea_lanes_only_join_ports(worlds, seed):
    world = worlds[seed]
    ports = {c["id"] for c in world["cities"] if c["is_port"]}
    for road in world["roads"]:
        if road["quality"] == "sea":
            assert road["from"] in ports
            assert road["to"] in ports


@pytest.mark.parametrize("seed", SEEDS)
def test_towns_sit_inside_the_field(worlds, seed):
    for city in worlds[seed]["cities"]:
        assert 0 <= city["x_miles"] <= 1300
        assert 0 <= city["y_miles"] <= 1000
        assert 0.0 <= city["x"] <= 1.0
        assert 0.0 <= city["y"] <= 1.0
        assert city["grid_ref"][0] in "ABCDEFGHIJ"


# ---------------------------------------------------------------------------
# Playability
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_engine_loads_the_world(tmp_path, worlds, seed):
    path = tmp_path / f"world_{seed}.json"
    path.write_text(json.dumps(worlds[seed]), encoding="utf-8")
    world = map_loader.load_map_from_json(path)
    assert len(world.cities) == DEFAULT_TOWNS
    assert world.roads


@pytest.mark.parametrize("seed", SEEDS)
def test_every_town_is_reachable(tmp_path, worlds, seed):
    path = tmp_path / f"world_{seed}.json"
    path.write_text(json.dumps(worlds[seed]), encoding="utf-8")
    world = map_loader.load_map_from_json(path)
    assert map_loader.isolated_cities(world) == []
    assert len(map_loader.mutually_reachable_cities(world)) == DEFAULT_TOWNS


# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_population_bands_are_pyramidal(worlds, seed):
    cities = worlds[seed]["cities"]
    counts = {band: 0 for band in ("< 1k", "1k-9k", "10k-99k", "100k+")}
    for city in cities:
        counts[city["population_band"]] += 1
    assert counts["< 1k"] > counts["1k-9k"] > counts["10k-99k"] > counts["100k+"]
    assert counts["100k+"] >= 1


@pytest.mark.parametrize("seed", SEEDS)
def test_terrain_and_ports_are_varied(worlds, seed):
    cities = worlds[seed]["cities"]
    kinds = {t for c in cities for t in c["terrain"]}
    assert len(kinds) >= 4
    ports = sum(1 for c in cities if c["is_port"])
    assert 0.12 * len(cities) <= ports <= 0.55 * len(cities)


@pytest.mark.parametrize("seed", SEEDS)
def test_route_network_is_neither_sparse_nor_dense(worlds, seed):
    world = worlds[seed]
    routes, towns = len(world["roads"]), len(world["cities"])
    assert towns <= routes <= towns * 3
    qualities = {r["quality"] for r in world["roads"]}
    assert "sea" in qualities
    assert len(qualities) >= 4
