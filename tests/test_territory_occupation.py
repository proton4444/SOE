"""Regression coverage for enduring sovereignty and temporary occupation."""

from __future__ import annotations

import pytest

from soe import combat, engine, models, orders, territory
from soe.combat import CombatResult
from soe.phases import combat_phase


@pytest.fixture
def occupation_state() -> models.GameState:
    state = models.GameState()
    state.world_map.cities["home"] = models.City(
        id="home", name="Home", population_band=models.PopulationBand.SMALL)
    state.world_map.cities["city"] = models.City(
        id="city", name="City", population_band=models.PopulationBand.MEDIUM,
        fortification_level=50)
    state.world_map.roads["road"] = models.Road(
        id="road", from_city_id="home", to_city_id="city",
        quality=models.RoadQuality.EXCELLENT)
    state.factions["p1"] = models.Faction(
        id="p1", name="Invaders", treasury=10_000,
        controlled_city_ids={"home"})
    state.factions["p2"] = models.Faction(
        id="p2", name="Sovereigns", treasury=10_000,
        secured_city_ids={"city"})
    state.factions["p3"] = models.Faction(
        id="p3", name="Sovereigns", treasury=10_000,
        controlled_city_ids={"city"})
    state.characters["a"] = models.Character(
        id="a", name="Attacker", faction_id="p1", location_city_id="city",
        movement_points=100, combat_skill=30)
    state.characters["b"] = models.Character(
        id="b", name="Occupier", faction_id="p2", location_city_id="city",
        movement_points=100, combat_skill=10)
    state.characters["ally"] = models.Character(
        id="ally", name="Ally", faction_id="p3", location_city_id="city")
    state.unit_stacks["a_army"] = models.UnitStack(
        id="a_army", faction_id="p1", location_city_id="city",
        unit_type=models.UnitType.SOLDIER, count=1000, owner_character_id="a")
    state.unit_stacks["b_garrison"] = models.UnitStack(
        id="b_garrison", faction_id="p2", location_city_id="city",
        unit_type=models.UnitType.SOLDIER, count=10, owner_character_id="b")
    state.unit_stacks["sovereign_garrison"] = models.UnitStack(
        id="sovereign_garrison", faction_id="p3", location_city_id="city",
        unit_type=models.UnitType.SOLDIER, count=10,
        owner_character_id="ally")
    return state


def _reconcile_lapse(state: models.GameState) -> None:
    territory.reconcile_occupations(state)
    assert "city" not in state.factions["p2"].secured_city_ids


def _attack_order(target_faction_id: str, target_character_id: str,
                  target_name: str) -> orders.AttackOrder:
    return orders.AttackOrder(
        player_id="p1", actor_id="a", location_city_id="city",
        target_faction_id=target_faction_id,
        target_character_id=target_character_id,
        target_name=target_name, definitely=True)


def _attack_secure_orders(include_tax: bool = False,
                          include_fortify: bool = False,
                          clear_sovereign: bool = False):
    """
    p1's invasion programme: beat the defenders down, then write SECURE.

    Occupation may only be *established* where nobody else is left standing
    inside under arms, so a run meant to end in occupation has to clear the
    sovereign's own garrison as well as the sitting occupier's. Tests about a
    failed or costly attack leave ``clear_sovereign`` off and expect no
    occupation.
    """
    result = [_attack_order("p2", "b", "Occupier")]
    if clear_sovereign:
        result.append(_attack_order("p3", "ally", "Ally"))
    result.append(orders.SecureOrder(player_id="p1", actor_id="a", city_id="city"))
    if include_tax:
        result.append(orders.TaxOrder(
            player_id="p1", actor_id="a", city_id="city", duration_days=7))
    if include_fortify:
        result.append(orders.FortifyOrder(
            player_id="p1", actor_id="a", city_id="city", percent=10))
    return result


def test_occupation_lapses_after_final_group_voluntarily_leaves(occupation_state):
    state = occupation_state
    move = orders.MoveOrder(
        player_id="p2", actor_id="b", destination_city_id="home")
    state, _ = engine.run_turn(state, {"p2": [move]}, seed=1)
    assert state.characters["b"].location_city_id == "home"
    assert state.factions["p2"].secured_city_ids == set()


def test_occupation_lapses_after_final_character_retreats_outside(occupation_state):
    occupation_state.characters["b"].location_position = models.LocationPosition.OUTSIDE
    _reconcile_lapse(occupation_state)


