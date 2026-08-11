"""
Tests for the v1.0 magical item slice.

the design describes five kinds of item made by a long-dead enchantress:
amulets lend a skill, crystals store power that is spent before the caster's
own, orbs power a SCAN, rings divide an attacker's odds, and wands supply both
the skill and the power for one named spell.
"""

import random
import re
from pathlib import Path

import pytest

from soe import config, engine, items, models, parser, storage
from soe.models import ItemType, LocationPosition, PopulationBand


@pytest.fixture
def world():
    """A wizard and a scout in Rome, a rival in Carthage, and a ruin nearby."""
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
        id="c1", name="Merlinus", faction_id="p1", location_city_id="city1",
        is_leader=True, gold=500, magic_skill=60, magic_power_current=60,
        trading_skill=10,
    )
    gs.characters["c2"] = models.Character(
        id="c2", name="Alan Reed", faction_id="p1", location_city_id="city1",
        combat_skill=20, gold=100, magic_skill=0, magic_power_current=0,
    )
    gs.characters["e1"] = models.Character(
        id="e1", name="Tengri", faction_id="p2", location_city_id="city2",
        combat_skill=25, is_leader=True, gold=500,
    )
    return gs


def escort(gs, count=45, leader="c1"):
    """
    Assign soldiers to a character so their flight has a real weight.

    the design prices FLY at one fifth of the group's encumbrance. A lone wizard
    weighs 1 and would fly for a single point, which is too cheap to show
    whether a crystal or a wand paid. Forty-five soldiers put the cost at 10.
    """
    gs.unit_stacks[f"stack_{leader}"] = models.UnitStack(
        id=f"stack_{leader}", faction_id=gs.characters[leader].faction_id,
        location_city_id=gs.characters[leader].location_city_id,
        unit_type=models.UnitType.SOLDIER, count=count,
        owner_character_id=leader,
    )


def give(gs, item_type, holder="c1", **kw):
    """Put an item of a known strength in a character's hands."""
    item = models.MagicalItem(
        id=f"item_{len(gs.magical_items) + 1}",
        name=f"*Test{len(gs.magical_items) + 1}*",
        item_type=item_type, holder_character_id=holder, **kw,
    )
    gs.magical_items[item.id] = item
    return item


def run(gs, text, player="p1", seed=42):
    """Parse one player's orders and run a turn."""
    orders = parser.parse_orders(text, gs, player)
    return engine.run_turn(gs, {player: orders}, seed=seed)


def messages(log, player="p1"):
    return [e.description for e in log.events if e.player_id == player]


# ---------------------------------------------------------------------------
# Naming and lookup
# ---------------------------------------------------------------------------

def test_item_names_resolve_with_or_without_asterisks(world):
    item = give(world, ItemType.CRYSTAL, power_current=10, power_max=40)
    item.name = "*Sarema*"
    assert items.find_item_by_name("*Sarema*", world) is item
    assert items.find_item_by_name("sarema", world) is item
    assert items.find_item_by_name("Velika", world) is None


def test_generated_names_are_unique_and_starred(world):
    rng = random.Random(7)
    names = {items.generate_item_name(world, rng) for _ in range(20)}
    # Generation alone does not register the item, so feed them back in to
    # prove the collision check actually looks at the registry.
    for i, name in enumerate(sorted(names)):
        world.magical_items[f"x{i}"] = models.MagicalItem(
            id=f"x{i}", name=name, item_type=ItemType.RING)
    fresh = items.generate_item_name(world, rng)
    assert fresh.startswith("*") and fresh.endswith("*")
    assert fresh not in names


# ---------------------------------------------------------------------------
# Crystals: power pooled and tapped first
# ---------------------------------------------------------------------------

def test_crystal_power_is_spent_before_the_casters_own(world):
    wizard = world.characters["c1"]
    give(world, ItemType.CRYSTAL, power_current=20, power_max=40)

    assert items.available_magic_power(wizard, world) == 80
    assert items.spend_magic_power(wizard, 15, world)
    # All 15 came out of the crystal; the wizard is untouched.
    assert items.items_of_type("c1", ItemType.CRYSTAL, world)[0].power_current == 5
    assert wizard.magic_power_current == 60


