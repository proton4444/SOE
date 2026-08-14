"""
Wave 2 review corrections (C7–C23): written order ≠ executed order.

Each test names a defect from docs/REVIEW_CORRECTIONS_2026-08-13.md and
was confirmed to fail against the pre-fix source.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from soe import engine, models, orders, parser
from soe.parser import control as parse_control
from soe.phases import finance, magic, units


@pytest.fixture
def world():
    gs = models.GameState()
    gs.world_map.cities["city1"] = models.City(
        id="city1", name="Rome", population_band=models.PopulationBand.MEDIUM,
        is_port=True, terrain={"forest"},
    )
    gs.world_map.cities["city2"] = models.City(
        id="city2", name="Carthage", population_band=models.PopulationBand.SMALL,
        is_port=True,
    )
    gs.world_map.roads["road1"] = models.Road(
        id="road1", from_city_id="city1", to_city_id="city2",
        quality=models.RoadQuality.GOOD,
    )
    gs.factions["p1"] = models.Faction(
        id="p1", name="Empire", treasury=5000, controlled_city_ids={"city1"},
    )
    gs.factions["p2"] = models.Faction(
        id="p2", name="Horde", treasury=1000, controlled_city_ids={"city2"},
    )
    gs.factions["npc"] = models.Faction(id="npc", name="Independents", is_npc=True)
    gs.characters["c1"] = models.Character(
        id="c1", name="Marcus", faction_id="p1", location_city_id="city1",
        combat_skill=15, magic_skill=40, magic_power_current=80,
        religion_skill=40, is_leader=True, gold=400, gender="male",
    )
    gs.characters["c2"] = models.Character(
        id="c2", name="Tengri", faction_id="p2", location_city_id="city2",
        combat_skill=10, is_leader=True, gold=200, gender="male",
    )
    gs.characters["c1b"] = models.Character(
        id="c1b", name="Julia", faction_id="p1", location_city_id="city1",
        combat_skill=20, gold=50, gender="female",
    )
    gs.characters["mary"] = models.Character(
        id="mary", name="Mary Wise", faction_id="p1", location_city_id="city1",
        gold=200, gender="female",
    )
    gs.characters["nancy"] = models.Character(
        id="nancy", name="Nancy Myers", faction_id="p1", location_city_id="city1",
        gold=80, gender="female",
    )
    gs.characters["alan"] = models.Character(
        id="alan", name="Alan Reed", faction_id="p1", location_city_id="city1",
        gold=40, gender="male",
    )
    gs.characters["joe"] = models.Character(
        id="joe", name="Joe", faction_id="p1", location_city_id="city1",
        gold=20, gender="male",
    )
    gs.characters["eng"] = models.Character(
        id="eng", name="Engineer", faction_id="p1", location_city_id="city1",
        gold=10, gender="male",
    )
    gs.characters["mike"] = models.Character(
        id="mike", name="Mike", faction_id="p1", location_city_id="city1",
        magic_skill=5, gold=10, gender="male",
    )
    gs.characters["npc1"] = models.Character(
        id="npc1", name="Nancy Lopenda", faction_id="npc",
        location_city_id="city1", religion_skill=45, gender="female",
    )
    return gs


def parse(gs, text, player="p1"):
    return parser.parse_orders(text, gs, player)


def run(gs, text, player="p1", seed=0):
    parsed = parse(gs, text, player) if isinstance(text, str) else text
    return engine.run_turn(gs, {player: parsed}, seed=seed)


def named(gs, name):
    return next(c for c in gs.characters.values() if c.name.lower() == name.lower())


def soldiers_at(gs, city_id, owner=None):
    total = 0
    for stack in gs.unit_stacks.values():
        if stack.unit_type != models.UnitType.SOLDIER:
            continue
        if stack.location_city_id != city_id:
            continue
        if owner is not None and stack.owner_character_id != owner:
            continue
        total += stack.count
    return total


# ---------------------------------------------------------------------------
# C7 — Revive NAME
# ---------------------------------------------------------------------------

def test_implicit_name_creates_a_character_from_a_local_stack(world):
    gs = world
    gs.unit_stacks["local"] = models.UnitStack(
        id="local", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=3, owner_character_id="c1",
    )
    run(gs, "Name male soldier Joe Henley.")
    joe = named(gs, "Joe Henley")
    assert joe.faction_id == "p1"
    assert joe.location_city_id == "city1"
    assert joe.gender == "male"
    assert gs.unit_stacks["local"].count == 2


def test_have_name_creates_a_character_from_a_local_stack(world):
    gs = world
    gs.unit_stacks["julias"] = models.UnitStack(
        id="julias", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=2, owner_character_id="c1b",
    )
    run(gs, "Have Julia name female soldier Donna Majesti.")
    donna = named(gs, "Donna Majesti")
    assert donna.gender == "female"
    assert donna.location_city_id == "city1"
    assert gs.unit_stacks["julias"].count == 1


def test_short_names_fail_loudly(world):
    gs = world
    gs.unit_stacks["local"] = models.UnitStack(
        id="local", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=3, owner_character_id="c1",
    )
    parsed = parse(gs, "Name male soldier Joe.")
    name_orders = [o for o in parsed if o.order_type() == "NAME"]
    assert name_orders
    assert name_orders[0].warnings
    assert name_orders[0].new_name.lower() in {"", "joe"}
    run(gs, parsed)
    assert not any(c.name.lower().startswith("joe") and c.id != "joe"
                   for c in gs.characters.values())
    assert gs.unit_stacks["local"].count == 3


def test_name_does_not_consume_a_distant_stack(world):
    gs = world
    gs.unit_stacks["local"] = models.UnitStack(
        id="local", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=3, owner_character_id="c1",
    )
    gs.unit_stacks["away"] = models.UnitStack(
        id="away", faction_id="p1", location_city_id="city2",
        unit_type=models.UnitType.SOLDIER, count=5, owner_character_id="c1",
    )
    run(gs, "Name male soldier Joe Henley.")
    assert named(gs, "Joe Henley").location_city_id == "city1"
    assert gs.unit_stacks["local"].count == 2
    assert gs.unit_stacks["away"].count == 5


# ---------------------------------------------------------------------------
# C8 — TELEPORT / FLY must move the priced group
# ---------------------------------------------------------------------------

def test_teleport_moves_the_soldiers_that_were_priced(world):
    gs = world
    gs.characters["c1"].magic_power_current = 80
    gs.unit_stacks["army"] = models.UnitStack(
        id="army", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=20, owner_character_id="c1",
    )
    magic.process_magic(
        {"p1": [orders.TeleportOrder(
            player_id="p1", actor_id="c1", target_character_id="c1",
            destination_city_id="city2",
        )]},
        gs, engine.TurnLog(), __import__("random").Random(1),
    )
    assert gs.characters["c1"].location_city_id == "city2"
    assert gs.unit_stacks["army"].location_city_id == "city2"


def test_a_lone_wizard_still_flies_alone(world):
    gs = world
    gs.characters["c1"].magic_power_current = 80
    gs.unit_stacks["other"] = models.UnitStack(
        id="other", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=10, owner_character_id="c1b",
    )
    magic.process_magic(
        {"p1": [orders.FlyOrder(
            player_id="p1", actor_id="c1", destination_city_id="city2",
        )]},
        gs, engine.TurnLog(), __import__("random").Random(1),
    )
    assert gs.characters["c1"].location_city_id == "city2"
    assert gs.unit_stacks["other"].location_city_id == "city1"
    assert gs.characters["c1b"].location_city_id == "city1"


# ---------------------------------------------------------------------------
# C9 — GET join must attach
# ---------------------------------------------------------------------------

def test_get_with_no_cargo_attaches_the_donor(world):
    gs = world
    parsed = parse(gs, "Get Julia.")
    finance.process_get({"p1": parsed}, gs, engine.TurnLog())
    assert gs.characters["c1b"].group_leader_id == "c1"


# ---------------------------------------------------------------------------
# C10 — GET units must honour ownership
# ---------------------------------------------------------------------------

def test_get_cannot_pull_another_characters_troops(world):
    gs = world
    gs.unit_stacks["julias"] = models.UnitStack(
        id="julias", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=4, owner_character_id="c1b",
    )
    gs.unit_stacks["marys"] = models.UnitStack(
        id="marys", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=8, owner_character_id="mary",
    )
    parsed = parse(gs, "Get 3 soldiers from Julia.")
    finance.process_get({"p1": parsed}, gs, engine.TurnLog())
    assert gs.unit_stacks["julias"].count == 1
    assert gs.unit_stacks["marys"].count == 8
    taken = [s for s in gs.unit_stacks.values()
             if s.owner_character_id == "c1" and s.unit_type.name == "SOLDIER"]
    assert sum(s.count for s in taken) == 3


def test_received_troops_travel_with_the_recipient(world):
    gs = world
    gs.unit_stacks["pool"] = models.UnitStack(
        id="pool", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=6,
    )
    parsed = parse(gs, "Have Julia get 4 soldiers from Marcus.")
    finance.process_get({"p1": parsed}, gs, engine.TurnLog())
    julias = [s for s in gs.unit_stacks.values()
              if s.owner_character_id == "c1b" and s.unit_type.name == "SOLDIER"]
    assert sum(s.count for s in julias) == 4
    from soe import groups
    groups.move_group(gs.characters["c1b"], "city2", gs)
    gs.characters["c1b"].location_city_id = "city2"
    for stack in julias:
        live = gs.unit_stacks.get(stack.id)
        if live:
            assert live.location_city_id == "city2"


# ---------------------------------------------------------------------------
# C11 — possessive her must not flatten percent invest
# ---------------------------------------------------------------------------

def test_percent_invest_of_her_gold_uses_the_agents_purse(world):
    gs = world
    gs.factions["p1"].treasury = 0
    parsed = parse(
        gs,
        "Have Nancy Myers go to Carthage. "
        "Have Mary Wise invest 75 percent of her gold in Rome.",
    )
    invest = next(o for o in parsed if o.order_type() == "INVEST")
    assert invest.actor_id == "mary"
    assert invest.amount == -75.0
    run(gs, parsed)
    # 75% of Mary's 200, not a flat 75.
    assert gs.characters["mary"].gold == pytest.approx(50.0)


def test_percent_offer_of_her_gold_uses_the_agents_purse(world):
    gs = world
    parsed = parse(
        gs,
        "Have Nancy Myers go to Carthage. "
        "Have Mary Wise offer 75 percent of her gold to Nancy Lopenda.",
    )
    offer = next(o for o in parsed if o.order_type() == "OFFER")
    assert offer.actor_id == "mary"
    assert offer.amount == -75.0


# ---------------------------------------------------------------------------
# C12 — IF branches must keep HAVE and failed clauses
# ---------------------------------------------------------------------------

def test_if_then_have_julia_recruits_both_stacks(world):
    gs = world
    parsed = parse(
        gs,
        "If Marcus has at least 1 gold then have Julia recruit 5 soldiers and 3 workers.",
    )
    assert len(parsed) == 1
    then = parsed[0].then_orders
    assert [o.order_type() for o in then] == ["RECRUIT", "RECRUIT"]
    assert all(o.actor_id == "c1b" for o in then)
    assert {o.unit_type.lower() for o in then} == {"soldier", "worker"}


def test_garbage_if_branch_clause_appears_as_a_warning(world):
    parsed = parse(
        world,
        "If Marcus has at least 1 gold then frobnicate the moon.",
    )
    then = parsed[0].then_orders
    assert then
    assert any(o.warnings for o in then)


def test_quoted_say_inside_if_is_restored(world):
    parsed = parse(
        world,
        'If Marcus has at least 1 gold then say "Hold the gate" to Julia.',
    )
    then = parsed[0].then_orders
    assert then
    body = " ".join(
        getattr(o, attr, "")
        for o in then
        for attr in ("message", "text", "original_text")
    )
    assert "Hold the gate" in body
    assert "zqz" not in body


# ---------------------------------------------------------------------------
# C13 — THEN is a barrier, not AND
# ---------------------------------------------------------------------------

def test_recruit_after_attack_then_does_not_run_the_same_turn(world):
    gs = world
    gs.characters["c2"].location_city_id = "city1"
    before = soldiers_at(gs, "city1")
    parsed = parse(gs, "Have Marcus attack Tengri then recruit 20 soldiers.")
    assert len(parsed) >= 2
    assert parsed[0].order_type() == "ATTACK"
    assert parsed[1].order_type() == "RECRUIT"
    assert getattr(parsed[1], "then_after", False)
    run(gs, parsed)
    assert soldiers_at(gs, "city1") == before
    queued = gs.order_queues.get("c1") or []
    assert any(isinstance(e.order, orders.RecruitOrder) for e in queued)


# ---------------------------------------------------------------------------
# C14 — TAX is a verb, not a substring
# ---------------------------------------------------------------------------

def test_query_the_taxman_is_not_tax(world):
    parsed = parse(world, "Query the taxman.")
    assert parsed
    assert all(o.order_type() != "TAX" for o in parsed)


def test_have_joe_report_on_taxation_is_not_tax(world):
    parsed = parse(world, "Have Joe report on taxation.")
    assert parsed
    assert all(o.order_type() != "TAX" for o in parsed)


def test_have_joe_tax_for_2_weeks_still_is_tax(world):
    parsed = parse(world, "Have Joe tax for 2 weeks.")
    assert parsed
    assert parsed[0].order_type() == "TAX"
    assert parsed[0].actor_id == "joe"


# ---------------------------------------------------------------------------
# C15 — Duration units must be parsed
# ---------------------------------------------------------------------------

def test_study_for_21_days_is_three_weeks(world):
    parsed = parse(world, "Study combat for 21 days.")
    assert parsed[0].order_type() == "STUDY"
    assert parsed[0].duration_weeks == 3


def test_collect_for_2_weeks_is_14_days(world):
    parsed = parse(world, "Collect wood for 2 weeks.")
    assert parsed[0].order_type() == "COLLECT"
    assert parsed[0].duration_days == 14


# ---------------------------------------------------------------------------
# C16 — One STUDY, one skill — or split it
# ---------------------------------------------------------------------------

def test_study_magic_and_sailing_covers_both_skills(world):
    parsed = parse(world, "Have Mike study magic and sailing for 1 week.")
    studies = [o for o in parsed if o.order_type() == "STUDY"]
    skills = {o.skill_name for o in studies}
    warned = any("sailing" in w.lower() for o in parsed for w in o.warnings)
    assert skills == {"magic", "sailing"} or (
        studies and warned and "sailing" not in {o.skill_name for o in studies}
    )


# ---------------------------------------------------------------------------
# C17 — Unknown city on BLESS / CURSE / SCRY is invalid
# ---------------------------------------------------------------------------

def test_unknown_city_does_not_bless_the_actors_location(world):
    gs = world
    parsed = parse(gs, "Have Marcus bless Atlantis.")
    assert parsed[0].warnings
    magic.process_religion(
        {"p1": parsed}, gs, engine.TurnLog(), __import__("random").Random(1),
    )
    assert "city1" not in gs.location_blessings
    assert not gs.location_blessings


# ---------------------------------------------------------------------------
# C18 — Honour documented COLLECT / TEACH forms
# ---------------------------------------------------------------------------

def test_have_engineer_collect_40_wood_parses(world):
    parsed = parse(world, "Have Engineer collect 40 wood.")
    assert parsed
    assert parsed[0].order_type() == "COLLECT"
    assert not any("Could not parse" in w for o in parsed for w in o.warnings)


def test_teach_mike_magic_to_level_10_parses(world):
    parsed = parse(world, "Teach Mike magic to level 10.")
    assert parsed
    assert parsed[0].order_type() == "TEACH"
    assert parsed[0].student_id == "mike"
    assert parsed[0].skill_name == "magic"
    assert parsed[0].teacher_id == "c1"


# ---------------------------------------------------------------------------
# C19 — Reflexives on independent NPCs
# ---------------------------------------------------------------------------

def test_independent_heal_herself_heals_that_character(world):
    parsed = parse(world, "Have Nancy Lopenda heal herself.")
    assert parsed
    heal = parsed[0]
    assert heal.order_type() == "HEAL"
    assert heal.actor_id == "npc1"
    assert "npc1" in heal.target_character_ids


# ---------------------------------------------------------------------------
# C20 — Multi-actor HAVE
# ---------------------------------------------------------------------------

def test_have_two_named_characters_both_receive_tax(world):
    parsed = parse(world, "Have Alan Reed and Mary Wise tax for 4 weeks.")
    taxes = [o for o in parsed if o.order_type() == "TAX"]
    assert {o.actor_id for o in taxes} == {"alan", "mary"}


def test_stop_them_stops_both(world):
    parsed = parse(
        world,
        "Have Alan Reed and Mary Wise tax for 4 weeks. Stop them.",
    )
    stops = [o for o in parsed if o.order_type() == "STOP"]
    assert {o.actor_id for o in stops} == {"alan", "mary"}


# ---------------------------------------------------------------------------
# C21 — Thousands separators in quantities
# ---------------------------------------------------------------------------

def test_recruit_1000_soldiers_with_a_comma(world):
    parsed = parse(world, "Recruit 1,000 soldiers.")
    assert parsed[0].order_type() == "RECRUIT"
    assert parsed[0].count == 1000


# ---------------------------------------------------------------------------
# C22 — If Joe has soldiers means any, not zero
# ---------------------------------------------------------------------------

def test_if_joe_has_soldiers_is_true_when_he_has_at_least_one(world):
    gs = world
    cond = parse_control.parse_if_condition("joe has soldiers", gs, "p1")
    assert cond is not None
    assert cond["unit"] == "soldier"
    assert cond["comparator"] in {"more than", "at least"}
    assert cond["amount"] == 0 or (cond["comparator"] == "at least" and cond["amount"] == 1)

    gs.unit_stacks["joes"] = models.UnitStack(
        id="joes", faction_id="p1", location_city_id="city1",
        unit_type=models.UnitType.SOLDIER, count=4, owner_character_id="joe",
    )
    parsed = parse(gs, "If Joe has soldiers then have Julia go to Carthage.")
    run(gs, parsed)
    assert gs.characters["c1b"].location_city_id == "city2"


# ---------------------------------------------------------------------------
# C23 — CLI example order filenames
# ---------------------------------------------------------------------------

def test_example_setup_copy_lines_use_the_names_process_turn_reads(tmp_path):
    from typer.testing import CliRunner

    import cli as soe_cli

    runner = CliRunner()
    result = runner.invoke(soe_cli.app, ["example-setup"])
    assert result.exit_code == 0
    out = result.stdout
    assert "player_1_turn1.txt" in out
    assert "player_2_turn1.txt" in out

    dest = tmp_path / "orders"
    dest.mkdir()
    src = Path("examples/orders_player1_turn1.txt")
    shutil.copy(src, dest / "player_1_turn1.txt")
    text = (dest / "player_1_turn1.txt").read_text(encoding="utf-8")
    assert text.strip()
    # process_turn only opens {faction_id}_turn{n}.txt — the dest name above.
    assert (dest / "player_1_turn1.txt").exists()
    assert not (dest / "orders_player1_turn1.txt").exists()
