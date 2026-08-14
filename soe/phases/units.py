"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

from typing import Dict, List

from soe.models import (
    GameState, Character, UnitStack, EliteUnit,
    UnitType, debit_gold, credit_gold,
)
from soe.orders import (
    Order, AssignOrder, NameOrder,
    PromoteOrder, WorkOrder, TrainOrder, UnnameOrder, CreateOrder, DisbandOrder,
)
from soe import config, groups, items
from soe.turn_log import TurnLog
from soe.phases.common import allocate_id


def process_work(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """
    Process WORK orders: the actor and their group labour for common wages.

    The daily rate comes from the location's population band (the design: work
    is scarce in lightly populated areas -- TINY towns pay nothing and the
    characters do voluntary community service). High-skill characters sell
    their own skills for a little more.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, WorkOrder):
                continue
            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue
            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            daily = config.WORK_WAGE_DAILY_PER_BAND.get(city.population_band, 0.0)
            workers = groups.group_soldier_count(actor, game_state, UnitType.WORKER)
            wage = daily * order.duration_days * (workers + 1)

            # Design: high-level characters sell their own skills -- but
            # only where there is work to sell it into.
            if daily > 0:
                best_skill = max(actor.combat_skill, actor.magic_skill,
                                 actor.religion_skill, actor.trading_skill,
                                 actor.sailing_skill)
                wage += (best_skill * config.WORK_SKILL_BONUS_PER_LEVEL_PER_DAY
                         * order.duration_days)
            wage = round(wage, 1)

            if wage > 0:
                credit_gold(actor, wage)
                turn_log.add("work", player_id, "work",
                            f"{actor.name} worked {order.duration_days} days in "
                            f"{city.name} and earned {wage}g",
                            location=city.id, character_id=actor.id)
            else:
                turn_log.add("work", player_id, "work_volunteered",
                            f"{actor.name} found no work in {city.name} and "
                            f"did voluntary community service instead",
                            location=city.id, character_id=actor.id)


def process_train(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """
    Process TRAIN orders: convert workers into soldiers or sailors.

    The trainer needs combat skill (soldiers) or sailing skill (sailors) of
    at least 10. the design sizes the work by skill -- a level-50 trainer
    converts 5 workers a week -- so one weekly turn converts what the skill
    supports and the rest stays in the pool for another week. This is the
    engine's turn-granular version of the rules' hours-long training time.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, TrainOrder):
                continue
            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue

            if order.unit_type == "sailor":
                skill = actor.sailing_skill
                skill_name = "sailing"
            else:
                skill = actor.combat_skill
                skill_name = "combat"

            if skill < config.TRAIN_MIN_TRAINER_SKILL:
                turn_log.add("train", player_id, "train_failed",
                            f"{actor.name}: needs {skill_name} skill of at least "
                            f"{config.TRAIN_MIN_TRAINER_SKILL} to train "
                            f"{order.unit_type}s (has {skill})",
                            character_id=actor.id, success=False)
                continue

            available = groups.group_soldier_count(actor, game_state, UnitType.WORKER)
            if available <= 0:
                turn_log.add("train", player_id, "train_failed",
                            f"{actor.name}: no workers in the group to train",
                            character_id=actor.id, success=False)
                continue

            if order.count > 0:
                trainees = min(order.count, available)
            else:
                trainees = available
            trainees = min(trainees, max(1, int(skill * config.TRAIN_WORKERS_PER_WEEK_FROM_SKILL)))

            removed = _remove_group_workers(actor, game_state, trainees)
            if removed <= 0:
                turn_log.add("train", player_id, "train_failed",
                            f"{actor.name}: no workers available to train",
                            character_id=actor.id, success=False)
                continue

            new_type = UnitType.SOLDIER if order.unit_type == "soldier" else UnitType.SAILOR
            _add_group_units(actor, game_state, new_type, removed)
            turn_log.add("train", player_id, "train",
                        f"{actor.name} trained {removed} worker(s) into "
                        f"{order.unit_type}s in one week",
                        location=actor.location_city_id, character_id=actor.id)