def test_crystals_drain_one_at_a_time_then_the_caster(world):
    wizard = world.characters["c1"]
    give(world, ItemType.CRYSTAL, power_current=10, power_max=40)
    give(world, ItemType.CRYSTAL, power_current=10, power_max=40)

    assert items.spend_magic_power(wizard, 75, world)
    crystals = items.items_of_type("c1", ItemType.CRYSTAL, world)
    assert [c.power_current for c in crystals] == [0, 0]
    assert wizard.magic_power_current == 5


def test_spending_more_than_available_changes_nothing(world):
    wizard = world.characters["c1"]
    crystal = give(world, ItemType.CRYSTAL, power_current=10, power_max=40)

    assert not items.spend_magic_power(wizard, 100, world)
    assert crystal.power_current == 10
    assert wizard.magic_power_current == 60


def test_a_spell_draws_on_a_crystal(world):
    world.characters["c1"].magic_power_current = 2
    escort(world)
    crystal = give(world, ItemType.CRYSTAL, power_current=30, power_max=40)

    world, log = run(world, "fly to carthage")
    assert world.characters["c1"].location_city_id == "city2"
    # Fly costs 10: the crystal covers it rather than the wizard's own 2.
    assert crystal.power_current == 20


# ---------------------------------------------------------------------------
# Amulets: borrowed skill
# ---------------------------------------------------------------------------

def test_best_amulet_wins_and_magic_is_never_granted(world):
    give(world, ItemType.AMULET, skill="trading", skill_level=50)
    give(world, ItemType.AMULET, skill="trading", skill_level=72)
    give(world, ItemType.AMULET, skill="magic", skill_level=90)

    char = world.characters["c1"]
    assert items.amulet_skill_level(char, "trading", world) == 72
    assert items.amulet_skill_level(char, "magic", world) == 0
    # The wearer's own trading skill is 10, so the amulet is what counts.
    assert items.effective_skill_with_items(char, "trading", world) == 72


def test_amulet_does_not_lower_a_better_natural_skill(world):
    world.characters["c1"].trading_skill = 80
    give(world, ItemType.AMULET, skill="trading", skill_level=40)
    assert items.effective_skill_with_items(world.characters["c1"], "trading", world) == 80


def test_conjuring_an_amulet_of_magic_is_refused(world):
    orders = parser.parse_orders("conjure an amulet of magic", world, "p1")
    assert orders and orders[0].warnings
    assert "magic" in orders[0].warnings[0]


# ---------------------------------------------------------------------------
# Rings: protection
# ---------------------------------------------------------------------------

def test_ring_divides_the_hit_chance_dropping_fractions():
    # the design's worked example: 74% against a prot-3 ring becomes 24%.
    assert items.apply_ring_protection(0.74, 3) == pytest.approx(0.24)
    assert items.apply_ring_protection(0.74, 0) == pytest.approx(0.74)


def test_best_ring_applies_and_a_blessing_adds_one(world):
    give(world, ItemType.RING, protection=2)
    give(world, ItemType.RING, protection=4)
    char = world.characters["c1"]
    assert items.ring_protection(char, world) == 4
    assert items.ring_protection(char, world, blessed=True) == 5


def test_a_blessing_alone_grants_no_protection(world):
    assert items.ring_protection(world.characters["c1"], world, blessed=True) == 0


def test_a_ring_reduces_combat_damage(world):
    from soe import combat

    give(world, ItemType.RING, holder="c2", protection=4)
    before_ringed = world.characters["c2"].health
    before_bare = world.characters["c1"].health

    combat.apply_casualties("p1", "city1", 0.5, world, random.Random(1))

    ringed_loss = before_ringed - world.characters["c2"].health
    bare_loss = before_bare - world.characters["c1"].health
    assert ringed_loss < bare_loss


# ---------------------------------------------------------------------------
# Wands: borrowed skill and power, but only when named
# ---------------------------------------------------------------------------