@pytest.mark.parametrize("change", ["death", "capture"])
def test_occupation_lapses_when_final_character_is_removed(occupation_state, change):
    character = occupation_state.characters["b"]
    if change == "death":
        character.is_dead = True
    else:
        character.is_prisoner = True
        character.captor_id = "a"
    _reconcile_lapse(occupation_state)


def test_capture_pipeline_lapses_final_characters_occupation(occupation_state):
    capture = orders.CaptureOrder(
        player_id="p1", actor_id="a", target_ids=["b"],
        target_names=["Occupier"])
    state, _ = engine.run_turn(occupation_state, {"p1": [capture]}, seed=1)
    assert state.characters["b"].is_prisoner
    assert state.factions["p2"].secured_city_ids == set()


def test_occupation_lapses_when_all_ordinary_soldiers_die(occupation_state):
    occupation_state.unit_stacks["b_garrison"].count = 0
    _reconcile_lapse(occupation_state)


def test_later_transfer_out_of_local_group_lapses_occupation(occupation_state):
    state = occupation_state
    give = orders.AssignOrder(
        player_id="p2", donor_id="b", recipient_id="a",
        unit_type="SOLDIER", unit_count=10)
    state, _ = engine.run_turn(state, {"p2": [give]}, seed=1)
    assert state.factions["p2"].secured_city_ids == set()


def test_unclaimed_city_keeps_existing_open_recruitment_behavior(
        occupation_state):
    state = occupation_state
    state.world_map.cities["open"] = models.City(
        id="open", name="Open", population_band=models.PopulationBand.SMALL)
    state.characters["a"].location_city_id = "open"
    state.characters["a"].gold = 1000
    recruit = orders.RecruitOrder(
        player_id="p1", actor_id="a", city_id="open",
        unit_type="soldier", count=1)
    state, log = engine.run_turn(state, {"p1": [recruit]}, seed=1)
    assert any(stack.faction_id == "p1" and stack.location_city_id == "open"
               and stack.count == 1 for stack in state.unit_stacks.values())
    assert any(event.event_type == "recruit"
               for event in log.get_player_events("p1"))


@pytest.mark.parametrize("replacement", ["elite", "summoned", "allied"])
def test_nonqualifying_forces_do_not_maintain_occupation(
        occupation_state, replacement):
    state = occupation_state
    del state.unit_stacks["b_garrison"]
    if replacement == "elite":
        state.elite_units["elite"] = models.EliteUnit(
            id="elite", name="Guard", faction_id="p2",
            leader_character_id="b", location_city_id="city", size=100)
    elif replacement == "summoned":
        state.summoned_creatures["summon"] = models.SummonedCreature(
            id="summon", summoner_id="b", creature_type=models.CreatureType.DRAGON,
            count=1, expires_turn=10)
    else:
        state.unit_stacks["allied"] = models.UnitStack(
            id="allied", faction_id="p3", location_city_id="city",
            unit_type=models.UnitType.SOLDIER, count=100,
            owner_character_id="ally")
    _reconcile_lapse(state)


def test_different_same_faction_local_character_can_maintain_occupation(
        occupation_state):
    state = occupation_state
    state.characters["b"].is_dead = True
    state.characters["other"] = models.Character(
        id="other", name="Other", faction_id="p2", location_city_id="city")
    state.unit_stacks["b_garrison"].owner_character_id = "other"
    territory.reconcile_occupations(state)
    assert state.factions["p2"].secured_city_ids == {"city"}


def test_returning_after_lapse_does_not_restore_occupation(occupation_state):
    state = occupation_state
    state.characters["b"].location_position = models.LocationPosition.OUTSIDE
    _reconcile_lapse(state)
    state.characters["b"].location_position = models.LocationPosition.INSIDE
    territory.reconcile_occupations(state)
    assert state.factions["p2"].secured_city_ids == set()


def test_attack_then_secure_transfers_occupation_in_one_batch(occupation_state):
    state, _ = engine.run_turn(
        occupation_state,
        {"p1": _attack_secure_orders(clear_sovereign=True)}, seed=1)
    assert state.factions["p1"].secured_city_ids == {"city"}
    assert state.factions["p2"].secured_city_ids == set()
    assert state.factions["p3"].controlled_city_ids == {"city"}