def _group_worker_stacks(actor: Character, game_state: GameState) -> List[UnitStack]:
    """Worker stacks the actor's group can draw on: group-owned stacks, then
    unowned faction stacks at the actor's location."""
    member_ids = {m.id for m in [actor] + groups.group_members(actor.id, game_state)}
    owned = [s for s in game_state.unit_stacks.values()
             if s.unit_type == UnitType.WORKER and s.owner_character_id in member_ids]
    if owned:
        return owned
    return [s for s in game_state.unit_stacks.values()
            if s.unit_type == UnitType.WORKER and not s.owner_character_id
            and s.faction_id == actor.faction_id
            and s.location_city_id == actor.location_city_id]


def _remove_group_workers(actor: Character, game_state: GameState, count: int) -> int:
    """Remove up to `count` workers from the actor's group; returns how many
    were actually removed."""
    removed = 0
    for stack in _group_worker_stacks(actor, game_state):
        if removed >= count:
            break
        take = min(stack.count, count - removed)
        stack.count -= take
        removed += take
        if stack.count <= 0:
            del game_state.unit_stacks[stack.id]
    return removed


def _add_group_units(actor: Character, game_state: GameState, unit_type: UnitType, count: int) -> None:
    """Add trained/created units to the actor's group, merging into an
    existing stack they own at the same location."""
    if count <= 0:
        return
    for stack in game_state.unit_stacks.values():
        if (stack.owner_character_id == actor.id and stack.unit_type == unit_type
                and stack.location_city_id == actor.location_city_id):
            stack.count += count
            return
    stack_id = allocate_id(game_state.unit_stacks, "stack")
    game_state.unit_stacks[stack_id] = UnitStack(
        id=stack_id, faction_id=actor.faction_id,
        location_city_id=actor.location_city_id, unit_type=unit_type, count=count,
        owner_character_id=actor.id,
    )


def process_unname(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """
    Process UNNAME orders: convert a named character back to a common worker.

    Per the design the character must be part of a group and have nothing of
    their own; the resulting worker goes to the group leader. The lead
    character cannot be unnamed (that would quit the game; the design treats it
    as the elimination mechanic, which the alpha declines to support).
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, UnnameOrder):
                continue
            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            target = game_state.characters.get(order.target_id)
            if not actor or not target:
                continue
            if target.is_dead:
                continue

            if target.is_leader:
                turn_log.add("unname", player_id, "unname_failed",
                            f"{actor.name}: cannot unname the lead character "
                            f"({target.name}) -- the engine does not support "
                            "quitting the game",
                            character_id=actor.id, success=False)
                continue

            if not target.group_leader_id:
                turn_log.add("unname", player_id, "unname_failed",
                            f"{actor.name}: {target.name} is not part of a "
                            "group and cannot be unnamed",
                            character_id=actor.id, success=False)
                continue

            leader = game_state.characters.get(target.group_leader_id)
            if not leader:
                continue

            if (groups.direct_members(target.id, game_state)
                    or groups.owned_stacks(target.id, game_state)
                    or any(s.owner_character_id == target.id for s in game_state.ships.values())):
                turn_log.add("unname", player_id, "unname_failed",
                            f"{actor.name}: {target.name} still has people, "
                            "units or ships of their own",
                            character_id=actor.id, success=False)
                continue

            # Convert: the character becomes one worker in the leader's group.
            del game_state.characters[target.id]
            for stack in game_state.unit_stacks.values():
                if stack.owner_character_id == leader.id and stack.unit_type == UnitType.WORKER:
                    stack.count += 1
                    break
            else:
                _add_group_units(leader, game_state, UnitType.WORKER, 1)

            turn_log.add("unname", player_id, "unname",
                        f"{actor.name} unnamed {target.name}, who became a "
                        f"worker in {leader.name}'s group",
                        character_id=actor.id)


def process_create(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """
    Process CREATE orders: form an elite troop unit from soldiers.

    The soldiers come from the actor's group. The unit starts at combat level
    1 and trains itself one partial point per turn (see process_elite_upkeep);
    the actor is its group leader.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, CreateOrder):
                continue
            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue

            available = groups.group_soldier_count(actor, game_state, UnitType.SOLDIER)
            if available < order.count:
                turn_log.add("create", player_id, "create_failed",
                            f"{actor.name}: only {available} soldiers in the "
                            f"group (need {order.count})",
                            character_id=actor.id, success=False)
                continue

            removed = 0
            for stack in groups.owned_stacks(actor.id, game_state) + [
                    s for s in game_state.unit_stacks.values()
                    if s.unit_type == UnitType.SOLDIER and not s.owner_character_id
                    and s.faction_id == actor.faction_id
                    and s.location_city_id == actor.location_city_id]:
                if removed >= order.count:
                    break
                if stack.unit_type != UnitType.SOLDIER:
                    continue
                take = min(stack.count, order.count - removed)
                stack.count -= take
                removed += take
                if stack.count <= 0:
                    del game_state.unit_stacks[stack.id]
            if removed <= 0:
                continue

            unit_id = allocate_id(game_state.elite_units, "elite")
            game_state.elite_units[unit_id] = EliteUnit(
                id=unit_id, name=order.unit_name, faction_id=player_id,
                leader_character_id=actor.id, location_city_id=actor.location_city_id,
                size=removed, combat_level=1,
            )
            turn_log.add("create", player_id, "create",
                        f"{actor.name} created elite unit '{order.unit_name}' "
                        f"with {removed} soldiers (combat level 1)",
                        location=actor.location_city_id, character_id=actor.id)