def test_a_wand_is_only_used_when_the_order_names_it(world):
    world.characters["c1"].magic_power_current = 0
    wand = give(world, ItemType.WAND, spell="fly", power_current=50,
                power_max=60, skill_level=70)
    wand.name = "*Doramba*"

    # No name in the order: the wand sits idle and the flight fails.
    world, log = run(world, "fly to carthage")
    assert world.characters["c1"].location_city_id == "city1"
    # Unspent, so the wand ends the turn at its start value plus regeneration.
    assert world.magical_items[wand.id].power_current == 50 + config.DAYS_PER_TURN


def test_a_named_wand_supplies_the_power(world):
    world.characters["c1"].magic_power_current = 0
    escort(world)
    wand = give(world, ItemType.WAND, spell="fly", power_current=50,
                power_max=60, skill_level=70)
    wand.name = "*Doramba*"

    world, log = run(world, "fly to carthage using *Doramba*")
    assert world.characters["c1"].location_city_id == "city2"
    # Fly costs 10, and the wand regains a point a day afterwards.
    assert world.magical_items[wand.id].power_current == 50 - 10 + config.DAYS_PER_TURN


def test_a_wand_of_the_wrong_spell_is_refused(world):
    wand = give(world, ItemType.WAND, spell="summon", power_current=50,
                power_max=60, skill_level=70)
    wand.name = "*Agamonke*"

    world, log = run(world, "fly to carthage using *Agamonke*")
    assert world.characters["c1"].location_city_id == "city1"
    assert any("wand of summon" in m for m in messages(log))


def test_a_wand_never_taps_a_crystal(world):
    world.characters["c1"].magic_power_current = 0
    escort(world)
    crystal = give(world, ItemType.CRYSTAL, power_current=40, power_max=40)
    wand = give(world, ItemType.WAND, spell="fly", power_current=3,
                power_max=60, skill_level=70)
    wand.name = "*Doramba*"

    world, log = run(world, "fly to carthage using *Doramba*")
    assert world.characters["c1"].location_city_id == "city1"
    # The crystal is untouched: a wand short of power simply fails.
    assert world.magical_items[crystal.id].power_current == 40


def test_with_clause_naming_no_item_is_left_alone(world):
    """`attack ... with 50 soldiers` must not be read as a wand clause."""
    stripped, wand = parser.strip_wand("attack tengri with soldiers", world)
    assert stripped == "attack tengri with soldiers"
    assert wand == ""


# ---------------------------------------------------------------------------
# CONJURE
# ---------------------------------------------------------------------------

def test_conjure_needs_magic_skill_25(world):
    world.characters["c1"].magic_skill = 20
    world.characters["c1"].magic_power_current = 20

    world, log = run(world, "conjure a ring")
    assert not world.magical_items
    assert any("magic skill 25" in m for m in messages(log))


def test_conjure_spends_all_power_and_can_succeed(world):
    # 60 power gives a 60% chance; this seed lands inside it.
    world, log = run(world, "conjure a ring", seed=3)
    conjured = [i for i in world.magical_items.values()
                if i.item_type == ItemType.RING]
    assert conjured, messages(log)
    item = conjured[0]
    assert item.holder_character_id == "c1"
    assert item.is_temporary
    assert item.protection > 0


def test_a_failed_conjuration_still_costs_everything(world):
    wizard = world.characters["c1"]
    wizard.magic_skill = 30
    wizard.magic_power_current = 30
    crystal = give(world, ItemType.CRYSTAL, power_current=5, power_max=40)

    # Deliberately search seeds for a failure: the point is the cost, not luck.
    for seed in range(50):
        gs = _clone(world)
        gs, log = run(gs, "conjure a ring", seed=seed)
        if any("conjuration failed" in m for m in messages(log)):
            # The wizard's own power is refilled by end-of-turn cleanup, but
            # the crystal is not: it was drained and stayed drained, because a
            # crystal only recharges off a possessor who ends at full power.
            assert gs.magical_items[crystal.id].power_current == 0
            assert not [i for i in gs.magical_items.values() if i.is_temporary]
            return
    pytest.fail("no seed produced a failed conjuration")


