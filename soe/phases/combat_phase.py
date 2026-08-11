"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Dict, List

from soe.models import (
    GameState, Character, LocationPosition,
)
from soe import groups, territory
from soe.orders import (
    Order, AttackOrder,
)
from soe.combat import CombatResolver, calculate_faction_power, apply_casualties
from soe.turn_log import TurnLog


def defending_side(defender_id: str, attacker_id: str, city_id: str,
                   game_state: GameState) -> List[str]:
    """
    Factions that fight alongside the defender at a location.

    An ally joins only if it actually has fighting strength present, so a lone
    envoy is not dragged into a battle it cannot influence. A faction allied to
    both combatants stays out rather than fighting itself.
    """
    side = [defender_id]
    defender = game_state.factions.get(defender_id)
    if not defender:
        return side

    for ally_id in sorted(defender.allies):
        if ally_id in (defender_id, attacker_id):
            continue
        ally = game_state.factions.get(ally_id)
        if not ally or attacker_id in ally.allies:
            continue
        if calculate_faction_power(ally_id, city_id, game_state) > 0:
            side.append(ally_id)

    return side


def supporting_side(attacker: Character, city_id: str,
                    game_state: GameState) -> List[str]:
    """
    Other factions whose characters have agreed to fight alongside this attacker.

    Design: a supporter joins "as if they had given the same ATTACK/CAPTURE
    order at exactly the same time", but stays a separate group. Their strength
    is summed per faction rather than merged, which is what the rules mean by
    combat leadership being "limited to a single group" -- the supporter's
    leadership lifts their own people and nobody else's.
    """
    extra: List[str] = []

    for char in game_state.characters.values():
        if char.supporting_id != attacker.id:
            continue
        if char.location_city_id != city_id or char.is_dead or char.is_prisoner:
            continue
        if char.faction_id == attacker.faction_id or char.faction_id in extra:
            continue
        if calculate_faction_power(char.faction_id, city_id, game_state) > 0:
            extra.append(char.faction_id)

    return sorted(extra)