def test_failed_attack_leaves_valid_defender_occupation(occupation_state):
    state = occupation_state
    state.unit_stacks["a_army"].count = 1
    state.unit_stacks["b_garrison"].count = 1000
    state, _ = engine.run_turn(state, {"p1": _attack_secure_orders()}, seed=1)
    assert state.factions["p2"].secured_city_ids == {"city"}
    assert state.factions["p1"].secured_city_ids == set()


def test_winning_without_surviving_secure_actor_cannot_occupy(
        occupation_state, monkeypatch):
    original = combat_phase.apply_casualties

    def kill_attacker(faction_id, city_id, rate, state, rng, member_ids=None):
        losses = original(faction_id, city_id, rate, state, rng, member_ids)
        if faction_id == "p1":
            state.characters["a"].is_dead = True
        return losses

    monkeypatch.setattr(combat_phase, "apply_casualties", kill_attacker)
    state, _ = engine.run_turn(
        occupation_state, {"p1": _attack_secure_orders()}, seed=1)
    assert state.factions["p1"].secured_city_ids == set()


def test_winning_without_surviving_ordinary_soldiers_cannot_occupy(
        occupation_state, monkeypatch):
    original = combat_phase.apply_casualties

    def remove_attackers(faction_id, city_id, rate, state, rng, member_ids=None):
        losses = original(faction_id, city_id, rate, state, rng, member_ids)
        if faction_id == "p1":
            state.unit_stacks.pop("a_army", None)
        return losses

    monkeypatch.setattr(combat_phase, "apply_casualties", remove_attackers)
    state, _ = engine.run_turn(
        occupation_state, {"p1": _attack_secure_orders()}, seed=1)
    assert state.factions["p1"].secured_city_ids == set()


def test_secure_contention_leaves_a_crowded_city_unoccupied(occupation_state):
    """
    Nobody wins a race that is not being run.

    Both factions stand armed inside, so neither may establish occupation, and
    the city stays unoccupied until one of them is displaced. There is no
    tie-break to lose: writing SECURE first is not an achievement.
    """
    state = occupation_state
    state.factions["p2"].secured_city_ids.clear()
    first = orders.SecureOrder(player_id="p1", actor_id="a", city_id="city")
    second = orders.SecureOrder(player_id="p2", actor_id="b", city_id="city")
    state, log = engine.run_turn(state, {"p1": [first], "p2": [second]}, seed=1)
    assert state.factions["p1"].secured_city_ids == set()
    assert state.factions["p2"].secured_city_ids == set()
    assert territory.occupying_faction_id(state, "city") is None
    failed = [event for event in log.events
              if event.event_type == "secure_failed"]
    assert {event.player_id for event in failed} == {"p1", "p2"}


def test_reconciliation_normalizes_legacy_duplicate_occupations(
        occupation_state):
    state = occupation_state
    state.factions["p1"].secured_city_ids.add("city")
    territory.reconcile_occupations(state)
    assert state.factions["p1"].secured_city_ids == {"city"}
    assert state.factions["p2"].secured_city_ids == set()


def test_foreign_force_can_move_inside_occupied_city(occupation_state):
    state = occupation_state
    state.characters["a"].location_city_id = "home"
    state.unit_stacks["a_army"].location_city_id = "home"
    move = orders.MoveOrder(
        player_id="p1", actor_id="a", destination_city_id="city",
        destination_position="inside")
    state, _ = engine.run_turn(state, {"p1": [move]}, seed=1)
    assert state.characters["a"].location_city_id == "city"
    assert state.characters["a"].location_position == models.LocationPosition.INSIDE
    assert state.factions["p2"].secured_city_ids == {"city"}


def test_new_occupation_can_tax_later_in_same_batch(occupation_state):
    occupation_state.tax_pools["city"] = 500
    state, log = engine.run_turn(
        occupation_state,
        {"p1": _attack_secure_orders(include_tax=True, clear_sovereign=True)},
        seed=1)
    assert state.factions["p1"].secured_city_ids == {"city"}
    assert any(event.event_type == "tax_success"
               for event in log.get_player_events("p1"))