def test_conjuring_a_wand_needs_a_spell(world):
    orders = parser.parse_orders("conjure a wand", world, "p1")
    assert orders and orders[0].warnings


def test_conjured_wand_carries_the_named_spell(world):
    world, log = run(world, "conjure a wand of teleport", seed=3)
    wands = [i for i in world.magical_items.values() if i.item_type == ItemType.WAND]
    assert wands, messages(log)
    assert wands[0].spell == "teleport"


def test_conjured_items_expire_and_the_owner_is_told(world):
    item = give(world, ItemType.RING, protection=3)
    item.expires_turn = world.turn_number

    world, log = run(world, "")
    assert item.id not in world.magical_items
    assert any("returned to whence it came" in m for m in messages(log))


def test_found_items_are_never_expired(world):
    item = give(world, ItemType.RING, protection=3)  # expires_turn stays -1
    world, log = run(world, "")
    assert item.id in world.magical_items


# ---------------------------------------------------------------------------
# CHARGE / RECHARGE and ABSORB
# ---------------------------------------------------------------------------

def test_charge_by_a_fixed_amount(world):
    crystal = give(world, ItemType.CRYSTAL, power_current=5, power_max=60)
    crystal.name = "*Madingo*"

    world, log = run(world, "charge *Madingo* by 10 points")
    assert world.magical_items[crystal.id].power_current == 15


def test_charge_to_a_target_level(world):
    crystal = give(world, ItemType.CRYSTAL, power_current=5, power_max=80)
    crystal.name = "*Ampu*"

    world, log = run(world, "charge *Ampu* to 30 power")
    assert world.magical_items[crystal.id].power_current == 30


def test_charge_without_a_quantity_gives_everything_it_can(world):
    crystal = give(world, ItemType.CRYSTAL, power_current=0, power_max=25)
    crystal.name = "*Hasimpa*"

    world, log = run(world, "recharge *Hasimpa*")
    # Capped by the crystal's maximum, not by the wizard's 60 power.
    assert world.magical_items[crystal.id].power_current == 25


def test_charge_names_several_items_with_their_own_quantities(world):
    a = give(world, ItemType.CRYSTAL, power_current=0, power_max=80)
    a.name = "*Ampu*"
    b = give(world, ItemType.CRYSTAL, power_current=0, power_max=80)
    b.name = "*Wasute*"

    world, log = run(world, "charge *Ampu* to 20 power and *Wasute* by 7 power")
    assert world.magical_items[a.id].power_current == 20
    assert world.magical_items[b.id].power_current == 7


def test_charging_a_ring_is_refused(world):
    ring = give(world, ItemType.RING, protection=3)
    ring.name = "*Doramba*"

    world, log = run(world, "charge *Doramba* by 10 points")
    assert any("holds no power" in m for m in messages(log))


def test_absorb_takes_power_out_of_an_item(world):
    world.characters["c1"].magic_power_current = 10
    crystal = give(world, ItemType.CRYSTAL, power_current=30, power_max=40)
    crystal.name = "*Madingo*"

    world, log = run(world, "absorb 10 points from *Madingo*")
    assert world.magical_items[crystal.id].power_current == 20
    # Turn cleanup refills power, so check the item side and the log.
    assert any("absorbed 10 power" in m for m in messages(log))


def test_absorb_everything_is_capped_by_the_casters_maximum(world):
    wizard = world.characters["c1"]
    wizard.magic_skill = 20          # maximum power is 20
    wizard.magic_power_current = 5
    crystal = give(world, ItemType.CRYSTAL, power_current=40, power_max=40)
    crystal.name = "*Umiki*"

    world, log = run(world, "have merlinus absorb everything from *Umiki*")
    # Only the 15 points of headroom move, and the crystal then recharges off
    # a possessor who is now at his maximum.
    assert any("absorbed 15 power" in m for m in messages(log))
    assert world.magical_items[crystal.id].power_current == 40 - 15 + config.DAYS_PER_TURN


