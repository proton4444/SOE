"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

from spoils_engine.models import (
    GameState, Character, SummonedCreature, CreatureType, ItemType,
    credit_gold,
)
from spoils_engine.orders import (
    Order, TeleportOrder, FlyOrder, HealOrder,
    SummonOrder, PrayOrder, BlessOrder, CurseOrder, ResurrectOrder,
    ScryOrder, ConjureOrder, ChargeOrder, AbsorbOrder,
)
from spoils_engine import config, encumbrance, items
from spoils_engine.turn_log import TurnLog
from spoils_engine.phases.common import allocate_id


def process_magic(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                  turn_log: TurnLog, rng: random.Random):
    """Process magic and healing orders."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            # Process Teleport
            if isinstance(order, TeleportOrder):
                if order.warnings:
                    continue

                wizard = game_state.characters.get(order.actor_id)
                target = game_state.characters.get(order.target_character_id)
                dest_city = game_state.world_map.cities.get(order.destination_city_id)

                if not wizard or not target or not dest_city:
                    continue

                # rules.md: the power needed "is equal to the total encumbrance
                # of the group (rounded up)", and "The TELEPORT command has no
                # limit on distance ... he may teleport to anywhere on the
                # planet." Distance plays no part -- an island with no overland
                # route is as cheap to reach as the next town.
                power_cost = encumbrance.teleport_power_cost(target, game_state)

                # Crystals are tapped before the caster's own power, and a
                # named wand supplies both skill and power on its own.
                error = items.pay_for_spell(wizard, power_cost, "teleport",
                                            order.wand_name, game_state)
                if error:
                    order.warnings.append(error)
                    turn_log.add("magic", player_id, "teleport_failed",
                                f"{wizard.name} cannot teleport {target.name}: {error}",
                                character_id=wizard.id, success=False)
                    continue

                # Teleport target
                old_city = game_state.world_map.cities[target.location_city_id]
                target.location_city_id = order.destination_city_id

                turn_log.add("magic", player_id, "teleport",
                            f"{wizard.name} teleported {target.name} from {old_city.name} to {dest_city.name}",
                            location=dest_city.id, character_id=wizard.id)

            # Process Fly
            elif isinstance(order, FlyOrder):
                if order.warnings:
                    continue

                wizard = game_state.characters.get(order.actor_id)
                dest_city = game_state.world_map.cities.get(order.destination_city_id)

                if not wizard or not dest_city:
                    continue

                # rules.md: "The magical power needed to fly is one-fifth (1/5)
                # of the total encumbrance of the group (rounded up)". Flight is
                # crow-flight "over any terrain, including bodies of water", so
                # no route is consulted.
                power_cost = encumbrance.fly_power_cost(wizard, game_state)

                error = items.pay_for_spell(wizard, power_cost, "fly",
                                            order.wand_name, game_state)
                if error:
                    order.warnings.append(error)
                    turn_log.add("magic", player_id, "fly_failed",
                                f"{wizard.name} cannot fly: {error}",
                                character_id=wizard.id, success=False)
                    continue

                # Fly the wizard
                old_city = game_state.world_map.cities[wizard.location_city_id]
                wizard.location_city_id = order.destination_city_id

                turn_log.add("magic", player_id, "fly",
                            f"{wizard.name} flew from {old_city.name} to {dest_city.name}",
                            location=dest_city.id, character_id=wizard.id)

            # Process Heal
            elif isinstance(order, HealOrder):
                if order.warnings:
                    continue

                healer = game_state.characters.get(order.actor_id)
                if not healer or healer.religion_skill <= 0:
                    turn_log.add("magic", player_id, "heal_failed",
                                "Healer has no religion skill",
                                character_id=order.actor_id, success=False)
                    continue

                # Process each target
                for target_id in order.target_character_ids:
                    target = game_state.characters.get(target_id)
                    if not target:
                        continue

                    # Check if at same location
                    if target.location_city_id != healer.location_city_id:
                        turn_log.add("magic", player_id, "heal_failed",
                                    f"{healer.name}: {target.name} is not at the same location",
                                    character_id=healer.id, success=False)
                        continue

                    # Calculate heal amount
                    if target_id in order.heal_to_levels:
                        desired_level = min(100, order.heal_to_levels[target_id])
                        heal_amount = max(0, desired_level - target.health)
                    elif target_id in order.heal_amounts:
                        heal_amount = order.heal_amounts[target_id]
                    else:
                        heal_amount = 100 - target.health  # Heal to full

                    # Check religious power
                    if healer.religious_power_current < heal_amount:
                        heal_amount = healer.religious_power_current

                    if heal_amount <= 0:
                        continue

                    # Apply healing
                    old_health = target.health
                    target.health = min(100, target.health + heal_amount)
                    healer.religious_power_current -= heal_amount

                    if target.health > 0:
                        target.is_dead = False

                    turn_log.add("magic", player_id, "heal",
                                f"{healer.name} healed {target.name} from {old_health} to {target.health}",
                                location=healer.location_city_id, character_id=healer.id)

            elif isinstance(order, ScryOrder):
                seer = game_state.characters.get(order.actor_id)
                target_city = game_state.world_map.cities.get(order.city_id)
                if not seer or not target_city:
                    continue

                power_cost = 3
                if not items.spend_magic_power(seer, power_cost, game_state):
                    turn_log.add("magic", player_id, "scry_failed",
                                f"{seer.name} lacks magic power to scry {target_city.name}",
                                character_id=seer.id, success=False)
                    continue

                defenders = game_state.get_faction_units_at_city(seer.faction_id, target_city.id)
                turn_log.add("magic", player_id, "scry",
                            f"{seer.name} scried {target_city.name}: spotted {len(defenders)} friendly unit stacks",
                            location=target_city.id, character_id=seer.id)


def process_summon(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process SUMMON orders to create magical creatures."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, SummonOrder):
                continue

            if order.warnings:
                continue

            summoner = game_state.characters.get(order.summoner_id)
            if not summoner or summoner.is_dead:
                continue

            # Calculate total magic power needed
            total_cost = 0
            creature_costs = {
                'skeleton': 1, 'zombie': 2, 'harpy': 5, 'minotaur': 10,
                'griffin': 20, 'chimera': 30, 'dragon': 40, 'demon': 50
            }

            for creature_type, count in order.creature_counts.items():
                cost_per = creature_costs.get(creature_type, 0)
                total_cost += cost_per * count

            # Pay for the summoning: a named wand on its own, otherwise
            # crystals first and then the summoner's own power.
            error = items.pay_for_spell(summoner, total_cost, "summon",
                                        order.wand_name, game_state)
            if error:
                turn_log.add("summon", player_id, "summon_failed",
                            f"{summoner.name} cannot summon: {error}",
                            character_id=summoner.id, success=False)
                continue

            # Create creatures
            for creature_type, count in order.creature_counts.items():
                # Convert string to CreatureType enum
                try:
                    creature_enum = CreatureType[creature_type.upper()]
                except KeyError:
                    continue

                creature_id = allocate_id(game_state.summoned_creatures, "creature")
                new_creature = SummonedCreature(
                    id=creature_id,
                    summoner_id=summoner.id,
                    creature_type=creature_enum,
                    count=count,
                    expires_turn=0  # Alpha: never expires (simplified)
                )

                game_state.summoned_creatures[creature_id] = new_creature

                turn_log.add("summon", player_id, "summon_success",
                            f"{summoner.name}: summoned {count} {creature_type}(s) (cost {creature_costs.get(creature_type, 0) * count})",
                            character_id=summoner.id)


def process_religion(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog, rng: random.Random):
    """Process PRAY/BLESS/CURSE/RESURRECT orders."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if order.warnings:
                continue  # Skip invalid orders

            if isinstance(order, PrayOrder):
                priest = game_state.characters.get(order.actor_id)
                if not priest or priest.religion_skill <= 0:
                    continue
                tithe = max(1, priest.religion_skill // 5)
                credit_gold(priest, tithe)
                turn_log.add("religion", player_id, "pray",
                            f"{priest.name} prayed for {order.intent or 'aid'} and received {tithe}g in donations",
                            character_id=priest.id)

            elif isinstance(order, BlessOrder):
                priest = game_state.characters.get(order.actor_id)
                if not priest or priest.religion_skill <= 0:
                    continue
                city_id = order.city_id or priest.location_city_id
                game_state.location_blessings[city_id] = max(game_state.location_blessings.get(city_id, 0), order.bonus)
                city_name = game_state.world_map.cities.get(city_id).name if city_id in game_state.world_map.cities else city_id
                turn_log.add("religion", player_id, "bless",
                            f"{priest.name} blessed {city_name} (+{order.bonus}% power)",
                            location=city_id, character_id=priest.id)

            elif isinstance(order, CurseOrder):
                priest = game_state.characters.get(order.actor_id)
                if not priest or priest.religion_skill <= 0:
                    continue
                city_id = order.city_id or priest.location_city_id
                game_state.location_curses[city_id] = max(game_state.location_curses.get(city_id, 0), order.penalty)
                city_name = game_state.world_map.cities.get(city_id).name if city_id in game_state.world_map.cities else city_id
                turn_log.add("religion", player_id, "curse",
                            f"{priest.name} cursed {city_name} (-{order.penalty}% enemy power)",
                            location=city_id, character_id=priest.id)

            elif isinstance(order, ResurrectOrder):
                priest = game_state.characters.get(order.actor_id)
                target = game_state.characters.get(order.target_id)
                if not priest or not target or not target.is_dead:
                    continue
                chance = min(0.9, priest.religion_skill / 100)
                if rng.random() <= chance:
                    target.is_dead = False
                    target.health = max(50, target.health)
                    turn_log.add("religion", player_id, "resurrect",
                                f"{priest.name} resurrected {target.name}",
                                character_id=priest.id)
                else:
                    turn_log.add("religion", player_id, "resurrect_failed",
                                f"{priest.name} failed to resurrect {target.name}",
                                character_id=priest.id, success=False)

def process_conjure(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                    turn_log: TurnLog, rng: random.Random):
    """
    CONJURE a magical item for temporary use.

    rules.md: needs magic skill 25. The spell spends *all* the caster's power,
    including anything in their crystals, and the chance of success as a
    percentage equals the power expended — so a caster at 62 power burns all 62
    for a 62% chance. A conjured item lasts about as many days as the power
    that bought it.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, ConjureOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue

            skill = actor.effective_skill(actor.magic_skill)
            if skill < config.CONJURE_MIN_MAGIC_SKILL:
                turn_log.add("magic", player_id, "conjure_failed",
                            f"{actor.name} needs magic skill "
                            f"{config.CONJURE_MIN_MAGIC_SKILL} to CONJURE "
                            f"(has {skill})",
                            character_id=actor.id, success=False)
                continue

            power = items.available_magic_power(actor, game_state)
            if power <= 0:
                turn_log.add("magic", player_id, "conjure_failed",
                            f"{actor.name} has no magic power to spend on a "
                            f"conjuration",
                            character_id=actor.id, success=False)
                continue

            # All of it, win or lose.
            items.spend_magic_power(actor, power, game_state)

            if rng.random() * 100.0 >= power:
                turn_log.add("magic", player_id, "conjure_failed",
                            f"{actor.name}'s conjuration failed "
                            f"({power} power spent for a {power}% chance)",
                            character_id=actor.id, success=False)
                continue

            # "the item will remain ... a number of days approximately equal to
            # the power expended". Turns are the engine's finest clock, so the
            # day count rounds up to whole turns.
            turns = max(1, math.ceil(power / config.DAYS_PER_TURN))
            conjured = items.make_item(
                game_state, rng, ItemType(order.item_type),
                holder_id=actor.id,
                expires_turn=game_state.turn_number + turns,
                skill=order.skill, spell=order.spell,
            )
            turn_log.add("magic", player_id, "conjure",
                        f"{actor.name} conjured "
                        f"{items.describe(conjured, game_state)} "
                        f"({power} power spent)",
                        character_id=actor.id, location=actor.location_city_id)


def _reachable_item(actor: Character, target, game_state: GameState,
                    verb: str) -> Tuple[object, str]:
    """
    Resolve one CHARGE/ABSORB target to an item the actor may act on.

    Returns (item, error); exactly one is meaningful. Shared by both verbs
    because the rules give them the same reach and the same item-kind test.
    """
    item = game_state.magical_items.get(target.item_id)
    if not item:
        return None, f"{target.item_name} is no longer anywhere to be found"
    if not item.holds_power:
        return None, (f"{item.name} is a {item.item_type.value} and holds no "
                      f"power, so it cannot be {verb}")
    if not items.can_reach_item(actor, item, game_state):
        return None, (f"{actor.name} cannot reach {item.name}: its holder is "
                      f"not here")
    return item, ""


def process_charge(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                   turn_log: TurnLog):
    """
    CHARGE/RECHARGE: move magic power from a magic-user into an item.

    rules.md: only magic power transfers, never religious power, and the
    charger needs magic skill of at least 1. `by N` adds N, `to N` tops the
    item up to N, and no quantity means as much as the caster can spare.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, ChargeOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue
            if actor.magic_skill < 1:
                turn_log.add("magic", player_id, "charge_failed",
                            f"{actor.name} has no magic skill and cannot "
                            f"charge a magical item",
                            character_id=actor.id, success=False)
                continue

            for target in order.targets:
                item, error = _reachable_item(actor, target, game_state, "charged")
                if error:
                    turn_log.add("magic", player_id, "charge_failed", error,
                                character_id=actor.id, success=False)
                    continue

                if target.amount < 0:
                    wanted = actor.magic_power_current
                elif target.to_level:
                    wanted = target.amount - item.power_current
                else:
                    wanted = target.amount

                # Charging draws on the caster's own power only: pushing power
                # from one crystal into another through its owner is not a
                # transfer rules.md contemplates.
                moved = max(0, min(wanted, actor.magic_power_current,
                                   item.power_headroom))
                if moved <= 0:
                    turn_log.add("magic", player_id, "charge_failed",
                                f"{actor.name} cannot add power to {item.name} "
                                f"(has {actor.magic_power_current}, item holds "
                                f"{item.power_current})",
                                character_id=actor.id, success=False)
                    continue

                actor.magic_power_current -= moved
                item.power_current += moved
                turn_log.add("magic", player_id, "charge",
                            f"{actor.name} charged {item.name} by {moved} power "
                            f"({items.describe(item, game_state)})",
                            character_id=actor.id,
                            location=actor.location_city_id)


def process_absorb(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                   turn_log: TurnLog):
    """
    ABSORB: move magic power from an item back into a magic-user.

    The mirror of CHARGE. A character cannot absorb past their own natural
    maximum, since that is the ceiling their power obeys everywhere else.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, AbsorbOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue
            if actor.magic_skill < 1:
                turn_log.add("magic", player_id, "absorb_failed",
                            f"{actor.name} has no magic skill and cannot "
                            f"absorb magic power",
                            character_id=actor.id, success=False)
                continue

            for target in order.targets:
                item, error = _reachable_item(actor, target, game_state, "absorbed from")
                if error:
                    turn_log.add("magic", player_id, "absorb_failed", error,
                                character_id=actor.id, success=False)
                    continue

                headroom = actor.max_magic_power - actor.magic_power_current
                wanted = item.power_current if target.amount < 0 else target.amount
                moved = max(0, min(wanted, item.power_current, headroom))
                if moved <= 0:
                    turn_log.add("magic", player_id, "absorb_failed",
                                f"{actor.name} absorbed nothing from {item.name} "
                                f"(item holds {item.power_current}, "
                                f"{actor.name} is at {actor.magic_power_current}/"
                                f"{actor.max_magic_power})",
                                character_id=actor.id, success=False)
                    continue

                item.power_current -= moved
                actor.magic_power_current += moved
                turn_log.add("magic", player_id, "absorb",
                            f"{actor.name} absorbed {moved} power from "
                            f"{item.name} ({items.describe(item, game_state)})",
                            character_id=actor.id,
                            location=actor.location_city_id)


def process_magic_free_zones(game_state: GameState, turn_log: TurnLog):
    """
    Drain everyone standing in a magic-free location, and their items with them.

    rules.md: in such a place magical power "does not exist, either in people
    or in magical items", and entering one drains a character instantly. This
    runs as one sweep after all movement rather than on each way of arriving,
    so walking, sailing, flying and being teleported in are all caught.
    """
    for character in game_state.characters.values():
        if character.is_dead:
            continue
        city = game_state.world_map.cities.get(character.location_city_id)
        if not city or not city.is_magic_free:
            continue
        if items.drain_magic_free_zone(character, game_state):
            turn_log.add("magic", character.faction_id, "magic_drained",
                        f"{character.name}'s magic power drained away in "
                        f"{city.name}",
                        character_id=character.id, location=city.id,
                        success=False)


def process_item_upkeep(game_state: GameState, turn_log: TurnLog):
    """
    End-of-turn item bookkeeping: regenerate power, retire conjured items.

    rules.md promises "You will be notified when a magical item disappears",
    so every expiry is logged to the faction that held it.
    """
    items.regenerate(game_state)
    for item, faction_id in items.expire(game_state):
        if not faction_id:
            continue
        turn_log.add("magic", faction_id, "item_expired",
                    f"{item.name} has returned to whence it came")