def process_combat(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                   turn_log: TurnLog, rng: random.Random,
                   fortification_authority: dict[str, str | None] | None = None):
    """Process combat orders using CombatResolver."""
    if fortification_authority is None:
        territory.reconcile_occupations(game_state)
        fortification_authority = territory.administrative_snapshot(game_state)

    # Group attacks by location.
    #
    # An attack happens wherever its attacker is standing when combat resolves,
    # not where they stood when the order was read. "Go to Redport and attack
    # Aurelia" is parsed while the character is still in Ashford, and movement
    # runs two phases earlier; freezing the parse-time city sent the battle to
    # the wrong town. A march that failed leaves the attacker at home, and the
    # attack is then fought there -- and finds nobody -- rather than pretending
    # the move succeeded.
    attacks_by_location = defaultdict(list)

    for player_id, orders in orders_by_player.items():
        for order in orders:
            if isinstance(order, AttackOrder) and not order.warnings:
                attacker = game_state.characters.get(order.actor_id)
                if attacker and attacker.location_city_id:
                    # Keep the order agreeing with the report of it.
                    order.location_city_id = attacker.location_city_id
                attacks_by_location[order.location_city_id].append((player_id, order))

    # Initialize combat resolver
    resolver = CombatResolver(rng)

    # Process each battle
    for city_id, attacks in attacks_by_location.items():
        city = game_state.world_map.cities.get(city_id)
        if not city:
            continue

        for attacker_player_id, attack_order in attacks:
            attacker = game_state.characters.get(attack_order.actor_id)
            if not attacker:
                continue

            # Find defender faction
            defender_faction_id = attack_order.target_faction_id
            if not defender_faction_id:
                turn_log.add("combat", attacker_player_id, "attack_failed",
                            f"{attacker.name} found no valid target in {city.name}",
                            location=city_id, character_id=attacker.id, success=False)
                continue

            # ATTACK requires the target to be present: if they are not,
            # no attack takes place.
            #
            # Presence is the gate, and it has to be asked before any strength
            # is counted. The old test -- defender_power == 0 -- was never a
            # presence test: unowned stacks bypass the group filter and the
            # defender's allies are added on top, so an absent Aurelia still
            # "lost" a battle to the soldiers she had left behind in Redport,
            # and the report named her as the loser. That also made hidden
            # movement useless: marching out could not evade a targeted attack
            # because whatever stayed behind was fought in her place.
            #
            # Only a named target is gated. An ATTACK that names no character
            # is aimed at a faction, and there is nobody whose absence could
            # call it off.
            if attack_order.target_character_id:
                target = game_state.characters.get(attack_order.target_character_id)
                if not target or target.is_dead or target.location_city_id != city_id:
                    # Says the attack found nobody without saying where they
                    # went -- marching in and looking around reveals this much
                    # and no more.
                    turn_log.add("combat", attacker_player_id, "attack_failed",
                                f"{attacker.name} could not attack: "
                                f"{attack_order.target_name} is not present in "
                                f"{city.name}; no attack takes place",
                                location=city_id, character_id=attacker.id,
                                success=False)
                    continue

            # Calculate powers. The defender's allies present at the location
            # stand with them, so their strength counts and they share the
            # losses.
            # Supporters fight as if they had attacked at the same moment, and
            # cannot also be counted among the defender's allies.
            supporters = supporting_side(attacker, city_id, game_state)
            side = [fid for fid in
                    defending_side(defender_faction_id, attacker_player_id, city_id, game_state)
                    if fid not in supporters]
            attacker_ids = groups.member_ids(attacker, game_state)
            target = game_state.characters.get(attack_order.target_character_id)
            defender_leader = groups.leader_of(target, game_state) if target else None
            defender_ids = (groups.member_ids(defender_leader, game_state)
                            if defender_leader else None)
            attacker_power = calculate_faction_power(
                attacker_player_id, city_id, game_state, attacker_ids,
                fortification_authority)
            attacker_power += sum(
                calculate_faction_power(
                    fid, city_id, game_state,
                    fortification_authority=fortification_authority,
                ) for fid in supporters
            )
            defender_power = calculate_faction_power(
                defender_faction_id, city_id, game_state, defender_ids,
                fortification_authority)
            defender_power += sum(
                calculate_faction_power(
                    fid, city_id, game_state,
                    fortification_authority=fortification_authority,
                ) for fid in side[1:]
            )

            # Validate engagement. A named target is already known to be here,
            # so the only thing left to be missing is anything to fight with.
            if defender_power == 0:
                turn_log.add("combat", attacker_player_id, "attack_failed",
                            f"{attacker.name} could not attack: "
                            f"{attack_order.target_name} has no fighting "
                            f"strength in {city.name}",
                            location=city_id, character_id=attacker.id, success=False)
                continue

            minimum_ratio = {
                "cravenly": 2.0, "cautiously": 1.5, "normal": 1.0,
                "bravely": 1 / 1.5, "recklessly": 0.5, "suicidally": 0.2,
            }.get(attack_order.stance, 1.0)
            if (not attack_order.definitely
                    and attacker_power / defender_power < minimum_ratio):
                turn_log.add("combat", attacker_player_id, "attack_declined",
                            f"{attacker.name} declined to attack (odds too poor)",
                            location=city_id, character_id=attacker.id, success=False)
                continue

            # Resolve combat
            result = resolver.resolve_combat(
                attacker_player_id, defender_faction_id,
                attacker_power, defender_power
            )

            # Apply casualties. Supporters bleed for it too.
            attacker_losses = apply_casualties(
                attacker_player_id, city_id, result.attacker_casualties,
                game_state, rng, attacker_ids,
            )
            for supporter_id in supporters:
                supporter_losses = apply_casualties(
                    supporter_id, city_id, result.attacker_casualties, game_state, rng
                )
                turn_log.add("combat", supporter_id, "supported",
                            f"Your forces fought alongside {attacker.name} in {city.name} "
                            f"(lost {supporter_losses['units']} units)",
                            location=city_id)
            defender_losses = {}
            for fid in side:
                defender_losses[fid] = apply_casualties(
                    fid, city_id, result.defender_casualties, game_state, rng,
                    defender_ids if fid == defender_faction_id else None,
                )

            attacker_threshold = {
                "cravenly": 0.0, "cautiously": 0.15, "normal": 0.25,
                "bravely": 0.35, "recklessly": 0.50, "suicidally": 2.0,
            }.get(attack_order.stance, 0.25)
            defender_threshold = (0.50 if attack_order.stance == "suicidally"
                                  else 0.35 if attack_order.stance == "recklessly"
                                  else 0.25)
            attacker_retreats = result.attacker_casualties > attacker_threshold
            defender_retreats = result.defender_casualties > defender_threshold
            if attacker_retreats and defender_retreats:
                attacker_retreats = defender_retreats = False

            def retreat(member_ids: set[str]) -> None:
                for char_id in member_ids:
                    char = game_state.characters.get(char_id)
                    if not char or char.location_city_id != city_id:
                        continue
                    char.location_position = (
                        LocationPosition.OUTSIDE
                        if char.location_position == LocationPosition.INSIDE
                        else LocationPosition.NEAR
                    )

            if attacker_retreats:
                retreat(attacker_ids)
            if defender_retreats and defender_ids:
                retreat(defender_ids)

            for char_id in attacker_ids:
                char = game_state.characters.get(char_id)
                if char:
                    char.morale = max(0, min(150, char.morale +
                                      (5 if result.winner_id == attacker_player_id else -15)))
            for char_id in defender_ids or set():
                char = game_state.characters.get(char_id)
                if char:
                    char.morale = max(0, min(150, char.morale +
                                      (5 if result.winner_id == defender_faction_id else -15)))

            if attacker_retreats or defender_retreats:
                retreating = attacker.name if attacker_retreats else attack_order.target_name
                turn_log.add("combat", attacker_player_id, "retreat",
                             f"{retreating} retreated from {city.name}",
                             location=city_id, character_id=attacker.id)

            # Log results
            allies = [game_state.factions[f].name for f in side[1:] if f in game_state.factions]
            with_allies = f" (aided by {', '.join(allies)})" if allies else ""

            if result.winner_id == attacker_player_id:
                turn_log.add("combat", attacker_player_id, "victory",
                            f"{attacker.name} defeated {attack_order.target_name}{with_allies} "
                            f"in {city.name} (lost {attacker_losses['units']} units)",
                            location=city_id, character_id=attacker.id)
                for fid in side:
                    turn_log.add("combat", fid, "defeat",
                                f"Your forces were defeated by {attacker.name} in {city.name} "
                                f"(lost {defender_losses[fid]['units']} units)",
                                location=city_id)
            else:
                turn_log.add("combat", attacker_player_id, "defeat",
                            f"{attacker.name} was defeated in {city.name} "
                            f"(lost {attacker_losses['units']} units)",
                            location=city_id, character_id=attacker.id)
                for fid in side:
                    turn_log.add("combat", fid, "victory",
                                f"Your forces successfully defended {city.name} "
                                f"(lost {defender_losses[fid]['units']} units)",
                                location=city_id)