def test_charging_reaches_an_item_held_by_a_companion(world):
    crystal = give(world, ItemType.CRYSTAL, holder="c2",
                   power_current=0, power_max=50)
    crystal.name = "*Gilopeshta*"

    world, log = run(world, "have merlinus charge *Gilopeshta* by 12 points")
    assert world.magical_items[crystal.id].power_current == 12


def test_charging_cannot_reach_an_item_elsewhere(world):
    world.characters["c2"].location_city_id = "city2"
    crystal = give(world, ItemType.CRYSTAL, holder="c2",
                   power_current=0, power_max=50)
    crystal.name = "*Gilopeshta*"

    world, log = run(world, "have merlinus charge *Gilopeshta* by 12 points")
    assert world.magical_items[crystal.id].power_current == 0
    assert any("cannot reach" in m for m in messages(log))


def test_a_character_with_no_magic_skill_cannot_charge(world):
    crystal = give(world, ItemType.CRYSTAL, holder="c2",
                   power_current=0, power_max=50)
    crystal.name = "*Gilopeshta*"

    world, log = run(world, "have alan reed charge *Gilopeshta*")
    assert world.magical_items[crystal.id].power_current == 0
    assert any("no magic skill" in m for m in messages(log))


# ---------------------------------------------------------------------------
# SCAN
# ---------------------------------------------------------------------------

def test_scan_reports_a_distant_city_and_spends_orb_power(world):
    orb = give(world, ItemType.ORB, power_current=60)
    orb.name = "*Sarema*"

    world, log = run(world, "scan carthage using *Sarema*")
    scans = [m for m in messages(log) if "scans Carthage" in m]
    assert scans, messages(log)
    assert "Tengri" in scans[0]

    cost = int(re.search(r"\((\d+) power\)", scans[0]).group(1))
    assert cost > 0
    assert world.magical_items[orb.id].power_current == 60 - cost + config.DAYS_PER_TURN


def test_scan_without_naming_an_orb_fails(world):
    give(world, ItemType.ORB, power_current=60)
    world, log = run(world, "scan carthage")
    assert any("must name the orb" in m for m in messages(log))


def test_scan_needs_the_orb_in_hand(world):
    orb = give(world, ItemType.ORB, holder="e1", power_current=60)
    orb.name = "*Sarema*"

    world, log = run(world, "scan carthage using *Sarema*")
    assert any("does not possess" in m for m in messages(log))


def test_scan_fails_when_the_orb_lacks_power(world):
    orb = give(world, ItemType.ORB, power_current=1)
    orb.name = "*Sarema*"

    world, log = run(world, "scan carthage using *Sarema*")
    assert any("not the" in m and "needed to reach" in m for m in messages(log))


def test_an_orb_cannot_see_people_merely_near_a_city(world):
    orb = give(world, ItemType.ORB, power_current=60)
    orb.name = "*Sarema*"
    world.characters["e1"].location_position = LocationPosition.NEAR

    world, log = run(world, "scan carthage using *Sarema*")
    assert any("sees nobody" in m for m in messages(log))


def test_an_orb_sees_through_lurking(world):
    orb = give(world, ItemType.ORB, power_current=60)
    orb.name = "*Sarema*"
    world.characters["e1"].is_lurking = True

    world, log = run(world, "scan carthage using *Sarema*")
    assert any("Tengri" in m and "scans Carthage" in m for m in messages(log))


# ---------------------------------------------------------------------------
# SEARCH in ruins
# ---------------------------------------------------------------------------

def test_searching_ruins_can_turn_up_an_item(world):
    world.characters["c1"].location_city_id = "ruin1"

    for seed in range(60):
        gs = _clone(world)
        gs, log = run(gs, "search for 30 days", seed=seed)
        if gs.magical_items:
            found = next(iter(gs.magical_items.values()))
            assert found.holder_character_id == "c1"
            assert not found.is_temporary  # found items last forever
            assert any("found *" in m for m in messages(log))
            return
    pytest.fail("no seed produced a find")


def test_searching_an_inhabited_city_finds_nothing(world):
    world, log = run(world, "search for 30 days")
    assert not world.magical_items
    assert any("not uninhabited ruins" in m for m in messages(log))