def process_elite_upkeep(game_state: GameState, turn_log: TurnLog) -> None:
    """Elite units train constantly: one partial point per week, with every
    five partial points becoming a combat level."""
    for unit in game_state.elite_units.values():
        unit.partial_level += config.ELITE_PARTIAL_PER_WEEK
        gained = int(unit.partial_level / config.ELITE_PARTIAL_PER_LEVEL)
        if gained > 0:
            unit.partial_level -= gained * config.ELITE_PARTIAL_PER_LEVEL
            unit.combat_level += gained
            leader = game_state.characters.get(unit.leader_character_id)
            turn_log.add("income", unit.faction_id, "elite_training",
                        f"Elite unit '{unit.name}' trained up to combat "
                        f"level {unit.combat_level}",
                        character_id=leader.id if leader else "")


def process_disband(orders_by_player: Dict[str, List[Order]],
                    game_state: GameState, turn_log: TurnLog) -> None:
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, DisbandOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            unit = game_state.elite_units.get(order.elite_unit_id)
            if (not actor or not unit or unit.faction_id != player_id
                    or unit.leader_character_id != actor.id):
                turn_log.add("disband", player_id, "disband_failed",
                             f"{getattr(actor, 'name', 'Character')}: does not lead "
                             f"{order.elite_unit_name}", character_id=order.actor_id,
                             success=False)
                continue
            _add_group_units(actor, game_state, UnitType.SOLDIER, unit.size)
            del game_state.elite_units[unit.id]
            turn_log.add("disband", player_id, "disband",
                         f"{actor.name} disbanded {unit.name}; {unit.size} soldiers "
                         "returned to the group", character_id=actor.id)