def test_move_recruit_attack_secure_cannot_recruit_future_occupation(
        occupation_state):
    state = occupation_state
    state.characters["a"].location_city_id = "home"
    state.unit_stacks["a_army"].location_city_id = "home"
    before = sum(stack.count for stack in state.unit_stacks.values()
                 if stack.faction_id == "p1")
    program = [
        orders.MoveOrder(player_id="p1", actor_id="a", destination_city_id="city"),
        orders.RecruitOrder(
            player_id="p1", actor_id="a", city_id="city",
            unit_type="soldier", count=10),
        *_attack_secure_orders(clear_sovereign=True),
    ]
    state, log = engine.run_turn(state, {"p1": program}, seed=1)
    after = sum(stack.count for stack in state.unit_stacks.values()
                if stack.faction_id == "p1")
    assert after <= before
    assert any(event.event_type == "recruit_failed"
               for event in log.get_player_events("p1"))
    assert state.factions["p1"].secured_city_ids == {"city"}


def test_valid_foreign_occupier_can_recruit_on_a_later_turn(occupation_state):
    recruit = orders.RecruitOrder(
        player_id="p2", actor_id="b", city_id="city",
        unit_type="soldier", count=1)
    state, log = engine.run_turn(occupation_state, {"p2": [recruit]}, seed=1)
    assert any(stack.faction_id == "p2" and stack.count == 1
               for stack in state.unit_stacks.values())
    assert any(event.event_type == "recruit"
               for event in log.get_player_events("p2"))


def test_valid_occupier_gets_fortification_benefit(occupation_state):
    state = occupation_state
    occupied = combat.calculate_faction_power("p2", "city", state)
    state.world_map.cities["city"].fortification_level = 0
    unfortified = combat.calculate_faction_power("p2", "city", state)
    assert occupied == pytest.approx(unfortified * 1.5)


def test_sovereign_gets_fortification_without_valid_foreign_occupier(
        occupation_state):
    state = occupation_state
    state.factions["p2"].secured_city_ids.clear()
    fortified = combat.calculate_faction_power("p3", "city", state)
    state.world_map.cities["city"].fortification_level = 0
    unfortified = combat.calculate_faction_power("p3", "city", state)
    assert fortified == pytest.approx(unfortified * 1.5)


def test_new_occupier_can_fortify_later_in_same_batch(occupation_state):
    occupation_state.characters["a"].resources["stone"] = 20
    state, log = engine.run_turn(
        occupation_state,
        {"p1": _attack_secure_orders(include_fortify=True,
                                     clear_sovereign=True)}, seed=1)
    assert state.world_map.cities["city"].fortification_level == 60
    assert any(event.event_type == "fortify"
               for event in log.get_player_events("p1"))


def test_combat_uses_one_fortification_authority_snapshot(
        occupation_state, monkeypatch):
    state = occupation_state
    state.characters["a2"] = models.Character(
        id="a2", name="Second", faction_id="p1", location_city_id="city")
    state.unit_stacks["a2_army"] = models.UnitStack(
        id="a2_army", faction_id="p1", location_city_id="city",
        unit_type=models.UnitType.SOLDIER, count=100,
        owner_character_id="a2")
    seen_defender_power = []

    def fixed_result(self, attacker_id, defender_id, attacker_power, defender_power):
        seen_defender_power.append(defender_power)
        return CombatResult(
            attacker_id=attacker_id, defender_id=defender_id,
            winner_id=attacker_id, loser_id=defender_id,
            attacker_power=attacker_power, defender_power=defender_power,
            attacker_casualties=0.0, defender_casualties=0.0)

    calls = 0

    def invalidate_after_first(faction_id, city_id, rate, game_state, rng,
                               member_ids=None):
        nonlocal calls
        if faction_id == "p2":
            calls += 1
            if calls == 1:
                game_state.characters["b"].location_position = (
                    models.LocationPosition.OUTSIDE)
        return {"units": 0, "ships": 0, "characters_wounded": 0,
                "characters_killed": 0}

    monkeypatch.setattr(combat_phase.CombatResolver, "resolve_combat", fixed_result)
    monkeypatch.setattr(combat_phase, "apply_casualties", invalidate_after_first)
    attacks = [
        orders.AttackOrder(
            player_id="p1", actor_id=actor_id, location_city_id="city",
            target_faction_id="p2", target_character_id="b",
            target_name="Occupier", definitely=True)
        for actor_id in ("a", "a2")
    ]
    engine.run_turn(state, {"p1": attacks}, seed=1)
    assert len(seen_defender_power) == 2
    # The first defeat drops morale from 100 to 85, but the foreign occupier's
    # start-of-combat fort multiplier remains for the second resolution.
    assert seen_defender_power[1] == pytest.approx(seen_defender_power[0] * 0.85)
    assert seen_defender_power[0] > 10