# ---------------------------------------------------------------------------
# Regeneration
# ---------------------------------------------------------------------------

def test_orbs_and_wands_regain_a_point_a_day(world):
    orb = give(world, ItemType.ORB, power_current=10)
    wand = give(world, ItemType.WAND, spell="fly", power_current=10,
                power_max=60, skill_level=70)

    items.regenerate(world)
    assert orb.power_current == 10 + config.DAYS_PER_TURN
    assert wand.power_current == 10 + config.DAYS_PER_TURN


def test_a_wand_does_not_regenerate_past_its_maximum(world):
    wand = give(world, ItemType.WAND, spell="fly", power_current=58,
                power_max=60, skill_level=70)
    items.regenerate(world)
    assert wand.power_current == 60


def test_an_orb_has_no_ceiling(world):
    orb = give(world, ItemType.ORB, power_current=500)
    items.regenerate(world)
    assert orb.power_current == 500 + config.DAYS_PER_TURN


def test_a_crystal_only_charges_off_a_possessor_at_full_power(world):
    full = give(world, ItemType.CRYSTAL, power_current=0, power_max=60)
    world.characters["c1"].magic_power_current = world.characters["c1"].max_magic_power

    drained = give(world, ItemType.CRYSTAL, holder="c2",
                   power_current=0, power_max=60)
    world.characters["c2"].magic_skill = 20
    world.characters["c2"].magic_power_current = 3

    items.regenerate(world)
    assert full.power_current == config.DAYS_PER_TURN
    assert drained.power_current == 0


def test_an_unheld_crystal_does_not_charge(world):
    loose = give(world, ItemType.CRYSTAL, holder="", power_current=0, power_max=60)
    items.regenerate(world)
    assert loose.power_current == 0


# ---------------------------------------------------------------------------
# Giving items away
# ---------------------------------------------------------------------------

def test_an_item_is_given_by_name(world):
    item = give(world, ItemType.AMULET, skill="trading", skill_level=72)
    item.name = "*Sarema*"

    world, log = run(world, "give *Sarema* to alan reed")
    assert world.magical_items[item.id].holder_character_id == "c2"


def test_giving_an_item_the_donor_lacks_is_refused(world):
    item = give(world, ItemType.AMULET, holder="c2", skill="trading", skill_level=72)
    item.name = "*Sarema*"

    world, log = run(world, "give *Sarema* to alan reed")
    assert any("not carrying" in m for m in messages(log))


def test_a_given_crystal_keeps_its_power(world):
    crystal = give(world, ItemType.CRYSTAL, power_current=33, power_max=60)
    crystal.name = "*Velika*"

    world, log = run(world, "give *Velika* to alan reed")
    moved = world.magical_items[crystal.id]
    assert moved.holder_character_id == "c2"
    assert moved.power_current == 33


# ---------------------------------------------------------------------------
# Reporting and persistence
# ---------------------------------------------------------------------------

def test_describe_matches_the_rules_report_format(world):
    amulet = give(world, ItemType.AMULET, skill="trading", skill_level=72)
    amulet.name = "*Sarema*"
    crystal = give(world, ItemType.CRYSTAL, power_current=51, power_max=60)
    crystal.name = "*Velika*"
    ring = give(world, ItemType.RING, protection=3)
    ring.name = "*Doramba*"

    assert items.describe(amulet, world) == "*Sarema* [amulet, trading 72]"
    assert items.describe(crystal, world) == "*Velika* [crystal, power 51/60]"
    assert items.describe(ring, world) == "*Doramba* [ring, prot 3]"


def test_a_temporary_item_shows_the_days_remaining(world):
    ring = give(world, ItemType.RING, protection=3)
    ring.name = "*Doramba*"
    ring.expires_turn = world.turn_number + 3
    assert items.describe(ring, world).endswith(f"{3 * config.DAYS_PER_TURN}d]")


def test_items_appear_on_the_status_report(world):
    from soe import reporting

    item = give(world, ItemType.CRYSTAL, power_current=51, power_max=60)
    item.name = "*Velika*"
    world, log = run(world, "")
    reports = reporting.generate_player_reports(world, log, {"p1": []})
    assert "Magical items:" in reports["p1"]
    assert items.describe(world.magical_items[item.id], world) in reports["p1"]