def process_assign(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process ASSIGN/GIVE orders for unit/gold transfers."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, AssignOrder):
                continue

            if order.warnings:
                continue

            donor = game_state.characters.get(order.donor_id)
            recipient = game_state.characters.get(order.recipient_id)

            if not donor or not recipient:
                continue

            # Check same location
            if donor.location_city_id != recipient.location_city_id:
                turn_log.add("assign", player_id, "assign_failed",
                            f"{donor.name}: {recipient.name} is not at the same location",
                            character_id=donor.id, success=False)
                continue

            # Transfer gold between character purses (legacy treasury as fall-back)
            if order.gold_amount > 0:
                faction = game_state.factions.get(player_id)
                if debit_gold(donor, faction, order.gold_amount):
                    credit_gold(recipient, order.gold_amount)
                    turn_log.add("assign", player_id, "assign_gold",
                                f"{donor.name} gave {order.gold_amount}g to {recipient.name}",
                                character_id=donor.id)
                else:
                    turn_log.add("assign", player_id, "assign_failed",
                                f"{donor.name}: insufficient gold",
                                character_id=donor.id, success=False)
                    continue

            # Transfer mass resources ("Give 50 armor to Thomas Ames"; a
            # bare "give stone to X" hands over everything the donor holds).
            for kind, wanted in order.resources.items():
                amount = wanted if wanted >= 0 else donor.resources.get(kind, 0)
                if donor.resources.get(kind, 0) < amount:
                    turn_log.add("assign", player_id, "assign_failed",
                                f"{donor.name}: insufficient {kind}",
                                character_id=donor.id, success=False)
                    continue
                donor.resources[kind] = donor.resources.get(kind, 0) - amount
                recipient.resources[kind] = (
                    recipient.resources.get(kind, 0) + amount)
                turn_log.add("assign", player_id, "assign_resource",
                            f"{donor.name} gave {amount} {kind} to {recipient.name}",
                            character_id=donor.id)

            # Hand over magical items. An item is a possession rather than a
            # subordinate, so it may cross faction lines exactly as gold and
            # units do, and it keeps whatever power it was holding.
            for item_id, item_name in zip(order.item_ids, order.item_names):
                item = game_state.magical_items.get(item_id)
                if not item or item.holder_character_id != donor.id:
                    turn_log.add("assign", player_id, "assign_failed",
                                f"{donor.name} is not carrying {item_name}",
                                character_id=donor.id, success=False)
                    continue
                item.holder_character_id = recipient.id
                turn_log.add("assign", player_id, "assign_item",
                            f"{donor.name} gave {items.describe(item, game_state)} "
                            f"to {recipient.name}",
                            character_id=donor.id)

            for unit_id, unit_name in zip(order.elite_unit_ids,
                                          order.elite_unit_names):
                unit = game_state.elite_units.get(unit_id)
                if (not unit or unit.leader_character_id != donor.id
                        or unit.faction_id != player_id):
                    turn_log.add("assign", player_id, "assign_failed",
                                 f"{donor.name} does not lead {unit_name}",
                                 character_id=donor.id, success=False)
                    continue
                if recipient.faction_id != player_id:
                    turn_log.add("assign", player_id, "assign_failed",
                                 f"Elite unit {unit_name} cannot cross factions",
                                 character_id=donor.id, success=False)
                    continue
                unit.leader_character_id = recipient.id
                unit.location_city_id = recipient.location_city_id
                turn_log.add("assign", player_id, "assign_elite",
                             f"{donor.name} assigned {unit.name} to {recipient.name}",
                             character_id=donor.id)

            # Assign named characters into the recipient's group. the design:
            # they keep whoever was assigned to them.
            for cid, cname in zip(order.character_ids, order.character_names):
                subject = game_state.characters.get(cid)
                if not subject or subject.faction_id != player_id:
                    turn_log.add("assign", player_id, "assign_failed",
                                f"{donor.name}: cannot assign {cname}",
                                character_id=donor.id, success=False)
                    continue

                # Units may be given across faction lines, but a character
                # cannot: taking somebody else's people is CAPTURE, not GIVE.
                if recipient.faction_id != player_id:
                    turn_log.add("assign", player_id, "assign_failed",
                                f"{donor.name}: {cname} cannot be assigned to "
                                f"another faction's character",
                                character_id=donor.id, success=False)
                    continue

                refusal = groups.attach(subject, recipient, game_state)
                if refusal:
                    turn_log.add("assign", player_id, "assign_failed",
                                f"{donor.name}: {subject.name} could not be assigned "
                                f"to {recipient.name} - {refusal}",
                                character_id=donor.id, success=False)
                    continue

                turn_log.add("assign", player_id, "assign_character",
                            f"{donor.name} assigned {subject.name} to {recipient.name}'s group",
                            character_id=donor.id)

            # Transfer units
            if order.unit_count > 0 and order.unit_type:
                # The donor's own units first, then the unowned pool standing
                # with them -- recruits land unowned until somebody is given them.
                donor_stack = None
                for stack in game_state.unit_stacks.values():
                    if (stack.faction_id == player_id and
                        stack.location_city_id == donor.location_city_id and
                        stack.unit_type.name == order.unit_type and
                        stack.owner_character_id == donor.id):
                        donor_stack = stack
                        break

                if donor_stack is None or donor_stack.count < order.unit_count:
                    for stack in game_state.unit_stacks.values():
                        if (stack.faction_id == player_id and
                            stack.location_city_id == donor.location_city_id and
                            stack.unit_type.name == order.unit_type and
                            not stack.owner_character_id):
                            donor_stack = stack
                            break

                if not donor_stack:
                    turn_log.add("assign", player_id, "assign_failed",
                                f"{donor.name}: no {order.unit_type.lower()}s available",
                                character_id=donor.id, success=False)
                    continue

                if donor_stack.count < order.unit_count:
                    turn_log.add("assign", player_id, "assign_failed",
                                f"{donor.name}: insufficient {order.unit_type.lower()}s (have {donor_stack.count}, need {order.unit_count})",
                                character_id=donor.id, success=False)
                    continue

                # Transfer units
                donor_stack.count -= order.unit_count

                # Find or create the recipient's stack. Units join the
                # recipient's faction -- GIVE may cross faction lines -- and
                # become theirs, so they travel with them from now on.
                recipient_stack = None
                for stack in game_state.unit_stacks.values():
                    if (stack.faction_id == recipient.faction_id and
                        stack.location_city_id == recipient.location_city_id and
                        stack.unit_type.name == order.unit_type and
                        stack.owner_character_id == recipient.id):
                        recipient_stack = stack
                        break

                if recipient_stack:
                    recipient_stack.count += order.unit_count
                else:
                    # Create new stack for recipient
                    new_stack_id = allocate_id(game_state.unit_stacks, "stack")
                    new_stack = UnitStack(
                        id=new_stack_id,
                        faction_id=recipient.faction_id,
                        location_city_id=recipient.location_city_id,
                        unit_type=UnitType[order.unit_type],
                        count=order.unit_count,
                        owner_character_id=recipient.id,
                    )
                    game_state.unit_stacks[new_stack_id] = new_stack

                # Remove donor stack if empty
                if donor_stack.count <= 0:
                    del game_state.unit_stacks[donor_stack.id]

                turn_log.add("assign", player_id, "assign_units",
                            f"{donor.name} gave {order.unit_count} {order.unit_type.lower()}s to {recipient.name}",
                            character_id=donor.id)


def _nameable_stack(actor, unit_type: str, player_id: str, game_state: GameState):
    """A stack of `unit_type` in the actor's group at their city, or None."""
    city = actor.location_city_id
    members = groups.member_ids(actor, game_state)
    owned = unowned = group_owned = None
    for stack in game_state.unit_stacks.values():
        if (stack.faction_id != player_id
                or stack.unit_type.name != unit_type
                or stack.count <= 0
                or stack.location_city_id != city):
            continue
        if stack.owner_character_id == actor.id:
            owned = stack
            break
        if not stack.owner_character_id and unowned is None:
            unowned = stack
        elif stack.owner_character_id in members and group_owned is None:
            group_owned = stack
    return owned or unowned or group_owned


def process_name(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process NAME orders to convert units to named characters."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, NameOrder):
                continue

            if order.warnings:
                continue

            faction = game_state.factions.get(player_id)
            if not faction:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor:
                turn_log.add("name", player_id, "name_failed",
                            "No actor to name a unit",
                            success=False)
                continue

            unit_stack = _nameable_stack(actor, order.unit_type, player_id, game_state)
            if not unit_stack:
                turn_log.add("name", player_id, "name_failed",
                            f"No {order.unit_type.lower()}s available to name "
                            f"at {actor.name}'s location",
                            success=False)
                continue

            # Check if name already exists
            name_exists = any(char.name.lower() == order.new_name.lower()
                            for char in game_state.characters.values())
            if name_exists:
                turn_log.add("name", player_id, "name_failed",
                            f"Name '{order.new_name}' already exists",
                            success=False)
                continue

            # Deduct 1 unit from stack
            unit_stack.count -= 1

            # Create new character
            new_char_id = allocate_id(game_state.characters, "char")
            new_character = Character(
                id=new_char_id,
                name=order.new_name,
                faction_id=player_id,
                location_city_id=unit_stack.location_city_id,
                gender=order.gender,
                title="",  # No title by default
                combat_skill=5,  # Basic skills for newly named units
                magic_skill=0,
                religion_skill=0,
                health=100,
                is_dead=False
            )

            game_state.characters[new_char_id] = new_character

            # Remove stack if empty
            if unit_stack.count <= 0:
                del game_state.unit_stacks[unit_stack.id]

            turn_log.add("name", player_id, "name_success",
                        f"Named {order.gender} {order.unit_type.lower()} '{order.new_name}'",
                        character_id=new_char_id)


def process_promote(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process PROMOTE orders to change character titles."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, PromoteOrder):
                continue

            if order.warnings:
                continue

            # Promote all characters in the order
            for i, char_id in enumerate(order.character_ids):
                character = game_state.characters.get(char_id)
                if not character:
                    continue

                old_title = character.title if character.title else "(untitled)"
                character.title = order.new_title
                new_title = order.new_title if order.new_title else "(untitled)"

                turn_log.add("promote", player_id, "promote_success",
                            f"{character.name}: promoted from {old_title} to {new_title}",
                            character_id=char_id)