def test_items_survive_a_save_and_load(world, tmp_path: Path):
    wand = give(world, ItemType.WAND, spell="teleport", power_current=62,
                power_max=75, skill_level=80)
    wand.name = "*Doramba*"
    wand.expires_turn = 9

    storage.save_game_state(world, tmp_path)
    reloaded = storage.load_game_state(tmp_path)

    restored = reloaded.magical_items[wand.id]
    assert restored.name == "*Doramba*"
    assert restored.item_type == ItemType.WAND
    assert restored.spell == "teleport"
    assert restored.power_current == 62
    assert restored.power_max == 75
    assert restored.skill_level == 80
    assert restored.holder_character_id == "c1"
    assert restored.expires_turn == 9


def test_an_old_save_without_items_still_loads(world, tmp_path: Path):
    storage.save_game_state(world, tmp_path)
    state_file = tmp_path / "state.json"
    import json
    data = json.loads(state_file.read_text(encoding="utf-8"))
    del data["magical_items"]
    state_file.write_text(json.dumps(data), encoding="utf-8")

    reloaded = storage.load_game_state(tmp_path)
    assert reloaded.magical_items == {}


def _clone(gs):
    """Deep-copy a game state so seed sweeps start from the same world."""
    import copy
    return copy.deepcopy(gs)


def test_scan_with_two_orbs_is_rejected_rather_than_misread(world):
    give(world, ItemType.ORB, power_current=60).name = "*Sarema*"
    give(world, ItemType.ORB, power_current=60).name = "*Doramba*"

    orders = parser.parse_orders(
        "scan rome using *Sarema* and carthage using *Doramba*", world, "p1")
    assert orders and orders[0].warnings
    assert "more than one orb" in orders[0].warnings[0]


# ---------------------------------------------------------------------------
# Magic-free zones
# ---------------------------------------------------------------------------

def test_a_magic_free_zone_drains_people_and_their_items(world):
    world.world_map.cities["city1"].is_magic_free = True
    crystal = give(world, ItemType.CRYSTAL, power_current=40, power_max=40)
    orb = give(world, ItemType.ORB, power_current=30)
    ring = give(world, ItemType.RING, protection=3)

    world, log = run(world, "")
    assert world.magical_items[crystal.id].power_current == 0
    assert world.magical_items[orb.id].power_current == 0
    # A ring holds no power, so it is unaffected.
    assert world.magical_items[ring.id].protection == 3
    assert any("drained away" in m for m in messages(log))


def test_items_do_not_regenerate_in_a_magic_free_zone(world):
    world.world_map.cities["city1"].is_magic_free = True
    orb = give(world, ItemType.ORB, power_current=30)

    items.regenerate(world)
    assert orb.power_current == 30


def test_an_ordinary_city_drains_nobody(world):
    crystal = give(world, ItemType.CRYSTAL, power_current=40, power_max=40)
    world, log = run(world, "")
    assert world.magical_items[crystal.id].power_current == 40
    assert not any("drained away" in m for m in messages(log))


def test_a_queued_charge_survives_save_and_load(world, tmp_path: Path):
    """ChargeOrder carries a list of nested dataclasses -- the risky round-trip."""
    crystal = give(world, ItemType.CRYSTAL, power_current=0, power_max=80)
    crystal.name = "*Ampu*"

    # Queue the charge behind a wait so it is still pending when we save.
    world, _ = run(world, "Wait for 2 weeks. Charge *Ampu* to 40 power.")
    storage.save_game_state(world, tmp_path)
    reloaded = storage.load_game_state(tmp_path)

    queued = [e for entries in reloaded.order_queues.values() for e in entries]
    charges = [e.order for e in queued if e.order_class == "ChargeOrder"]
    assert charges, [e.order_class for e in queued]
    target = charges[0].targets[0]
    assert target.item_name == "*Ampu*"
    assert target.amount == 40
    assert target.to_level is True
