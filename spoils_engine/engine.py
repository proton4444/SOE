"""
Turn processing engine for Spoils of Empire.

Processes orders in deterministic phases and updates game state.
All randomness is controlled by a seeded RNG for reproducibility.
"""

import math
import random
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import heapq

from spoils_engine.models import (
    GameState, Character, UnitStack, Ship, SummonedCreature, EliteUnit,
    UnitType, ShipType, RoadQuality, CreatureType, LocationPosition, ItemType,
    PopulationBand,
    available_gold, debit_gold, credit_gold,
)
from spoils_engine.orders import (
    Order, MoveOrder, SailOrder, RecruitOrder, BuyShipOrder, AttackOrder, TeleportOrder, FlyOrder, HealOrder,
    SecureOrder, FortifyOrder, UnfortifyOrder, AllyOrder, EnemyOrder, NeutralOrder, AssignOrder, NameOrder,
    PromoteOrder, TaxOrder, CaptureOrder, FreeOrder, StudyOrder, TeachOrder, SummonOrder, CollectOrder,
    BuildOrder, MineOrder, PrayOrder, BlessOrder, CurseOrder, ResurrectOrder, TradeOrder,
    ScryOrder, KillOrder, EnslaveOrder, InterrogateOrder, NoncomOrder, LurkOrder,
    ProbeOrder, SearchOrder, ScanOrder,
    ConjureOrder, ChargeOrder, AbsorbOrder,
    MessageOrder, PostOrder, ReportOrder, AddressOrder, PasswordOrder,
    GetOrder, TransferOrder, UnloadOrder, PayOrder, BorrowOrder, RepayOrder,
    JoinOrder, SupportOrder, actor_field, actor_id_of,
    WorkOrder, TrainOrder, UnnameOrder, CreateOrder, InvestOrder,
    PassageOrder, PreachOrder, OfferOrder, IfOrder,
)
from spoils_engine import config, fog, groups, items, order_queue
from spoils_engine.combat import CombatResolver, calculate_faction_power, apply_casualties
from spoils_engine.parser import get_player_leader, resolve_character


# ============================================================================
# TURN LOG (for reporting)
# ============================================================================

@dataclass
class TurnEvent:
    """A single event that occurred during turn processing."""
    phase: str
    player_id: str
    event_type: str
    description: str
    location_city_id: str = ""
    character_id: str = ""
    success: bool = True


@dataclass
class TurnLog:
    """Log of all events during a turn."""
    events: List[TurnEvent] = field(default_factory=list)

    def add(self, phase: str, player_id: str, event_type: str, description: str,
            location: str = "", character_id: str = "", success: bool = True):
        """Add an event to the log."""
        self.events.append(TurnEvent(
            phase=phase,
            player_id=player_id,
            event_type=event_type,
            description=description,
            location_city_id=location,
            character_id=character_id,
            success=success
        ))

    def get_player_events(self, player_id: str) -> List[TurnEvent]:
        """Get all events for a specific player."""
        return [e for e in self.events if e.player_id == player_id]


# ============================================================================
# SHARED HELPERS
# ============================================================================

def allocate_id(registry: Dict[str, object], prefix: str) -> str:
    """
    Allocate an entity id that is not already used in `registry`.

    Sizing an id off len(registry) alone collides once anything has been
    removed -- e.g. a stack wiped out in combat frees its number and the next
    allocation silently overwrites a live entity.
    """
    n = len(registry) + 1
    while f"{prefix}_{n}" in registry:
        n += 1
    return f"{prefix}_{n}"


def actor_can_act(order: Order, player_id: str, game_state: GameState,
                  actor_attr: str = "actor_id",
                  offered_ids: set = None) -> bool:
    """
    Check the preconditions every acting character must satisfy.

    The actor must exist, belong to the issuing player, be alive, and not be
    held prisoner. Appends a warning to the order and returns False on failure.

    `offered_ids` lists characters named in the same submission's OFFER
    orders: they are exempt from the ownership check (see validate_orders).
    """
    actor_id = getattr(order, actor_attr, "")
    if not actor_id:
        order.warnings.append("No actor specified")
        return False

    actor = game_state.characters.get(actor_id)
    if not actor:
        order.warnings.append(f"Character {actor_id} not found")
        return False

    if actor.faction_id != player_id and actor_id not in (offered_ids or set()):
        order.warnings.append("Character does not belong to you")
        return False

    if actor.is_dead:
        order.warnings.append(f"{actor.name} is dead and cannot act")
        return False

    if actor.is_prisoner:
        order.warnings.append(f"{actor.name} is a prisoner and cannot act")
        return False

    return True


# ============================================================================
# PATHFINDING
# ============================================================================

def _dijkstra(start_city_id: str, end_city_id: str, game_state: GameState,
              sea_only: bool) -> Tuple[List[str], float]:
    """
    Shortest path between two cities over the road graph.

    Args:
        sea_only: If True, traverse only sea lanes; if False, traverse only
            land roads. The two networks are disjoint -- land movement may not
            cross a sea lane and a ship may not sail up a road.

    Returns:
        Tuple of (path_as_city_ids, total_cost)
    """
    if start_city_id == end_city_id:
        return ([start_city_id], 0.0)

    distances = {start_city_id: 0.0}
    previous = {}
    pq = [(0.0, start_city_id)]
    visited = set()

    while pq:
        current_dist, current_id = heapq.heappop(pq)

        if current_id in visited:
            continue
        visited.add(current_id)

        if current_id == end_city_id:
            # Reconstruct path
            path = []
            node = end_city_id
            while node in previous:
                path.append(node)
                node = previous[node]
            path.append(start_city_id)
            path.reverse()
            return (path, current_dist)

        for neighbor_city, road in game_state.world_map.neighbors(current_id):
            is_sea_lane = road.quality == RoadQuality.SEA
            if is_sea_lane != sea_only:
                continue

            if neighbor_city.id in visited:
                continue

            cost = config.get_movement_cost(road.quality)
            new_dist = current_dist + cost

            if neighbor_city.id not in distances or new_dist < distances[neighbor_city.id]:
                distances[neighbor_city.id] = new_dist
                previous[neighbor_city.id] = current_id
                heapq.heappush(pq, (new_dist, neighbor_city.id))

    # No path found
    return ([], float('inf'))


def find_shortest_path(start_city_id: str, end_city_id: str, game_state: GameState) -> Tuple[List[str], float]:
    """Find the shortest overland route between two cities."""
    return _dijkstra(start_city_id, end_city_id, game_state, sea_only=False)


def find_sea_route(start_city_id: str, end_city_id: str, game_state: GameState) -> Tuple[List[str], float]:
    """Find the shortest route between two cities using only sea lanes."""
    return _dijkstra(start_city_id, end_city_id, game_state, sea_only=True)


# ============================================================================
# PHASE 1: VALIDATION
# ============================================================================

def validate_orders(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """
    Validate all orders and mark invalid ones with warnings.

    Every order carrying an actor goes through `actor_can_act`, so ownership,
    death and imprisonment are enforced uniformly rather than per order type.
    Order-specific preconditions (destinations, ports, skills) are checked on
    top of that.

    This runs on the orders the queue released for *this* turn, not on the raw
    submission, so an order that waited three turns is judged against the world
    it actually executes in.
    """
    # Characters named in this turn's OFFER orders may not belong to the
    # player yet: the rules let you order them on the assumption the offer is
    # accepted. Validation lets those orders through; process_offer fails them
    # if the character actually refuses.
    offered_ids = {
        o.target_id for orders in orders_by_player.values() for o in orders
        if isinstance(o, OfferOrder)
    }

    for player_id, orders in orders_by_player.items():
        for order in orders:
            # An IF statement tests a condition about (possibly) another
            # player's character; the condition evaluation owns that check.
            if isinstance(order, IfOrder):
                continue
            # Universal actor preconditions. A few order types name their
            # actor with a role-specific field instead of `actor_id`.
            actor_attr = actor_field(order)
            if hasattr(order, actor_attr):
                if not actor_can_act(order, player_id, game_state, actor_attr,
                                     offered_ids):
                    continue

            actor = game_state.characters.get(getattr(order, actor_attr, ""))

            # Order-specific preconditions
            if isinstance(order, (MoveOrder, SailOrder)):
                if not game_state.world_map.cities.get(order.destination_city_id):
                    order.warnings.append("Destination city not found")
                elif isinstance(order, SailOrder):
                    destination = game_state.world_map.cities[order.destination_city_id]
                    if not destination.is_port:
                        order.warnings.append(f"{destination.name} is not a port")

            elif isinstance(order, AttackOrder):
                faction = game_state.factions.get(player_id)
                target = game_state.factions.get(order.target_faction_id)
                if faction and target and target.id in faction.allies:
                    order.warnings.append(
                        f"{target.name} is your ally - declare them an enemy first"
                    )

            elif isinstance(order, RecruitOrder):
                if not game_state.world_map.cities.get(order.city_id):
                    order.warnings.append("City not found")

                try:
                    UnitType(order.unit_type)
                except ValueError:
                    order.warnings.append(f"Invalid unit type '{order.unit_type}'")

            elif isinstance(order, BuyShipOrder):
                city = game_state.world_map.cities.get(order.city_id)
                if not city:
                    order.warnings.append("City not found")
                elif not city.is_port:
                    order.warnings.append(f"City {city.name} is not a port")

                try:
                    ShipType(order.ship_type)
                except ValueError:
                    order.warnings.append(f"Invalid ship type '{order.ship_type}'")

            elif isinstance(order, (TeleportOrder, FlyOrder, SummonOrder, ScryOrder)):
                if actor and actor.magic_skill <= 0:
                    order.warnings.append("Character has no magic skill")

            elif isinstance(order, (PrayOrder, BlessOrder, CurseOrder, ResurrectOrder)):
                if actor and actor.religion_skill <= 0:
                    order.warnings.append("Character has no religion skill")

            elif isinstance(order, AssignOrder):
                recipient = game_state.characters.get(order.recipient_id)
                if not recipient:
                    order.warnings.append("Recipient not found")
                elif recipient.is_dead:
                    order.warnings.append(f"{recipient.name} is dead")

            elif isinstance(order, TradeOrder):
                if order.amount <= 0:
                    order.warnings.append("Trade amount must be positive")
                if order.action not in ("buy", "sell"):
                    order.warnings.append(f"Unknown trade action '{order.action}'")


# ============================================================================
# PHASE 2: MOVEMENT
# ============================================================================

def process_group_leadership(orders_by_player: Dict[str, List[Order]],
                             game_state: GameState, turn_log: TurnLog):
    """
    Give a character their independence the moment they are given an order.

    rules.md: "Whenever you use the HAVE command, the character named in the
    command will automatically become a group leader if he was not already one.
    From that point on, he will remain independent unless given specific orders
    to join another group."

    This runs before the phases that act on those orders, so a character who is
    told to go somewhere leaves with their own group rather than dragging their
    former leader's people along.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if order.warnings or not order.explicit_actor:
                continue

            actor = game_state.characters.get(actor_id_of(order))
            if not actor or actor.faction_id != player_id:
                continue

            former_leader_id = actor.group_leader_id
            if not groups.detach(actor):
                continue

            former = game_state.characters.get(former_leader_id)
            turn_log.add("groups", player_id, "became_leader",
                         f"{actor.name} left {former.name}'s group and now leads their own"
                         if former else f"{actor.name} now leads their own group",
                         character_id=actor.id)


def process_join(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                 turn_log: TurnLog):
    """Process JOIN -- the ASSIGN operation, given to the one being assigned."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, JoinOrder) or order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            target = game_state.characters.get(order.target_id)

            if not actor:
                continue
            if not target or target.faction_id != player_id:
                turn_log.add("groups", player_id, "join_failed",
                             f"{actor.name}: cannot join {order.target_name or 'them'}",
                             character_id=actor.id, success=False)
                continue

            refusal = groups.attach(actor, target, game_state)
            if refusal:
                turn_log.add("groups", player_id, "join_failed",
                             f"{actor.name} could not join {target.name}: {refusal}",
                             character_id=actor.id, success=False)
                continue

            following = len(groups.group_members(actor.id, game_state))
            brought = f" bringing {following} other(s)" if following else ""
            turn_log.add("groups", player_id, "join",
                         f"{actor.name} joined {target.name}'s group{brought}",
                         character_id=actor.id)


def process_support(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                    turn_log: TurnLog):
    """
    Process SUPPORT -- agree to fight alongside someone when they attack.

    The supporter keeps their own group, so combat leadership does not carry
    across; see `combat.calculate_faction_power`. With no duration the
    agreement stands until a HALT or STOP clears the character's queue.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, SupportOrder) or order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue

            target_id = order.target_ids[0] if order.target_ids else ""
            target = game_state.characters.get(target_id)
            if not target:
                turn_log.add("groups", player_id, "support_failed",
                             f"{actor.name}: nobody by that name to support",
                             character_id=actor.id, success=False)
                continue

            actor.supporting_id = target.id
            if order.duration_days > 0:
                actor.support_until_turn = (
                    game_state.turn_number
                    + order_queue.turns_for_days(order.duration_days)
                )
                window = f" for {order.duration_days} day(s)"
            else:
                actor.support_until_turn = -1  # until halted
                window = " until halted"

            turn_log.add("groups", player_id, "support",
                         f"{actor.name} will fight alongside {target.name}{window}",
                         character_id=actor.id)


def expire_support(game_state: GameState, turn_log: TurnLog):
    """Drop support agreements whose time is up."""
    for char in game_state.characters.values():
        if not char.supporting_id or char.support_until_turn < 0:
            continue
        if game_state.turn_number >= char.support_until_turn:
            target = game_state.characters.get(char.supporting_id)
            char.supporting_id = ""
            char.support_until_turn = -1
            turn_log.add("groups", char.faction_id, "support_ended",
                         f"{char.name} is no longer supporting "
                         f"{target.name if target else 'anyone'}",
                         character_id=char.id)


def process_movement(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                     turn_log: TurnLog, rng: random.Random):
    """Process all movement orders."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, MoveOrder):
                continue

            if order.warnings:
                continue  # Skip invalid orders

            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue

            # Find path
            path, cost = find_shortest_path(actor.location_city_id, order.destination_city_id, game_state)

            if not path or cost == float('inf'):
                order.warnings.append("No path found to destination")
                turn_log.add("movement", player_id, "move_failed",
                            f"{actor.name} could not find path to destination",
                            character_id=actor.id, success=False)
                continue

            # Check movement points
            if cost > actor.movement_points:
                order.warnings.append(f"Insufficient movement points (need {cost}, have {actor.movement_points})")
                turn_log.add("movement", player_id, "move_failed",
                            f"{actor.name} lacks movement points (need {cost:.1f}, have {actor.movement_points})",
                            character_id=actor.id, success=False)
                continue

            # Move character, and whoever is travelling with them. rules.md:
            # a group goes where its leader goes. Position (inside/outside/near)
            # is shared by the travelling party.
            start_city = game_state.world_map.cities[actor.location_city_id]
            end_city = game_state.world_map.cities[order.destination_city_id]
            try:
                arrive_pos = LocationPosition(order.destination_position or "inside")
            except ValueError:
                arrive_pos = LocationPosition.INSIDE
            travelled = groups.move_group(
                actor, order.destination_city_id, game_state, position=arrive_pos
            )
            actor.location_city_id = order.destination_city_id
            actor.location_position = arrive_pos
            # Round up: truncating made every sub-1.0 hop (excellent roads cost
            # 0.5) free, so a character could cross the map without ever
            # spending a movement point.
            actor.movement_points -= max(1, math.ceil(cost))
            for member in travelled:
                member.movement_points -= max(1, math.ceil(cost))

            escort = groups.describe_escort(travelled, actor, game_state)
            pos_note = "" if arrive_pos == LocationPosition.INSIDE else f" ({arrive_pos.value})"
            turn_log.add("movement", player_id, "move",
                        f"{actor.name} moved from {start_city.name} to {end_city.name}"
                        f"{pos_note}{escort} (cost: {cost:.1f})",
                        location=end_city.id, character_id=actor.id)


def process_sail(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                 turn_log: TurnLog, rng: random.Random):
    """Process all sailing orders."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, SailOrder):
                continue

            if order.warnings:
                continue  # Skip invalid orders

            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue

            # Find a ship at the actor's location
            ship = None
            if order.ship_id:
                ship = game_state.ships.get(order.ship_id)
                if not ship or ship.faction_id != player_id:
                    turn_log.add("sail", player_id, "sail_failed",
                                f"{actor.name}: specified ship not found or not owned",
                                character_id=actor.id, success=False)
                    continue
                if ship.location_city_id != actor.location_city_id:
                    turn_log.add("sail", player_id, "sail_failed",
                                f"{actor.name}: ship not at current location",
                                character_id=actor.id, success=False)
                    continue
            else:
                # Auto-select first available ship at location
                for s in game_state.ships.values():
                    if s.faction_id == player_id and s.location_city_id == actor.location_city_id:
                        ship = s
                        break

            if not ship:
                turn_log.add("sail", player_id, "sail_failed",
                            f"{actor.name}: no ship available at current location",
                            character_id=actor.id, success=False)
                continue

            # Find sea route
            path, cost = find_sea_route(actor.location_city_id, order.destination_city_id, game_state)

            if not path or cost == float('inf'):
                turn_log.add("sail", player_id, "sail_failed",
                            f"{actor.name}: no sea route found to destination",
                            character_id=actor.id, success=False)
                continue

            # Count sailors and rowers at this location
            sailors_count = 0
            total_crew = 0  # Everyone except captain can row
            for stack in game_state.unit_stacks.values():
                if stack.faction_id == player_id and stack.location_city_id == actor.location_city_id:
                    if stack.unit_type == UnitType.SAILOR:
                        sailors_count += stack.count
                    total_crew += stack.count

            # Check crew requirements
            MIN_SAILORS = 10
            OPTIMAL_ROWERS = 40

            if sailors_count < MIN_SAILORS:
                turn_log.add("sail", player_id, "sail_failed",
                            f"{actor.name}: insufficient sailors (need {MIN_SAILORS}, have {sailors_count})",
                            character_id=actor.id, success=False)
                continue

            # Calculate sailing efficiency based on crew
            available_rowers = total_crew - MIN_SAILORS  # Subtract required sailors
            rowing_efficiency = min(1.0, available_rowers / OPTIMAL_ROWERS) if OPTIMAL_ROWERS > 0 else 0.5

            # Simplified: Sailing always succeeds if we have minimum crew and sea route exists
            # In full implementation, would factor in captain's sailing skill and trip duration

            # Move the ship and captain
            start_city = game_state.world_map.cities[actor.location_city_id]
            end_city = game_state.world_map.cities[order.destination_city_id]

            ship.location_city_id = order.destination_city_id
            actor.location_city_id = order.destination_city_id

            # Load units onto the ship, up to its capacity. Previously every
            # stack in the port sailed along regardless of capacity, so a
            # single galley could ferry an unlimited army.
            berths = ship.capacity
            embarked = 0
            for stack in sorted(game_state.unit_stacks.values(), key=lambda s: s.id):
                if stack.faction_id != player_id or stack.location_city_id != start_city.id:
                    continue
                if berths <= 0:
                    break

                if stack.count <= berths:
                    stack.location_city_id = order.destination_city_id
                    berths -= stack.count
                    embarked += stack.count
                else:
                    # Split the stack: only `berths` units fit aboard
                    boarding = berths
                    stack.count -= boarding
                    new_stack_id = allocate_id(game_state.unit_stacks, "stack")
                    game_state.unit_stacks[new_stack_id] = UnitStack(
                        id=new_stack_id,
                        faction_id=stack.faction_id,
                        location_city_id=order.destination_city_id,
                        unit_type=stack.unit_type,
                        count=boarding,
                    )
                    berths = 0
                    embarked += boarding

            efficiency_note = f" (rowing efficiency: {rowing_efficiency * 100:.0f}%)" if rowing_efficiency < 1.0 else ""
            efficiency_note += f" carrying {embarked} units" if embarked else ""
            turn_log.add("sail", player_id, "sail",
                        f"{actor.name} sailed from {start_city.name} to {end_city.name}{efficiency_note}",
                        location=end_city.id, character_id=actor.id)


# ============================================================================
# PHASE 3: RECRUIT & BUY
# ============================================================================

def process_recruit_and_buy(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                            turn_log: TurnLog, rng: random.Random):
    """Process recruitment and ship purchase orders."""
    # Track recruitment per city to enforce caps
    recruit_counts = defaultdict(lambda: defaultdict(int))

    for player_id, orders in orders_by_player.items():
        faction = game_state.factions.get(player_id)
        if not faction:
            continue

        for order in orders:
            # Handle RecruitOrder
            if isinstance(order, RecruitOrder):
                if order.warnings:
                    continue

                actor = game_state.characters.get(order.actor_id)
                city = game_state.world_map.cities.get(order.city_id)
                if not actor or not city:
                    continue

                # Check recruit cap
                cap = config.get_recruit_cap_for_city(city.population_band)
                already_recruited = recruit_counts[order.city_id][order.unit_type]

                if already_recruited + order.count > cap:
                    available = cap - already_recruited
                    order.count = max(0, available)
                    if order.count == 0:
                        order.warnings.append(f"Recruitment cap reached in {city.name}")
                        turn_log.add("recruit", player_id, "recruit_failed",
                                    f"Recruitment cap reached in {city.name}",
                                    location=city.id, character_id=actor.id, success=False)
                        continue

                # Check cost (spent from the actor's purse / legacy treasury)
                unit_type_enum = UnitType(order.unit_type)
                cost = config.get_recruit_cost(unit_type_enum) * order.count

                if not debit_gold(actor, faction, cost):
                    have = available_gold(actor, faction)
                    order.warnings.append(f"Insufficient gold (need {cost}, have {have})")
                    turn_log.add("recruit", player_id, "recruit_failed",
                                f"Insufficient gold to recruit {order.count} {order.unit_type}",
                                location=city.id, character_id=actor.id, success=False)
                    continue

                # Create unit stack. Recruits belong to whoever raised them, so
                # they march with that character rather than being left behind.
                stack_id = allocate_id(game_state.unit_stacks, f"stack_{player_id}")
                new_stack = UnitStack(
                    id=stack_id,
                    faction_id=player_id,
                    location_city_id=order.city_id,
                    unit_type=unit_type_enum,
                    count=order.count,
                    owner_character_id=actor.id,
                )
                game_state.unit_stacks[stack_id] = new_stack

                # Update recruit count
                recruit_counts[order.city_id][order.unit_type] += order.count

                turn_log.add("recruit", player_id, "recruit",
                            f"{actor.name} recruited {order.count} {order.unit_type} in {city.name} for {cost}g",
                            location=city.id, character_id=actor.id)

            # Handle BuyShipOrder
            elif isinstance(order, BuyShipOrder):
                if order.warnings:
                    continue

                actor = game_state.characters.get(order.actor_id)
                city = game_state.world_map.cities.get(order.city_id)
                if not actor or not city:
                    continue

                # Check cost
                ship_type_enum = ShipType(order.ship_type)
                cost = config.get_ship_cost(ship_type_enum) * order.count

                if not debit_gold(actor, faction, cost):
                    have = available_gold(actor, faction)
                    order.warnings.append(f"Insufficient gold (need {cost}, have {have})")
                    turn_log.add("buy_ship", player_id, "buy_failed",
                                f"Insufficient gold to buy {order.count} {order.ship_type}",
                                location=city.id, character_id=actor.id, success=False)
                    continue

                # Create ships
                for i in range(order.count):
                    ship_id = allocate_id(game_state.ships, f"ship_{player_id}")
                    new_ship = Ship(
                        id=ship_id,
                        faction_id=player_id,
                        location_city_id=order.city_id,
                        ship_type=ship_type_enum
                    )
                    game_state.ships[ship_id] = new_ship

                turn_log.add("buy_ship", player_id, "buy_ship",
                            f"{actor.name} bought {order.count} {order.ship_type} in {city.name} for {cost}g",
                            location=city.id, character_id=actor.id)


# ============================================================================
# PHASE 4: MAGIC
# ============================================================================

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

                # Calculate power cost (simplified: distance not calculated, use fixed cost)
                # In full version, would calculate actual distance
                power_cost = 5  # Simplified

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

                # Simplified: Fixed cost for flight (ignores encumbrance for alpha)
                power_cost = 10  # Simplified fixed cost

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


# ============================================================================
# PHASE 5: COMBAT
# ============================================================================

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

    rules.md: a supporter joins "as if they had given the same ATTACK/CAPTURE
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
                   turn_log: TurnLog, rng: random.Random):
    """Process combat orders using CombatResolver."""
    # Group attacks by location
    attacks_by_location = defaultdict(list)

    for player_id, orders in orders_by_player.items():
        for order in orders:
            if isinstance(order, AttackOrder) and not order.warnings:
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

            # Calculate powers. The defender's allies present at the location
            # stand with them, so their strength counts and they share the
            # losses.
            # Supporters fight as if they had attacked at the same moment, and
            # cannot also be counted among the defender's allies.
            supporters = supporting_side(attacker, city_id, game_state)
            side = [fid for fid in
                    defending_side(defender_faction_id, attacker_player_id, city_id, game_state)
                    if fid not in supporters]
            attack_side = [attacker_player_id] + supporters
            attacker_power = sum(
                calculate_faction_power(fid, city_id, game_state) for fid in attack_side
            )
            defender_power = sum(
                calculate_faction_power(fid, city_id, game_state) for fid in side
            )

            # Validate engagement
            if defender_power == 0:
                turn_log.add("combat", attacker_player_id, "attack_failed",
                            f"{attacker.name} found no defenders in {city.name}",
                            location=city_id, character_id=attacker.id, success=False)
                continue

            if not resolver.should_attack(attacker_power, defender_power):
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
                attacker_player_id, city_id, result.attacker_casualties, game_state, rng
            )
            for supporter_id in supporters:
                supporter_losses = apply_casualties(
                    supporter_id, city_id, result.attacker_casualties, game_state, rng
                )
                turn_log.add("combat", supporter_id, "supported",
                            f"Your forces fought alongside {attacker.name} in {city.name} "
                            f"(lost {supporter_losses['units']} units)",
                            location=city_id)
            defender_losses = {
                fid: apply_casualties(fid, city_id, result.defender_casualties, game_state, rng)
                for fid in side
            }

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


# ============================================================================
# PHASE 6: INCOME & UPKEEP
# ============================================================================

def process_work(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """
    Process WORK orders: the actor and their group labour for common wages.

    The daily rate comes from the location's population band (rules.md: work
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

            # rules.md: high-level characters sell their own skills -- but
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
    at least 10. rules.md sizes the work by skill -- a level-50 trainer
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

    Per rules.md the character must be part of a group and have nothing of
    their own; the resulting worker goes to the group leader. The lead
    character cannot be unnamed (that would quit the game; rules.md treats it
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


def process_invest(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """
    Process INVEST orders: put gold into a town's growth pool.

    The investor need not be present; the weekly check in
    process_invest_weekly converts the pool into population. Uninhabited
    locations (ruins) cannot be invested in.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, InvestOrder):
                continue
            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue
            city = game_state.world_map.cities.get(order.city_id)
            if not city:
                continue
            if city.is_ruin:
                turn_log.add("invest", player_id, "invest_failed",
                            f"{actor.name}: cannot invest in uninhabited "
                            f"{city.name}",
                            location=city.id, character_id=actor.id, success=False)
                continue

            faction = game_state.factions.get(player_id)
            if order.amount < 0:
                if order.amount < -1:
                    amount = available_gold(actor, faction) * (-order.amount / 100.0)
                else:
                    amount = available_gold(actor, faction)
            else:
                amount = order.amount

            if not debit_gold(actor, faction, amount):
                turn_log.add("invest", player_id, "invest_failed",
                            f"{actor.name}: insufficient gold to invest "
                            f"{amount:g}g",
                            location=city.id, character_id=actor.id, success=False)
                continue

            pool = game_state.invest_pools.get(city.id, 0.0)
            game_state.invest_pools[city.id] = round(pool + amount, 1)
            turn_log.add("invest", player_id, "invest",
                        f"{actor.name} invested {amount:g}g in {city.name} "
                        f"(pool {game_state.invest_pools[city.id]:g}g)",
                        location=city.id, character_id=actor.id)


def process_preach(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog, rng):
    """
    Process PREACH orders: collect tithes and donations.

    Donations scale with religion skill and location population. The preacher
    may also attract followers -- mostly unskilled workers, occasionally a
    soldier, per rules.md.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, PreachOrder):
                continue
            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue
            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            daily = config.PREACH_DONATION_DAILY_PER_BAND.get(city.population_band, 0.0)
            donations = int(actor.religion_skill / 100.0 * daily * order.duration_days
                            * (0.5 + rng.random()))
            if donations > 0:
                credit_gold(actor, donations)
            followers = 0
            follower_roll = rng.random()
            if follower_roll < (actor.religion_skill / 100.0) * config.PREACH_FOLLOWER_CHANCE:
                followers = rng.randint(1, 3)

            details = []
            if donations:
                details.append(f"collected {donations}g in donations")
            else:
                details.append("collected nothing")
            if followers:
                _add_group_units(actor, game_state, UnitType.WORKER, followers)
                details.append(f"{followers} follower(s) joined")

            turn_log.add("preach", player_id, "preach",
                        f"{actor.name} preached {order.duration_days} days in "
                        f"{city.name} and {'; '.join(details)}",
                        location=city.id, character_id=actor.id)


def _offer_acceptance_threshold(target: Character, game_state: GameState) -> float:
    """The gold an offer to `target` must reach: half the square of the
    highest skill plus the value of items in their possession (rules.md)."""
    highest = max(target.combat_skill, target.magic_skill, target.religion_skill,
                  target.trading_skill, target.sailing_skill)
    threshold = config.OFFER_ACCEPT_FRACTION_OF_LEVEL_SQUARE * (highest ** 2)
    for item in game_state.magical_items.values():
        if item.holder_character_id != target.id:
            continue
        value = (item.power_current * config.OFFER_ITEM_VALUE_POWER_PER_POINT
                 + item.skill_level * config.OFFER_ITEM_VALUE_SKILL_PER_POINT
                 + item.protection * config.OFFER_ITEM_VALUE_PROTECTION_PER_POINT)
        threshold += value
    return threshold


def _transfer_ownership(target: Character, new_faction_id: str, game_state: GameState) -> None:
    """The offeree, their group, their units, ships and elite units all move
    to the new faction (rules.md: "he and everyone and everything currently
    assigned to him will become yours to control")."""
    member_ids = {m.id for m in [target] + groups.group_members(target.id, game_state)}
    for member in game_state.characters.values():
        if member.id in member_ids:
            member.faction_id = new_faction_id
    for stack in game_state.unit_stacks.values():
        if stack.owner_character_id in member_ids:
            stack.faction_id = new_faction_id
    for ship in game_state.ships.values():
        if ship.owner_character_id in member_ids:
            ship.faction_id = new_faction_id
    for unit in game_state.elite_units.values():
        if unit.leader_character_id in member_ids:
            unit.faction_id = new_faction_id


def process_offer(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                  turn_log: TurnLog) -> set[tuple[str, str]]:
    """
    Process OFFER orders: recruit an independent character (or free one of
    your prisoners) with gold.

    Acceptance is deterministic: the offer must reach half the square of the
    offeree's highest level plus item value. A character under another
    player's control always declines. Offers to one's own prisoners are
    accepted (the rules' magic ensures sincerity).

    Runs before movement and group leadership so an accepted character joins
    the faction in time for any orders chained after the offer ("Offer ...
    and have her come to Pomye") to work.

    Returns {(player_id, character_id)} of refusals, so run_turn can fail the
    chained orders that assumed acceptance.
    """
    refusals: set[tuple[str, str]] = set()
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, OfferOrder):
                continue
            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            target = game_state.characters.get(order.target_id)
            if not actor or not target:
                continue

            faction = game_state.factions.get(player_id)
            if order.amount < 0:
                amount = available_gold(actor, faction) * (-order.amount / 100.0) if order.amount < -1 else available_gold(actor, faction)
            else:
                amount = order.amount

            target_faction = game_state.factions.get(target.faction_id)

            # One's own prisoner: the magic of the offer guarantees sincerity.
            if target.is_prisoner and target.captor_id and \
                    game_state.characters.get(target.captor_id, None) and \
                    game_state.characters[target.captor_id].faction_id == player_id:
                if not debit_gold(actor, faction, amount):
                    turn_log.add("offer", player_id, "offer_failed",
                                f"{actor.name}: insufficient gold to offer "
                                f"{amount:g}g to {target.name}",
                                character_id=actor.id, success=False)
                    continue
                target.is_prisoner = False
                target.captor_id = ""
                _transfer_ownership(target, player_id, game_state)
                turn_log.add("offer", player_id, "offer",
                            f"{actor.name} offered {amount:g}g and {target.name} "
                            "accepted: they join your faction, released from "
                            "prison",
                            character_id=actor.id)
                continue

            # A character already under a player's control declines politely.
            if target_faction and not target_faction.is_npc:
                turn_log.add("offer", player_id, "offer_rejected",
                            f"{target.name} declined your offer -- they are "
                            "already under another player's command",
                            character_id=actor.id, success=False)
                refusals.add((player_id, target.id))
                continue

            threshold = _offer_acceptance_threshold(target, game_state)
            if amount < threshold:
                turn_log.add("offer", player_id, "offer_rejected",
                            f"{target.name} declined your offer of {amount:g}g "
                            f"-- they hold out for at least {threshold:g}g",
                            character_id=actor.id, success=False)
                refusals.add((player_id, target.id))
                continue

            if not debit_gold(actor, faction, amount):
                turn_log.add("offer", player_id, "offer_failed",
                            f"{actor.name}: insufficient gold to offer "
                            f"{amount:g}g to {target.name}",
                            character_id=actor.id, success=False)
                continue

            _transfer_ownership(target, player_id, game_state)
            turn_log.add("offer", player_id, "offer",
                        f"{actor.name} offered {amount:g}g and {target.name} "
                        "accepted: they and their group join your faction",
                        character_id=actor.id)
    return refusals


def process_passage(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                    turn_log: TurnLog, rng: random.Random):
    """
    Process BUY PASSAGE orders: travel one direct sealane hop on a merchant
    ship.

    Cost is the group's size in gold (encumbrance is unmodelled). Passage may
    fail -- the bigger the group, the harder to find a berth -- and
    `definitely` improves the odds. On success the whole group travels, like
    any other movement.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, PassageOrder):
                continue
            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue

            start_city = game_state.world_map.cities.get(actor.location_city_id)
            end_city = game_state.world_map.cities.get(order.destination_city_id)
            if not start_city or not end_city:
                continue
            if start_city.id == end_city.id:
                turn_log.add("passage", player_id, "passage_failed",
                            f"{actor.name}: already at {end_city.name}",
                            character_id=actor.id, success=False)
                continue

            # One direct sealane hop only (rules.md).
            path, cost = find_sea_route(actor.location_city_id, order.destination_city_id, game_state)
            if not path or cost == float('inf') or len(path) != 2:
                turn_log.add("passage", player_id, "passage_failed",
                            f"{actor.name}: no direct sealane from "
                            f"{start_city.name} to {end_city.name}",
                            character_id=actor.id, success=False)
                continue

            owners = [actor] + groups.group_members(actor.id, game_state)
            people = len(owners)
            for owner in owners:
                people += sum(stack.count for stack in groups.owned_stacks(owner.id, game_state)
                              if stack.location_city_id == actor.location_city_id)

            fare = people * config.PASSAGE_COST_PER_PERSON
            faction = game_state.factions.get(player_id)
            if not debit_gold(actor, faction, fare):
                turn_log.add("passage", player_id, "passage_failed",
                            f"{actor.name}: cannot afford passage "
                            f"({fare}g for a party of {people})",
                            character_id=actor.id, success=False)
                continue

            chance = config.PASSAGE_BASE_CHANCE - config.PASSAGE_SIZE_PENALTY_PER_100 * (people / 100.0)
            if order.definitely:
                chance += config.PASSAGE_DEFINITELY_BONUS
            chance = max(0.0, min(1.0, chance))

            if rng.random() > chance:
                credit_gold(actor, fare)
                turn_log.add("passage", player_id, "passage_failed",
                            f"{actor.name}: no berth found on the {start_city.name}-"
                            f"{end_city.name} run for a party of {people} "
                            "(refunded the fare)",
                            character_id=actor.id, success=False)
                continue

            travelled = groups.move_group(actor, end_city.id, game_state)
            actor.location_city_id = end_city.id
            escort = groups.describe_escort(travelled, actor, game_state)
            turn_log.add("passage", player_id, "passage",
                        f"{actor.name} bought passage from {start_city.name} to "
                        f"{end_city.name}{escort} (fare {fare}g)",
                        location=end_city.id, character_id=actor.id)


def _count_condition_units(subject: Character, unit: str, game_state: GameState) -> int:
    """Count what an IF condition asks about, per rules.md: recruitable
    ranks, creatures, items and power the character controls."""
    if unit == "gold":
        return int(available_gold(subject, game_state.factions.get(subject.faction_id)))
    if unit == "soldier":
        return groups.group_soldier_count(subject, game_state, UnitType.SOLDIER)
    if unit == "sailor":
        return groups.group_soldier_count(subject, game_state, UnitType.SAILOR)
    if unit == "worker":
        return groups.group_soldier_count(subject, game_state, UnitType.WORKER)
    if unit == "slave":
        return groups.group_soldier_count(subject, game_state, UnitType.SLAVE)
    if unit == "horse":
        return subject.resources.get("horse", 0)
    if unit == "catapult":
        return subject.resources.get("catapult", 0)
    if unit == "weapon":
        return subject.resources.get("weapon", 0)
    if unit == "armor":
        return subject.resources.get("armor", 0)
    if unit == "wood":
        return subject.resources.get("wood", 0)
    if unit == "stone":
        return subject.resources.get("stone", 0)
    if unit == "iron":
        return subject.resources.get("iron", 0)
    if unit == "copper":
        return subject.resources.get("copper", 0)
    if unit == "silver":
        return subject.resources.get("silver", 0)
    if unit == "gems":
        return subject.resources.get("gems", 0)
    if unit == "galley":
        return sum(1 for ship in game_state.ships.values()
                   if ship.faction_id == subject.faction_id
                   and ship.location_city_id == subject.location_city_id)
    if unit in ("skeleton", "zombie", "harpy", "minotaur", "griffin",
                "chimera", "dragon", "demon"):
        return sum(creature.count for creature in game_state.summoned_creatures.values()
                   if creature.summoner_id == subject.id
                   and creature.creature_type.value == unit)
    if unit == "encumbrance":
        # No encumbrance model; the group's size in people stands in for it.
        return 1 + sum(
            stack.count for stack in game_state.unit_stacks.values()
            if stack.faction_id == subject.faction_id
            and stack.location_city_id == subject.location_city_id)
    if unit == "power":
        if subject.magic_skill == 0 and subject.religion_skill == 0:
            return 0
        return subject.magic_power_current + subject.religious_power_current
    return 0


def evaluate_if_condition(condition: dict, game_state: GameState, player_id: str,
                          turn_log: TurnLog, order) -> Optional[bool]:
    """Evaluate one parsed IF condition against the current state."""
    subject = resolve_character(condition["subject_name"], game_state, player_id,
                                enemy_ok=True)
    if not subject.found:
        return None

    subject_char = game_state.characters.get(subject.entity_id)
    if not subject_char or subject_char.is_dead:
        return None

    amount = int(condition.get("amount", 0))
    comparator = condition.get("comparator", "exactly")
    unit = condition.get("unit", "gold")
    modifier = condition.get("power_modifier", "")

    if unit == "power":
        if modifier == "magic" or modifier == "magical":
            value = subject_char.magic_power_current
        elif modifier == "religious" or modifier == "religion":
            value = subject_char.religious_power_current
        else:
            value = max(subject_char.magic_power_current,
                        subject_char.religious_power_current)
    else:
        value = _count_condition_units(subject_char, unit, game_state)

    if comparator in ("less than", "fewer than"):
        return value < amount
    if comparator == "more than":
        return value > amount
    if comparator == "at least":
        return value >= amount
    if comparator == "at most":
        return value <= amount
    return value == amount


def process_if_orders(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                      turn_log: TurnLog):
    """
    Evaluate IF statements and splice the chosen branch's orders into the
    turn.

    Runs right after the queue releases the turn's orders, so a condition
    waited on across turns is judged against the world it lands in -- the
    engine's version of "tested after all preceding orders have executed".
    """
    for player_id, orders in orders_by_player.items():
        spliced: List[Order] = []
        for order in orders:
            if not isinstance(order, IfOrder):
                spliced.append(order)
                continue
            if order.warnings or not order.condition:
                spliced.append(order)
                continue

            result = evaluate_if_condition(order.condition, game_state, player_id,
                                           turn_log, order)
            if result is None:
                turn_log.add("if", player_id, "if_unknown",
                            f"Condition 'if {order.condition.get('subject_name')} "
                            f"has {order.condition.get('comparator')} "
                            f"{order.condition.get('amount')} "
                            f"{order.condition.get('unit')}' could not be "
                            "resolved",
                            success=False)
                continue

            branch = order.then_orders if result else order.else_orders
            turn_log.add("if", player_id, "if_branch",
                        f"IF condition {'held' if result else 'failed'} -- "
                        f"{len(branch)} order(s) {'issued' if result else 'skipped'}",
                        character_id=order.actor_id or "")
            spliced.extend(branch)
        orders_by_player[player_id] = spliced


def sync_elite_locations(game_state: GameState) -> None:
    """Elite units travel with their group leader; keep their stored location
    in step whenever the leader moves."""
    for unit in game_state.elite_units.values():
        leader = game_state.characters.get(unit.leader_character_id)
        if leader and not leader.is_dead:
            unit.location_city_id = leader.location_city_id


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


def process_invest_weekly(game_state: GameState, turn_log: TurnLog,
                          rng: Optional[random.Random] = None):
    """
    The weekly INVEST check (rules.md): for each town with invested gold,
    spend about population/100 gold on infrastructure and raise the population
    by the same amount. Some randomness, capped per week so a huge pool cannot
    explode a town in one turn. A band crossing raises the town's income and
    recruit cap.
    """
    if not game_state.invest_pools:
        return
    rng = rng or random.Random(0)
    for city_id, pool in list(game_state.invest_pools.items()):
        city = game_state.world_map.cities.get(city_id)
        if not city:
            continue
        pool = game_state.invest_pools.get(city_id, 0)
        if pool <= 0:
            continue

        pop = config.city_population(city)
        spend = int(pop / 100 * (1 + (rng.random() - 0.5) * 2 * config.INVEST_SPEND_SCATTER))
        spend = max(0, min(spend, int(pool)))
        if spend <= 0:
            continue

        gain = min(spend, config.INVEST_POPULATION_GAIN_MAX)
        game_state.invest_pools[city_id] = round(pool - spend, 1)
        city.population = pop + gain
        if city.population >= 1_000_000:
            city.population_band = PopulationBand.LARGE
        elif city.population >= 100_000:
            city.population_band = PopulationBand.MEDIUM
        elif city.population >= 10_000:
            city.population_band = PopulationBand.SMALL

        turn_log.add("income", city_id, "invest_growth",
                     f"{gain} gold invested in {city.name} was spent on growth: "
                     f"population rose to {city.population:,}")

        if game_state.invest_pools[city_id] <= 0:
            del game_state.invest_pools[city_id]


def process_income_and_upkeep(game_state: GameState, turn_log: TurnLog,
                              rng: Optional[random.Random] = None):
    """Award income and deduct upkeep."""
    for faction in game_state.factions.values():
        # Calculate income from controlled cities (goes to tax pools until collected)
        income = 0
        for city_id in faction.controlled_city_ids:
            city = game_state.world_map.cities.get(city_id)
            if city:
                base_income = config.get_income_for_city(city.population_band)
                pool_key = city.id
                pool_cap = base_income * 4  # roughly 30 days of income
                new_pool = min(pool_cap, game_state.tax_pools.get(pool_key, 0) + base_income)
                game_state.tax_pools[pool_key] = new_pool
                income += base_income

        # Calculate upkeep costs
        upkeep = 0.0

        # Unit upkeep
        for stack in game_state.unit_stacks.values():
            if stack.faction_id == faction.id:
                unit_upkeep = config.UPKEEP_PER_UNIT.get(stack.unit_type, 0)
                upkeep += unit_upkeep * stack.count

        # Ship upkeep
        for ship in game_state.ships.values():
            if ship.faction_id == faction.id:
                ship_upkeep = config.UPKEEP_PER_SHIP.get(ship.ship_type, 0)
                upkeep += ship_upkeep

        # Named character salaries. The leader draws none. Which character that
        # is comes from the is_leader flag rather than iteration order, so
        # adding or removing characters no longer silently moves the exemption.
        leader = get_player_leader(game_state, faction.id)
        for char in game_state.characters.values():
            if char.faction_id == faction.id and char is not leader:
                upkeep += config.calculate_character_salary(
                    char.combat_skill, char.magic_skill
                )

        # Elite troop salary: soldiers times combat level per month (rules.md),
        # prorated to a weekly turn. The unit trains constantly, so the bill
        # comes due every turn regardless of orders.
        for unit in game_state.elite_units.values():
            if unit.faction_id == faction.id:
                upkeep += (unit.size * unit.combat_level
                           * config.ELITE_SALARY_FRACTION_OF_MONTH)

        # Round upkeep to 1 decimal place
        upkeep = round(upkeep, 1)

        # Income accrues to the per-city tax pools ONLY. It reaches a character
        # purse when collected with TAX. Upkeep is paid from the leader's gold
        # (legacy treasury as fall-back); shortfall becomes wage debt for PAY.
        paid = 0.0
        if upkeep > 0 and leader:
            can_pay = min(upkeep, available_gold(leader, faction))
            if can_pay > 0:
                debit_gold(leader, faction, can_pay)
                paid = can_pay
            shortfall = round(upkeep - paid, 1)
            if shortfall > 0:
                faction.wage_debt = round(faction.wage_debt + shortfall, 1)

        # Bankers guild: interest on outstanding loans each turn
        if faction.loan_balance > 0:
            interest = round(faction.loan_balance * config.BORROW_INTEREST_RATE, 2)
            faction.loan_balance = round(faction.loan_balance + interest, 2)
            if faction.loan_grace_turns > 0:
                faction.loan_grace_turns -= 1

        # Log events
        if income > 0:
            turn_log.add("income", faction.id, "income",
                        f"{income}g accrued in tax pools (use TAX to collect)")

        if upkeep > 0:
            turn_log.add("income", faction.id, "upkeep",
                        f"Paid {paid}g in upkeep (units, ships, salaries)"
                        + (f"; {round(upkeep - paid, 1)}g added to wage debt" if paid < upkeep else ""))

        if faction.wage_debt > 0:
            turn_log.add("income", faction.id, "debt",
                        f"Wage debt: {faction.wage_debt}g (use PAY to settle)",
                        success=False)

        if faction.loan_balance > 0:
            turn_log.add("income", faction.id, "loan",
                        f"Bank loan: {faction.loan_balance}g"
                        + (f" (grace {faction.loan_grace_turns} turns)" if faction.loan_grace_turns else
                           " (minimum repayments due)"))


# ============================================================================
# PHASE 7: LOCATION CONTROL & DIPLOMACY
# ============================================================================

def process_secure(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process SECURE orders for location control."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, SecureOrder):
                continue

            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue

            # Get actor's current location
            city_id = actor.location_city_id
            city = game_state.world_map.cities.get(city_id)
            if not city:
                continue

            faction = game_state.factions.get(player_id)
            if not faction:
                continue

            # Check if location is already secured by someone else
            for other_faction in game_state.factions.values():
                if other_faction.id != player_id and city_id in other_faction.secured_city_ids:
                    turn_log.add("secure", player_id, "secure_failed",
                                f"{actor.name}: {city.name} already secured by {other_faction.name}",
                                location=city_id, character_id=actor.id, success=False)
                    continue

            # Secure the location
            faction.secured_city_ids.add(city_id)
            turn_log.add("secure", player_id, "secure",
                        f"{actor.name} secured {city.name}",
                        location=city_id, character_id=actor.id)


def process_fortifications(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process FORTIFY and UNFORTIFY orders that modify city defenses."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if isinstance(order, (FortifyOrder, UnfortifyOrder)):
                if order.warnings:
                    continue  # Skip invalid orders

                actor = game_state.characters.get(order.actor_id)
                if not actor:
                    continue

                city_id = order.city_id or actor.location_city_id
                city = game_state.world_map.cities.get(city_id)
                if not city:
                    continue

                current = city.fortification_level
                stone_needed = max(1, order.percent)

                if isinstance(order, FortifyOrder):
                    available_stone = actor.resources.get("stone", 0)
                    if available_stone < stone_needed:
                        turn_log.add("fortify", player_id, "fortify_failed",
                                    f"{actor.name}: insufficient stone to fortify {city.name}",
                                    character_id=actor.id, success=False)
                        continue

                    actor.resources["stone"] = available_stone - stone_needed
                    new_level = min(100, current + order.percent)
                    city.fortification_level = new_level
                    turn_log.add("fortify", player_id, "fortify",
                                f"{actor.name}: fortified {city.name} to {new_level}%", character_id=actor.id)

                else:
                    new_level = max(0, current - order.percent)
                    city.fortification_level = new_level
                    turn_log.add("fortify", player_id, "unfortify",
                                f"{actor.name}: reduced fortifications in {city.name} to {new_level}%", character_id=actor.id)


def process_diplomacy(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process ALLY, ENEMY, and NEUTRAL diplomacy orders."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            faction = game_state.factions.get(player_id)
            if not faction:
                continue

            if isinstance(order, AllyOrder):
                if order.warnings or not order.target_faction_id:
                    continue

                # Add to allies, remove from enemies
                faction.allies.add(order.target_faction_id)
                faction.enemies.discard(order.target_faction_id)

                target_faction = game_state.factions.get(order.target_faction_id)
                if target_faction:
                    turn_log.add("diplomacy", player_id, "ally",
                                f"Declared {target_faction.name} as ally")

            elif isinstance(order, EnemyOrder):
                if order.warnings or not order.target_faction_id:
                    continue

                # Add to enemies, remove from allies
                faction.enemies.add(order.target_faction_id)
                faction.allies.discard(order.target_faction_id)

                target_faction = game_state.factions.get(order.target_faction_id)
                if target_faction:
                    turn_log.add("diplomacy", player_id, "enemy",
                                f"Declared {target_faction.name} as enemy")

            elif isinstance(order, NeutralOrder):
                if order.warnings or not order.target_faction_id:
                    continue

                # Remove from both allies and enemies
                faction.allies.discard(order.target_faction_id)
                faction.enemies.discard(order.target_faction_id)

                target_faction = game_state.factions.get(order.target_faction_id)
                if target_faction:
                    turn_log.add("diplomacy", player_id, "neutral",
                                f"Set diplomatic stance to neutral with {target_faction.name}")


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

            # Assign named characters into the recipient's group. rules.md:
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

            # Find a unit stack of the specified type for this faction
            unit_stack = None
            for stack in game_state.unit_stacks.values():
                if (stack.faction_id == player_id and
                    stack.unit_type.name == order.unit_type and
                    stack.count > 0):
                    unit_stack = stack
                    break

            if not unit_stack:
                turn_log.add("name", player_id, "name_failed",
                            f"No {order.unit_type.lower()}s available to name",
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


def process_tax(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process TAX orders to collect taxes from locations."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, TaxOrder):
                continue

            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue

            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            # Check if location is secured by another faction.
            # (The `continue` used here previously only advanced the inner
            # faction loop, so the order went ahead and taxed anyway.)
            blocked_by = next(
                (f for f in game_state.factions.values()
                 if f.id != player_id and actor.location_city_id in f.secured_city_ids),
                None
            )
            if blocked_by:
                turn_log.add("tax", player_id, "tax_failed",
                            f"{actor.name}: {city.name} is secured by {blocked_by.name}",
                            character_id=actor.id, success=False)
                continue

            # Count soldiers at this location for this faction
            soldier_count = 0
            for stack in game_state.unit_stacks.values():
                if (stack.faction_id == player_id and
                    stack.location_city_id == actor.location_city_id and
                    stack.unit_type == UnitType.SOLDIER):
                    soldier_count += stack.count

            if soldier_count == 0:
                turn_log.add("tax", player_id, "tax_failed",
                            f"{actor.name}: no soldiers available to collect taxes",
                            character_id=actor.id, success=False)
                continue

            pool_key = city.id
            available_taxes = game_state.tax_pools.get(pool_key, 0)

            if available_taxes <= 0:
                turn_log.add("tax", player_id, "tax_failed",
                            f"{actor.name}: no taxes accumulated at {city.name}",
                            character_id=actor.id, success=False)
                continue

            collection_rate = soldier_count * order.duration_days // 4
            taxes_collected = min(available_taxes, max(1, collection_rate))
            game_state.tax_pools[pool_key] = max(0, available_taxes - taxes_collected)

            credit_gold(actor, taxes_collected)

            turn_log.add("tax", player_id, "tax_success",
                        f"{actor.name}: collected {taxes_collected}g in taxes from {city.name} "
                        f"({soldier_count} soldiers, {order.duration_days} days, {game_state.tax_pools.get(pool_key, 0)}g remains)",
                        character_id=actor.id)


def process_trade(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process TRADE orders to buy or sell resources with trading skill discounts."""
    for player_id, orders in orders_by_player.items():
        faction = game_state.factions.get(player_id)
        for order in orders:
            if not isinstance(order, TradeOrder):
                continue

            if order.warnings:
                continue  # Skip invalid orders

            actor = game_state.characters.get(order.actor_id)
            if not actor or not faction:
                continue

            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            # Prices come from config, never from the order: a player-supplied
            # price would let a faction name its own sale value and mint gold.
            #
            # The market quotes a buy price above and a sell price below the
            # base value. Trading skill narrows that spread in the trader's
            # favour but never inverts it, so buying and selling in the same
            # city is always a small loss rather than an arbitrage loop.
            base_price = config.get_resource_price(order.resource_type)
            # An amulet of trading lets the wearer "buy and sell items as if he
            # were a trader" at the amulet's level, so it stands in for the
            # character's own skill whenever it is higher.
            trading = items.effective_skill_with_items(actor, "trading", game_state)
            spread = config.RESOURCE_MARKET_SPREAD * (1 - trading / 200)
            if order.action == "buy":
                unit_price = max(1, round(base_price * (1 + spread / 2)))
            else:
                unit_price = max(1, round(base_price * (1 - spread / 2)))

            if order.action == "buy":
                total_cost = unit_price * order.amount
                if not debit_gold(actor, faction, total_cost):
                    turn_log.add("trade", player_id, "trade_failed",
                                f"{actor.name}: insufficient gold to buy {order.amount} {order.resource_type}",
                                character_id=actor.id, success=False)
                    continue

                actor.resources[order.resource_type] = actor.resources.get(order.resource_type, 0) + order.amount
                turn_log.add("trade", player_id, "buy",
                            f"{actor.name} bought {order.amount} {order.resource_type} in {city.name} for {total_cost}g",
                            character_id=actor.id)
            else:
                available = actor.resources.get(order.resource_type, 0)
                if available < order.amount:
                    turn_log.add("trade", player_id, "trade_failed",
                                f"{actor.name}: not enough {order.resource_type} to sell",
                                character_id=actor.id, success=False)
                    continue

                actor.resources[order.resource_type] = available - order.amount
                revenue = unit_price * order.amount
                credit_gold(actor, revenue)
                turn_log.add("trade", player_id, "sell",
                            f"{actor.name} sold {order.amount} {order.resource_type} in {city.name} for {revenue}g",
                            character_id=actor.id)


def report_pending_orders(game_state: GameState, turn_log: TurnLog):
    """Tell each player what is still sitting in their characters' queues."""
    for faction_id in game_state.factions:
        for line in order_queue.pending_summary(game_state, faction_id):
            turn_log.add("queue", faction_id, "pending", line)


def process_collect(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process COLLECT/GATHER orders to gather resources (wood, stone)."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, CollectOrder):
                continue

            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue

            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            # Validate terrain for resource type
            resource_type = order.resource_type.lower()

            if resource_type == "wood":
                # Wood requires forest terrain
                if not ("forest" in city.terrain or "woods" in city.terrain):
                    turn_log.add("collect", player_id, "collect_failed",
                                f"{actor.name}: no forests available at {city.name} for wood gathering",
                                character_id=actor.id, success=False)
                    continue

            elif resource_type == "stone":
                # Stone requires hills or mountains
                if not city.terrain & {"hills", "mountains", "mountain"}:
                    turn_log.add("collect", player_id, "collect_failed",
                                f"{actor.name}: no hills/mountains available at {city.name} for stone gathering",
                                character_id=actor.id, success=False)
                    continue

            # Count workers at this location for this faction
            worker_count = 0
            for stack in game_state.unit_stacks.values():
                if (stack.faction_id == player_id and
                    stack.location_city_id == actor.location_city_id and
                    stack.unit_type == UnitType.WORKER):
                    worker_count += stack.count

            if worker_count == 0:
                turn_log.add("collect", player_id, "collect_failed",
                            f"{actor.name}: no workers available to gather {resource_type}",
                            character_id=actor.id, success=False)
                continue

            # Calculate resource yield
            # Wood: 3 per worker per day
            # Stone: 2 per worker per day (harder work)
            if resource_type == "wood":
                daily_rate = 3
            else:  # stone
                daily_rate = 2

            richness = city.resource_richness.get(resource_type, 1.0)
            resources_gathered = int(worker_count * order.duration_days * daily_rate * richness)

            # Add resources to character's inventory
            if resource_type not in actor.resources:
                actor.resources[resource_type] = 0
            actor.resources[resource_type] += resources_gathered

            turn_log.add("collect", player_id, "collect_success",
                        f"{actor.name}: gathered {resources_gathered} {resource_type} at {city.name} "
                        f"({worker_count} workers, {order.duration_days} days)",
                        character_id=actor.id)


def process_build(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process BUILD/CONSTRUCT/MAKE orders to build items from resources."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, BuildOrder):
                continue

            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue

            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            item_type = order.item_type.lower()

            if item_type == "galley":
                # Galleys require 200 wood each and must be built at a port
                wood_per_galley = 200
                total_wood_needed = wood_per_galley * order.count

                # Check if at a port city
                if not city.is_port:
                    turn_log.add("build", player_id, "build_failed",
                                f"{actor.name}: cannot build galleys at {city.name} (not a port city)",
                                character_id=actor.id, success=False)
                    continue

                # Check if actor has enough wood
                wood_available = actor.resources.get("wood", 0)
                if wood_available < total_wood_needed:
                    turn_log.add("build", player_id, "build_failed",
                                f"{actor.name}: insufficient wood to build {order.count} galley(s) "
                                f"(need {total_wood_needed}, have {wood_available})",
                                character_id=actor.id, success=False)
                    continue

                # Consume wood
                actor.resources["wood"] -= total_wood_needed

                # Create galleys
                for i in range(order.count):
                    ship_id = allocate_id(game_state.ships, "ship")
                    new_ship = Ship(
                        id=ship_id,
                        faction_id=player_id,
                        location_city_id=actor.location_city_id,
                        ship_type=ShipType.GALLEY,
                        capacity=550
                    )
                    game_state.ships[ship_id] = new_ship

                turn_log.add("build", player_id, "build_success",
                            f"{actor.name}: built {order.count} galley(s) at {city.name} "
                            f"(consumed {total_wood_needed} wood)",
                            character_id=actor.id)

            elif item_type == "catapult":
                # Catapults require 4 wood each (basic cost 20, 1/5 = 4)
                wood_per_catapult = 4
                total_wood_needed = wood_per_catapult * order.count

                # Check if actor has enough wood
                wood_available = actor.resources.get("wood", 0)
                if wood_available < total_wood_needed:
                    turn_log.add("build", player_id, "build_failed",
                                f"{actor.name}: insufficient wood to build {order.count} catapult(s) "
                                f"(need {total_wood_needed}, have {wood_available})",
                                character_id=actor.id, success=False)
                    continue

                # Consume wood
                actor.resources["wood"] -= total_wood_needed

                # Add catapults to inventory
                if "catapult" not in actor.resources:
                    actor.resources["catapult"] = 0
                actor.resources["catapult"] += order.count

                turn_log.add("build", player_id, "build_success",
                            f"{actor.name}: built {order.count} catapult(s) at {city.name} "
                            f"(consumed {total_wood_needed} wood)",
                            character_id=actor.id)

            elif item_type == "weapon" or item_type == "weapons":
                # Weapons require 1 iron each (basic cost 5, 1/5 = 1)
                iron_per_weapon = 1
                total_iron_needed = iron_per_weapon * order.count

                # Check if actor has enough iron
                iron_available = actor.resources.get("iron", 0)
                if iron_available < total_iron_needed:
                    turn_log.add("build", player_id, "build_failed",
                                f"{actor.name}: insufficient iron to build {order.count} weapon(s) "
                                f"(need {total_iron_needed}, have {iron_available})",
                                character_id=actor.id, success=False)
                    continue

                # Consume iron
                actor.resources["iron"] -= total_iron_needed

                # Add weapons to inventory
                if "weapon" not in actor.resources:
                    actor.resources["weapon"] = 0
                actor.resources["weapon"] += order.count

                turn_log.add("build", player_id, "build_success",
                            f"{actor.name}: built {order.count} weapon(s) at {city.name} "
                            f"(consumed {total_iron_needed} iron)",
                            character_id=actor.id)

            elif item_type == "armor":
                # Armor requires 1 iron each (basic cost 5, 1/5 = 1)
                iron_per_armor = 1
                total_iron_needed = iron_per_armor * order.count

                # Check if actor has enough iron
                iron_available = actor.resources.get("iron", 0)
                if iron_available < total_iron_needed:
                    turn_log.add("build", player_id, "build_failed",
                                f"{actor.name}: insufficient iron to build {order.count} armor "
                                f"(need {total_iron_needed}, have {iron_available})",
                                character_id=actor.id, success=False)
                    continue

                # Consume iron
                actor.resources["iron"] -= total_iron_needed

                # Add armor to inventory
                if "armor" not in actor.resources:
                    actor.resources["armor"] = 0
                actor.resources["armor"] += order.count

                turn_log.add("build", player_id, "build_success",
                            f"{actor.name}: built {order.count} armor at {city.name} "
                            f"(consumed {total_iron_needed} iron)",
                            character_id=actor.id)

            else:
                turn_log.add("build", player_id, "build_failed",
                            f"{actor.name}: unknown item type '{item_type}'",
                            character_id=actor.id, success=False)


def process_mine(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process MINE orders to extract minerals (iron, gold, silver, copper, gems)."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, MineOrder):
                continue

            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue

            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            # Validate terrain - mining requires hills or mountains
            resource_type = order.resource_type.lower()
            if not ("hills" in city.terrain or "mountains" in city.terrain or "mountain" in city.terrain):
                turn_log.add("mine", player_id, "mine_failed",
                            f"{actor.name}: no hills/mountains available at {city.name} for mining",
                            character_id=actor.id, success=False)
                continue

            # Count workers at this location for this faction
            worker_count = 0
            for stack in game_state.unit_stacks.values():
                if (stack.faction_id == player_id and
                    stack.location_city_id == actor.location_city_id and
                    stack.unit_type == UnitType.WORKER):
                    worker_count += stack.count

            if worker_count == 0:
                turn_log.add("mine", player_id, "mine_failed",
                            f"{actor.name}: no workers available to mine {resource_type}",
                            character_id=actor.id, success=False)
                continue

            # Calculate mining yield (alpha: simplified, no richness variation)
            # Iron: 2 per worker per day (heaviest, hardest to extract)
            # Copper: 3 per worker per day
            # Silver: 4 per worker per day
            # Gold: 5 per worker per day (rarest but easier to find when present)
            # Gems: 6 per worker per day (smallest, easiest to gather)
            yield_rates = {
                "iron": 2,
                "copper": 3,
                "silver": 4,
                "gold": 5,
                "gems": 6
            }

            daily_rate = yield_rates.get(resource_type, 2)
            richness = city.resource_richness.get(resource_type, 1.0)
            resources_mined = int(worker_count * order.duration_days * daily_rate * richness)

            # Add resources to character's inventory
            if resource_type not in actor.resources:
                actor.resources[resource_type] = 0
            actor.resources[resource_type] += resources_mined

            turn_log.add("mine", player_id, "mine_success",
                        f"{actor.name}: mined {resources_mined} {resource_type} at {city.name} "
                        f"({worker_count} workers, {order.duration_days} days)",
                        character_id=actor.id)


def process_capture(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog, rng):
    """Process CAPTURE orders to take prisoners."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, CaptureOrder):
                continue

            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue

            # Simplified capture for alpha: if you have more power, you capture
            # In full game: would do combat resolution with capture attempts
            for i, target_id in enumerate(order.target_ids):
                target = game_state.characters.get(target_id)
                if not target or target.is_dead or target.is_prisoner:
                    continue

                # Check same location
                if actor.location_city_id != target.location_city_id:
                    turn_log.add("capture", player_id, "capture_failed",
                                f"{actor.name}: {target.name} is not at this location",
                                character_id=actor.id, success=False)
                    continue

                # Calculate power (simplified - use combat power calculation)
                attacker_power = calculate_faction_power(player_id, actor.location_city_id, game_state)
                defender_power = calculate_faction_power(target.faction_id, target.location_city_id, game_state)

                # Capture check: 50% + power ratio bonus. A magical ring cuts
                # the chance of being captured just as it cuts the chance of
                # being hit, and a blessing on the location adds to it.
                capture_chance = 0.5 + (attacker_power / max(1, defender_power + attacker_power)) * 0.5
                protection = items.ring_protection(
                    target, game_state,
                    blessed=target.location_city_id in game_state.location_blessings)
                capture_chance = items.apply_ring_protection(capture_chance, protection)

                if rng.random() < capture_chance:
                    # Successful capture
                    target.is_prisoner = True
                    target.captor_id = actor.id
                    turn_log.add("capture", player_id, "capture_success",
                                f"{actor.name}: captured {target.name}!",
                                character_id=actor.id)
                else:
                    # Failed capture - minor damage to target
                    damage = rng.randint(5, 15)
                    target.health = max(0, target.health - damage)
                    if target.health <= 0:
                        target.is_dead = True
                        turn_log.add("capture", player_id, "capture_killed",
                                    f"{actor.name}: killed {target.name} during capture attempt",
                                    character_id=actor.id)
                    else:
                        turn_log.add("capture", player_id, "capture_failed",
                                    f"{actor.name}: failed to capture {target.name} (dealt {damage} damage)",
                                    character_id=actor.id, success=False)


def process_free(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process FREE/RELEASE orders to free prisoners."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, FreeOrder):
                continue

            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue

            # Free all specified prisoners
            for i, prisoner_id in enumerate(order.prisoner_ids):
                prisoner = game_state.characters.get(prisoner_id)
                if not prisoner:
                    continue

                # Check if this character is actually a prisoner held by this actor
                if not prisoner.is_prisoner or prisoner.captor_id != actor.id:
                    turn_log.add("free", player_id, "free_failed",
                                f"{actor.name}: {prisoner.name} is not a prisoner held by you",
                                character_id=actor.id, success=False)
                    continue

                # Free the prisoner
                prisoner.is_prisoner = False
                prisoner.captor_id = ""

                turn_log.add("free", player_id, "free_success",
                            f"{actor.name}: freed {prisoner.name}",
                            character_id=actor.id)


def _prisoner_held_by(prisoner: Character, actor: Character) -> bool:
    return bool(prisoner and prisoner.is_prisoner and prisoner.captor_id == actor.id)


def process_kill(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process KILL/EXECUTE orders against held prisoners."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, KillOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue
            for prisoner_id in order.prisoner_ids:
                prisoner = game_state.characters.get(prisoner_id)
                if not prisoner:
                    continue
                if not _prisoner_held_by(prisoner, actor):
                    turn_log.add("kill", player_id, "kill_failed",
                                f"{actor.name}: {prisoner.name} is not your prisoner",
                                character_id=actor.id, success=False)
                    continue
                prisoner.is_dead = True
                prisoner.health = 0
                prisoner.is_prisoner = False
                prisoner.captor_id = ""
                turn_log.add("kill", player_id, "kill_success",
                            f"{actor.name}: executed {prisoner.name}",
                            character_id=actor.id)


def process_enslave(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Convert prisoners into unnamed slave labour units."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, EnslaveOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue
            for prisoner_id in list(order.prisoner_ids):
                prisoner = game_state.characters.get(prisoner_id)
                if not prisoner:
                    continue
                if not _prisoner_held_by(prisoner, actor):
                    turn_log.add("enslave", player_id, "enslave_failed",
                                f"{actor.name}: {prisoner.name} is not your prisoner",
                                character_id=actor.id, success=False)
                    continue

                # Valuables on the prisoner are lost (rules warn to TAKE first)
                lost_gold = prisoner.gold
                prisoner.gold = 0

                # Add one slave unit at the actor's location for the captors
                stack = next(
                    (s for s in game_state.unit_stacks.values()
                     if s.faction_id == player_id
                     and s.location_city_id == actor.location_city_id
                     and s.unit_type == UnitType.SLAVE),
                    None,
                )
                if stack:
                    stack.count += 1
                else:
                    sid = allocate_id(game_state.unit_stacks, "stack")
                    game_state.unit_stacks[sid] = UnitStack(
                        id=sid,
                        faction_id=player_id,
                        location_city_id=actor.location_city_id,
                        unit_type=UnitType.SLAVE,
                        count=1,
                    )

                # Named identity is gone — remove the character
                name = prisoner.name
                del game_state.characters[prisoner_id]
                msg = f"{actor.name}: enslaved {name} (now 1 slave)"
                if lost_gold:
                    msg += f"; {lost_gold}g of their purse was lost"
                turn_log.add("enslave", player_id, "enslave_success", msg,
                            character_id=actor.id)


def process_interrogate(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                        turn_log: TurnLog, rng: random.Random):
    """Extract faction / leader intel from a prisoner."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, InterrogateOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue
            for prisoner_id in order.prisoner_ids:
                prisoner = game_state.characters.get(prisoner_id)
                if not prisoner:
                    continue
                if not _prisoner_held_by(prisoner, actor):
                    turn_log.add("interrogate", player_id, "interrogate_failed",
                                f"{actor.name}: {prisoner.name} is not your prisoner",
                                character_id=actor.id, success=False)
                    continue

                actor_level = actor.combat_skill + actor.magic_skill + actor.religion_skill
                victim_level = prisoner.combat_skill + prisoner.magic_skill + prisoner.religion_skill
                chance = 0.35 + (actor_level - victim_level) / 200
                chance = max(0.1, min(0.9, chance))

                # Higher-level victims more likely to die under torture
                death_chance = 0.05 + victim_level / 400
                if rng.random() < death_chance:
                    prisoner.is_dead = True
                    prisoner.health = 0
                    prisoner.is_prisoner = False
                    prisoner.captor_id = ""
                    turn_log.add("interrogate", player_id, "interrogate_killed",
                                f"{actor.name}: {prisoner.name} died under interrogation",
                                character_id=actor.id, success=False)
                    continue

                if rng.random() < chance:
                    fac = game_state.factions.get(prisoner.faction_id)
                    fac_name = fac.name if fac else prisoner.faction_id
                    leader = get_player_leader(game_state, prisoner.faction_id)
                    leader_name = leader.name if leader else "unknown"
                    turn_log.add("interrogate", player_id, "interrogate_success",
                                f"{actor.name}: {prisoner.name} revealed faction '{fac_name}', "
                                f"leader '{leader_name}'",
                                character_id=actor.id)
                else:
                    damage = rng.randint(5, 20)
                    prisoner.health = max(1, prisoner.health - damage)
                    turn_log.add("interrogate", player_id, "interrogate_failed",
                                f"{actor.name}: {prisoner.name} revealed nothing "
                                f"(took {damage} damage)",
                                character_id=actor.id, success=False)


def process_status_orders(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                          turn_log: TurnLog):
    """Process NONCOM/COMBATANT and LURK/UNLURK status flags."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if isinstance(order, NoncomOrder):
                if order.warnings:
                    continue
                for cid, cname in zip(order.character_ids, order.character_names):
                    char = game_state.characters.get(cid)
                    if not char or char.faction_id != player_id:
                        turn_log.add("status", player_id, "status_failed",
                                    f"Cannot set status for {cname}", success=False)
                        continue
                    char.is_noncom = order.set_noncom
                    label = "non-combatant" if order.set_noncom else "combatant"
                    turn_log.add("status", player_id, "noncom",
                                f"{char.name} is now a {label}",
                                character_id=char.id)

            elif isinstance(order, LurkOrder):
                if order.warnings:
                    continue
                actor = game_state.characters.get(order.actor_id)
                if not actor:
                    continue
                # rules.md: "The LURK command should only be used on the leader
                # of a group. Everyone in the group will automatically be
                # included." A member who later breaks away keeps the flag only
                # if their new leader is given their own LURK order.
                actor.is_lurking = order.set_lurking
                followers = groups.group_members(actor.id, game_state)
                for member in followers:
                    member.is_lurking = order.set_lurking

                verb = "starts lurking" if order.set_lurking else "stops lurking"
                with_group = f" (with {len(followers)} in their group)" if followers else ""
                turn_log.add("status", player_id, "lurk",
                            f"{actor.name} {verb}{with_group}",
                            character_id=actor.id)


def process_probe(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                  turn_log: TurnLog, rng: random.Random):
    """
    Magically report on another player's character.

    rules.md: costs 25 power always; success chance = caster magic skill %;
    target resists with effective skill %; on resist the target is told an
    attempt was made but not by whom.
    """
    PROBE_COST = 25
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, ProbeOrder) or order.warnings:
                continue
            caster = game_state.characters.get(order.actor_id)
            target = game_state.characters.get(order.target_id)
            if not caster or not target:
                turn_log.add("intel", player_id, "probe_failed",
                            "PROBE: caster or target missing", success=False)
                continue
            error = items.pay_for_spell(caster, PROBE_COST, "probe",
                                        order.wand_name, game_state)
            if error:
                turn_log.add("intel", player_id, "probe_failed",
                            f"{caster.name} cannot probe: {error}",
                            character_id=caster.id, success=False)
                continue
            # Base success: magic skill as a percentage. A wand casts at its
            # own skill level, since it supplies the skill as well as the power.
            wand = (items.find_item_by_name(order.wand_name, game_state)
                    if order.wand_name else None)
            cast_skill = wand.skill_level if wand else caster.magic_skill
            success_roll = rng.random() * 100.0
            if success_roll >= cast_skill:
                turn_log.add("intel", player_id, "probe_failed",
                            f"{caster.name} failed to probe {target.name} "
                            f"(magic skill {cast_skill})",
                            character_id=caster.id, success=False)
                continue

            resist = fog.effective_skill_level(target)
            if rng.random() * 100.0 < resist:
                turn_log.add("intel", player_id, "probe_resisted",
                            f"{caster.name}'s probe of {target.name} was resisted",
                            character_id=caster.id, success=False)
                # Target learns only that an attempt was made.
                turn_log.add("intel", target.faction_id, "probe_detected",
                            f"{target.name} felt a magical probe attempt",
                            character_id=target.id, success=True)
                continue

            city = game_state.world_map.cities.get(target.location_city_id)
            city_name = city.name if city else "unknown"
            pos = target.location_position.value
            soldiers = groups.group_soldier_count(target, game_state)
            report = (
                f"{caster.name} probed {target.name}: at {city_name} ({pos}), "
                f"combat {target.combat_skill}, magic {target.magic_skill}, "
                f"religion {target.religion_skill}, trading {target.trading_skill}, "
                f"health {target.health}, gold {target.gold:.0f}, "
                f"~{soldiers} soldiers in their group"
                f"{', lurking' if target.is_lurking else ''}"
            )
            turn_log.add("intel", player_id, "probe", report,
                        location=target.location_city_id, character_id=caster.id)


def process_search(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                   turn_log: TurnLog, rng: random.Random):
    """
    SEARCH/EXPLORE uninhabited ruins at the actor's current location.

    rules.md: must be *inside* a ruin; outside/near and inhabited cities find
    nothing. A successful dig turns up one of the enchantress's magical items,
    which lasts forever, and the chance scales with how long the dig ran.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, SearchOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue
            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            if actor.location_position != LocationPosition.INSIDE:
                turn_log.add("intel", player_id, "search_failed",
                            f"{actor.name} must be inside the ruins to search "
                            f"(currently {actor.location_position.value})",
                            character_id=actor.id, location=city.id, success=False)
                continue
            if not city.is_ruin:
                turn_log.add("intel", player_id, "search_failed",
                            f"{actor.name} found nothing of value at {city.name} "
                            f"(not uninhabited ruins)",
                            character_id=actor.id, location=city.id, success=False)
                continue

            # Longer searches help a little, up to a ceiling: no amount of
            # digging guarantees a ruin still has anything left in it.
            days = max(1, order.duration_days)
            chance = min(config.RUIN_ITEM_MAX_CHANCE,
                        config.RUIN_ITEM_BASE_CHANCE
                        + config.RUIN_ITEM_CHANCE_PER_DAY * min(days, 30))
            if rng.random() < chance:
                kinds = sorted(config.RUIN_ITEM_WEIGHTS)
                kind = rng.choices(
                    kinds, weights=[config.RUIN_ITEM_WEIGHTS[k] for k in kinds]
                )[0]
                # Found items are permanent: expires_turn stays -1.
                found = items.make_item(game_state, rng, ItemType(kind),
                                        holder_id=actor.id)
                turn_log.add("intel", player_id, "search",
                            f"{actor.name} searched the ruins of {city.name} "
                            f"and found {items.describe(found, game_state)}",
                            character_id=actor.id, location=city.id)
            else:
                turn_log.add("intel", player_id, "search",
                            f"{actor.name} searched the ruins of {city.name} "
                            f"and found nothing",
                            character_id=actor.id, location=city.id)


def orb_scan_cost(from_city_id: str, to_city_id: str, game_state: GameState) -> int:
    """
    Power an orb spends to reach a location.

    rules.md prices a scan at one power per ten miles. The engine has no miles,
    so the overland route's movement cost stands in for the distance and
    `ORB_POWER_PER_HOP` converts it. An unreachable location costs nothing to
    scan because the orb never gets there; callers check reachability first.
    """
    if from_city_id == to_city_id:
        return 0
    path, cost = find_shortest_path(from_city_id, to_city_id, game_state)
    if not path:
        return -1
    return max(1, int(round(cost * config.ORB_POWER_PER_HOP)))


def process_scan(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                 turn_log: TurnLog):
    """
    SCAN a distant city with a magical orb.

    rules.md: the orb must be named in the order and held by the actor. It
    spends its own power — never the caster's, never a crystal's — at a rate
    set by the distance. The report is complete, unlike REPORT/QUERY: everyone
    of note is detected whether or not they are lurking. But an orb "will only
    tell you who is inside or outside a town or city. It cannot be used to scan
    people near the town", and it cannot see monsters.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, ScanOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue

            if not order.orb_name:
                turn_log.add("intel", player_id, "scan_failed",
                            f"{actor.name} must name the orb to SCAN with "
                            f"(e.g. 'scan Kitesta using *Anomba*')",
                            character_id=actor.id, success=False)
                continue

            orb = items.find_item_by_name(order.orb_name, game_state)
            if not orb or orb.item_type != ItemType.ORB:
                turn_log.add("intel", player_id, "scan_failed",
                            f"{actor.name} has no magical orb called "
                            f"{order.orb_name}",
                            character_id=actor.id, success=False)
                continue
            if orb.holder_character_id != actor.id:
                turn_log.add("intel", player_id, "scan_failed",
                            f"{actor.name} does not possess {orb.name}",
                            character_id=actor.id, success=False)
                continue

            for city_id, city_name in zip(order.city_ids, order.city_names):
                cost = orb_scan_cost(actor.location_city_id, city_id, game_state)
                if cost < 0:
                    turn_log.add("intel", player_id, "scan_failed",
                                f"{orb.name} cannot reach {city_name}: no route "
                                f"from {actor.name}'s location",
                                character_id=actor.id, success=False)
                    continue
                if orb.power_current < cost:
                    turn_log.add("intel", player_id, "scan_failed",
                                f"{orb.name} has {orb.power_current} power, not "
                                f"the {cost} needed to reach {city_name}",
                                character_id=actor.id, success=False)
                    continue

                orb.power_current -= cost
                seen = [
                    c for c in game_state.characters.values()
                    if c.location_city_id == city_id and not c.is_dead
                    and c.location_position != LocationPosition.NEAR
                ]
                if seen:
                    who = ", ".join(
                        f"{c.name} ({c.location_position.value})"
                        for c in sorted(seen, key=lambda c: c.name)
                    )
                    detail = f"sees {who}"
                else:
                    detail = "sees nobody"
                turn_log.add("intel", player_id, "scan",
                            f"{actor.name} scans {city_name} with {orb.name} "
                            f"({cost} power): {detail}",
                            character_id=actor.id, location=city_id)


def process_messages(orders_by_player: Dict[str, List[Order]],
                     game_state: GameState, turn_log: TurnLog):
    """
    SAY and TELL: deliver a message to other players.

    rules.md: "A character may give a message to any other character. If they
    are not in the same location, then inexpensive and readily available magic
    will be used to transmit the message" — so there is no distance rule and no
    cost. A message may also go to everyone at a town, or to every player.

    Delivery is a log event addressed to the recipient's faction, which is
    exactly how the reporting layer already routes per-player text.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, MessageOrder) or order.warnings:
                continue
            sender = game_state.characters.get(order.actor_id)
            if not sender:
                continue

            body = order.message.strip()
            if len(body) > config.MESSAGE_MAX_LENGTH:
                body = body[:config.MESSAGE_MAX_LENGTH]
                turn_log.add("message", player_id, "message_truncated",
                            f"{sender.name}'s message was truncated to "
                            f"{config.MESSAGE_MAX_LENGTH} characters",
                            character_id=sender.id, success=False)

            audience = _message_audience(order, game_state)
            if not audience:
                turn_log.add("message", player_id, "message_failed",
                            f"{sender.name}'s message reached nobody",
                            character_id=sender.id, success=False)
                continue

            for faction_id, described in sorted(audience.items()):
                # The sender already gets a confirmation below; hearing their
                # own broadcast read back to them is just noise.
                if faction_id == player_id:
                    continue
                turn_log.add("message", faction_id, "message_received",
                            f"{sender.name} says to {described}: \"{body}\"",
                            character_id=sender.id)
            turn_log.add("message", player_id, "message_sent",
                        f"{sender.name} sent a message to "
                        f"{_message_target_name(order, game_state)}",
                        character_id=sender.id)


def _message_target_name(order: MessageOrder, game_state: GameState) -> str:
    """How to describe a message's addressee back to the sender."""
    if order.to_everyone:
        return "everyone"
    if order.recipient_city_id:
        return f"everyone in {order.recipient_city_name}"
    return ", ".join(order.recipient_names) or "nobody"


def _message_audience(order: MessageOrder,
                      game_state: GameState) -> Dict[str, str]:
    """
    Which factions hear this message, and how the delivery is addressed.

    A prisoner's own player still receives anything sent to them, per rules.md,
    which falls out of keying on the character's faction rather than on who is
    holding them.
    """
    audience: Dict[str, str] = {}

    if order.to_everyone:
        for faction_id in game_state.factions:
            audience[faction_id] = "everyone"
        return audience

    if order.recipient_city_id:
        for character in game_state.characters.values():
            if (character.location_city_id == order.recipient_city_id
                    and not character.is_dead):
                audience[character.faction_id] = (
                    f"everyone in {order.recipient_city_name}")

    for recipient_id in order.recipient_ids:
        recipient = game_state.characters.get(recipient_id)
        if not recipient or recipient.is_dead:
            continue
        audience[recipient.faction_id] = recipient.name

    return audience


def process_post(orders_by_player: Dict[str, List[Order]],
                 game_state: GameState, turn_log: TurnLog):
    """
    POST a notice at the gates of a town the faction has secured.

    rules.md: only in a town secured by one of your characters, and the poster
    must be there — though not necessarily the one who secured it. An empty
    message takes the notice down. Everyone inside or just outside the gates is
    told when a notice goes up or changes.
    """
    for player_id, orders in orders_by_player.items():
        faction = game_state.factions.get(player_id)
        for order in orders:
            if not isinstance(order, PostOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor or not faction:
                continue
            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            if city.id not in faction.secured_city_ids:
                turn_log.add("message", player_id, "post_failed",
                            f"{actor.name} cannot post at {city.name}: your "
                            f"faction has not secured it",
                            character_id=actor.id, location=city.id,
                            success=False)
                continue

            body = order.message.strip()
            if len(body) > config.POST_MAX_LENGTH:
                turn_log.add("message", player_id, "post_failed",
                            f"{actor.name}'s notice is longer than "
                            f"{config.POST_MAX_LENGTH} characters and was "
                            f"rejected",
                            character_id=actor.id, location=city.id,
                            success=False)
                continue

            if not body:
                game_state.posted_messages.pop(city.id, None)
                turn_log.add("message", player_id, "post_removed",
                            f"{actor.name} took down the notice at {city.name}",
                            character_id=actor.id, location=city.id)
                continue

            game_state.posted_messages[city.id] = body
            turn_log.add("message", player_id, "post",
                        f"{actor.name} posted a notice at {city.name}: \"{body}\"",
                        character_id=actor.id, location=city.id)

            # Everyone at the gates sees a notice go up.
            for faction_id in _factions_at_gates(city.id, game_state):
                if faction_id == player_id:
                    continue
                turn_log.add("message", faction_id, "post_seen",
                            f"A notice at the gates of {city.name} reads: "
                            f"\"{body}\"",
                            location=city.id)


def _factions_at_gates(city_id: str, game_state: GameState) -> set:
    """
    Factions with somebody inside or just outside a town.

    Those hiding *near* the town are not at the gates and do not see notices.
    """
    return {
        character.faction_id for character in game_state.characters.values()
        if character.location_city_id == city_id and not character.is_dead
        and character.location_position != LocationPosition.NEAR
    }


def process_report(orders_by_player: Dict[str, List[Order]],
                   game_state: GameState, turn_log: TurnLog,
                   rng: random.Random):
    """
    REPORT and QUERY: ask a character what they can see.

    rules.md: the report covers the reporter's own status plus what they can
    learn of the location. `briefly` drops the skill lists and the other people
    at the location. QUERY differs only in reaching a busy subordinate, which
    the engine gets for free: an order that has been released for this turn
    executes regardless of what else its actor is doing.
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, ReportOrder) or order.warnings:
                continue
            for subject_id in order.subject_ids:
                subject = game_state.characters.get(subject_id)
                if not subject or subject.is_dead:
                    turn_log.add("report", player_id, "report_failed",
                                "No report: that character is gone",
                                success=False)
                    continue
                for line in _compose_report(subject, order.brief, game_state, rng):
                    turn_log.add("report", player_id, "report", line,
                                character_id=subject.id,
                                location=subject.location_city_id)


def _compose_report(subject: Character, brief: bool, game_state: GameState,
                    rng: random.Random) -> List[str]:
    """
    Build one character's report.

    The full form follows the shape of the example in `rules.md`: the reporter
    and their group, then what else is notable at the location. The brief form
    keeps the first line and drops the skills and the neighbours.
    """
    city = game_state.world_map.cities.get(subject.location_city_id)
    city_name = city.name if city else "an unknown place"

    skills = ""
    if not brief:
        parts = [f"{label} {value}" for label, value in (
            ("combat", subject.combat_skill), ("magic", subject.magic_skill),
            ("religion", subject.religion_skill),
            ("trading", subject.trading_skill)) if value]
        skills = f" ({', '.join(parts)})" if parts else ""

    soldiers = groups.group_soldier_count(subject, game_state)
    followers = groups.group_members(subject.id, game_state)

    # The rules' example names the people in the group before counting the
    # unnamed units: "Captain John May (combat 20, magic 25), Adept Carolyn
    # Bond, 39 soldiers, 307 gold, currently awaiting orders in Umadosh."
    tail = [c.name for c in sorted(followers, key=lambda c: c.name)]
    if soldiers:
        tail.append(f"{soldiers} soldiers")
    tail.append(f"{subject.gold:,.0f} gold")

    head = (f"{subject.name}{skills}, {', '.join(tail)}, "
            f"currently {subject.location_position.value} {city_name}")
    lines = [("Brief report: " if brief else "Report: ") + head]

    if brief:
        return lines

    posted = game_state.posted_messages.get(subject.location_city_id)
    if posted and subject.location_position != LocationPosition.NEAR:
        lines.append(f"  A notice at the gates of {city_name} reads: \"{posted}\"")

    # Who else the reporter can make out, under the ordinary fog rules.
    if city:
        seen = sorted(
            (other for other in game_state.characters.values()
             if other.id != subject.id and not other.is_dead
             and other.location_city_id == subject.location_city_id
             and other.faction_id != subject.faction_id
             and fog.detects(subject, other, city, game_state, rng)),
            key=lambda c: c.name,
        )
        if seen:
            lines.append(f"  Other notable people in {city_name}: "
                         + ", ".join(c.name for c in seen))
    return lines


def process_address_and_password(orders_by_player: Dict[str, List[Order]],
                                 game_state: GameState, turn_log: TurnLog,
                                 rng: random.Random):
    """
    ADDRESS and PASSWORD: change a player's contact details.

    rules.md treats both as taking effect as soon as they are parsed rather
    than as things a character does, so neither needs an actor or a location.
    A password under eight characters is replaced by a generated one, and one
    over sixty-four is truncated.
    """
    for player_id, orders in orders_by_player.items():
        faction = game_state.factions.get(player_id)
        if not faction:
            continue
        for order in orders:
            if isinstance(order, AddressOrder) and not order.warnings:
                faction.email = order.address.strip()
                turn_log.add("message", player_id, "address",
                            f"Reports will now be sent to {faction.email}")

            elif isinstance(order, PasswordOrder) and not order.warnings:
                password = order.password.strip()
                if len(password) < config.PASSWORD_MIN_LENGTH:
                    password = "".join(
                        rng.choice("abcdefghijkmnpqrstuvwxyz23456789")
                        for _ in range(config.PASSWORD_MIN_LENGTH + 4))
                    faction.password = password
                    turn_log.add("message", player_id, "password",
                                f"That password was shorter than "
                                f"{config.PASSWORD_MIN_LENGTH} characters, so "
                                f"one was generated for you: {password}")
                    continue
                faction.password = password[:config.PASSWORD_MAX_LENGTH]
                turn_log.add("message", player_id, "password",
                            "Your password has been changed")


def expire_postings(game_state: GameState, turn_log: TurnLog):
    """
    Take down notices at towns nobody secures any more.

    rules.md: "A posting will remain in effect until you no longer secure the
    location." Ownership can change through combat, so this is checked at the
    end of every turn rather than only when a POST is issued.
    """
    secured = set()
    for faction in game_state.factions.values():
        secured |= faction.secured_city_ids

    for city_id in list(game_state.posted_messages):
        if city_id in secured:
            continue
        del game_state.posted_messages[city_id]
        city = game_state.world_map.cities.get(city_id)
        if city:
            turn_log.add("message", "", "post_lapsed",
                        f"The notice at {city.name} has come down: nobody "
                        f"secures the town any more", location=city_id)


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


def process_sightings(game_state: GameState, turn_log: TurnLog, rng: random.Random):
    """
    End-of-turn fog of war: each faction's living characters try to notice
    others at the same city under the position and LURK rules.
    """
    for faction_id in sorted(game_state.factions.keys()):
        # Independent stream per faction so adding a player does not reshuffle
        # everyone else's sightings under the same turn seed.
        faction_rng = random.Random(rng.randint(0, 2**31 - 1))
        for sighting in fog.collect_sightings(game_state, faction_id, faction_rng):
            turn_log.add(
                "sighting",
                faction_id,
                "spotted",
                fog.format_sighting(sighting),
                location=sighting.city_id,
                character_id=sighting.observer_id,
            )


def process_get(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Process GET/TAKE/OBTAIN — inverse of ASSIGN/GIVE."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, GetOrder) or order.warnings:
                continue
            recipient = game_state.characters.get(order.actor_id)
            donor = game_state.characters.get(order.donor_id)
            if not recipient or not donor:
                continue

            # Cannot take from another player's free character
            donor_is_prisoner = donor.is_prisoner and donor.captor_id == recipient.id
            if donor.faction_id != player_id and not donor_is_prisoner:
                turn_log.add("get", player_id, "get_failed",
                            f"{recipient.name}: cannot take from {donor.name} (not under your control)",
                            character_id=recipient.id, success=False)
                continue

            if recipient.location_city_id != donor.location_city_id:
                turn_log.add("get", player_id, "get_failed",
                            f"{recipient.name}: {donor.name} is not at the same location",
                            character_id=recipient.id, success=False)
                continue

            # Character-join form: no gold/units/resources — just co-locate
            if (order.gold_amount <= 0 and order.unit_count <= 0
                    and not order.resources):
                turn_log.add("get", player_id, "get_join",
                            f"{donor.name} joined {recipient.name}",
                            character_id=recipient.id)
                continue

            if order.gold_amount > 0:
                donor_faction = game_state.factions.get(donor.faction_id)
                if debit_gold(donor, donor_faction if donor.faction_id == player_id else None,
                              order.gold_amount):
                    credit_gold(recipient, order.gold_amount)
                    turn_log.add("get", player_id, "get_gold",
                                f"{recipient.name} took {order.gold_amount}g from {donor.name}",
                                character_id=recipient.id)
                else:
                    turn_log.add("get", player_id, "get_failed",
                                f"{recipient.name}: {donor.name} has insufficient gold",
                                character_id=recipient.id, success=False)
                    continue

            for kind, wanted in order.resources.items():
                amount = wanted if wanted >= 0 else donor.resources.get(kind, 0)
                if donor.resources.get(kind, 0) < amount:
                    turn_log.add("get", player_id, "get_failed",
                                f"{recipient.name}: {donor.name} has "
                                f"insufficient {kind}",
                                character_id=recipient.id, success=False)
                    continue
                donor.resources[kind] = donor.resources.get(kind, 0) - amount
                recipient.resources[kind] = (
                    recipient.resources.get(kind, 0) + amount)
                turn_log.add("get", player_id, "get_resource",
                            f"{recipient.name} took {amount} {kind} "
                            f"from {donor.name}",
                            character_id=recipient.id)

            if order.unit_count > 0 and order.unit_type:
                donor_stack = next(
                    (s for s in game_state.unit_stacks.values()
                     if s.faction_id == donor.faction_id
                     and s.location_city_id == donor.location_city_id
                     and s.unit_type.name == order.unit_type),
                    None,
                )
                if not donor_stack or donor_stack.count < order.unit_count:
                    turn_log.add("get", player_id, "get_failed",
                                f"{recipient.name}: not enough {order.unit_type.lower()}s to take",
                                character_id=recipient.id, success=False)
                    continue
                donor_stack.count -= order.unit_count
                recip_stack = next(
                    (s for s in game_state.unit_stacks.values()
                     if s.faction_id == recipient.faction_id
                     and s.location_city_id == recipient.location_city_id
                     and s.unit_type.name == order.unit_type),
                    None,
                )
                if recip_stack:
                    recip_stack.count += order.unit_count
                else:
                    sid = allocate_id(game_state.unit_stacks, "stack")
                    game_state.unit_stacks[sid] = UnitStack(
                        id=sid,
                        faction_id=recipient.faction_id,
                        location_city_id=recipient.location_city_id,
                        unit_type=UnitType[order.unit_type],
                        count=order.unit_count,
                    )
                if donor_stack.count <= 0:
                    del game_state.unit_stacks[donor_stack.id]
                turn_log.add("get", player_id, "get_units",
                            f"{recipient.name} took {order.unit_count} "
                            f"{order.unit_type.lower()}s from {donor.name}",
                            character_id=recipient.id)


def process_transfer(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Banking-guild gold transfer with fee."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, TransferOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            recipient = game_state.characters.get(order.recipient_id)
            if not actor or not recipient:
                continue
            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                turn_log.add("transfer", player_id, "transfer_failed",
                            f"{actor.name}: no banking office here",
                            character_id=actor.id, success=False)
                continue

            faction = game_state.factions.get(player_id)
            amount = order.gold_amount
            if amount <= 0:
                amount = int(available_gold(actor, faction))
            if amount <= 0:
                turn_log.add("transfer", player_id, "transfer_failed",
                            f"{actor.name}: nothing to transfer",
                            character_id=actor.id, success=False)
                continue

            fee = config.transfer_fee(amount)
            total = amount + fee
            if not debit_gold(actor, faction, total):
                turn_log.add("transfer", player_id, "transfer_failed",
                            f"{actor.name}: need {total}g ({amount}g + {fee}g fee)",
                            character_id=actor.id, success=False)
                continue

            credit_gold(recipient, amount)
            turn_log.add("transfer", player_id, "transfer_success",
                        f"{actor.name} transferred {amount}g to {recipient.name} "
                        f"(fee {fee}g)",
                        character_id=actor.id)


def process_unload(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """
    Process UNLOAD -- turn a member of your group loose without ordering them
    to do anything.

    rules.md: "you can always make a character a group leader by simply giving
    him an order. However, the UNLOAD command is useful when you simply want a
    character to become a group leader and not do anything else."
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, UnloadOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            if not actor:
                continue
            for tid, tname in zip(order.target_ids, order.target_names):
                target = game_state.characters.get(tid)
                if not target or target.faction_id != player_id:
                    turn_log.add("unload", player_id, "unload_failed",
                                f"{actor.name}: cannot unload {tname}",
                                character_id=actor.id, success=False)
                    continue
                if target.location_city_id != actor.location_city_id:
                    turn_log.add("unload", player_id, "unload_failed",
                                f"{actor.name}: {target.name} is not co-located",
                                character_id=actor.id, success=False)
                    continue
                if not groups.detach(target):
                    turn_log.add("unload", player_id, "unload_failed",
                                f"{actor.name}: {target.name} already leads their own group",
                                character_id=actor.id, success=False)
                    continue
                turn_log.add("unload", player_id, "unload_success",
                            f"{actor.name} unloaded {target.name}, who now leads their own group",
                            character_id=actor.id)


def process_pay(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Pay down wage debt from the actor's purse."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, PayOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            faction = game_state.factions.get(player_id)
            if not actor or not faction:
                continue

            if order.gold_amount > 0:
                amount = float(order.gold_amount)
            else:
                # Pay off debt only (no surplus) when amount omitted
                amount = min(faction.wage_debt, available_gold(actor, faction))

            if amount <= 0:
                turn_log.add("pay", player_id, "pay_failed",
                            f"{actor.name}: nothing to pay",
                            character_id=actor.id, success=False)
                continue
            if not debit_gold(actor, faction, amount):
                turn_log.add("pay", player_id, "pay_failed",
                            f"{actor.name}: insufficient gold",
                            character_id=actor.id, success=False)
                continue

            faction.wage_debt = round(faction.wage_debt - amount, 1)
            # Negative debt = surplus credit (rules allow this)
            label = "debt" if faction.wage_debt >= 0 else "surplus"
            turn_log.add("pay", player_id, "pay_success",
                        f"{actor.name} paid {amount}g toward wages "
                        f"({label} now {abs(faction.wage_debt)}g)",
                        character_id=actor.id)


def process_borrow(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                   turn_log: TurnLog, rng: random.Random):
    """Borrow gold from the bankers guild."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, BorrowOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            faction = game_state.factions.get(player_id)
            if not actor or not faction:
                continue
            city = game_state.world_map.cities.get(actor.location_city_id)
            if not city:
                continue

            amount = order.gold_amount or config.BORROW_MAX_AMOUNT
            # Chance scales with city size and character impressiveness
            band_bonus = {
                "TINY": -0.15, "SMALL": 0.0, "MEDIUM": 0.1, "LARGE": 0.2,
            }
            # PopulationBand is enum with values like "< 10k" — use name
            band_name = city.population_band.name if hasattr(city.population_band, "name") else "SMALL"
            impress = (actor.combat_skill + actor.magic_skill + actor.religion_skill
                       + actor.trading_skill) / 200
            debt_penalty = min(0.4, faction.loan_balance / 2000)
            chance = config.BORROW_BASE_CHANCE + band_bonus.get(band_name, 0) + impress - debt_penalty
            chance = max(0.05, min(0.95, chance))

            if rng.random() > chance:
                turn_log.add("borrow", player_id, "borrow_failed",
                            f"{actor.name}: loan of {amount}g refused in {city.name}",
                            character_id=actor.id, success=False)
                continue

            credit_gold(actor, amount)
            faction.loan_balance = round(faction.loan_balance + amount, 2)
            faction.loan_grace_turns = max(faction.loan_grace_turns, config.BORROW_GRACE_TURNS)
            turn_log.add("borrow", player_id, "borrow_success",
                        f"{actor.name} borrowed {amount}g in {city.name} "
                        f"(balance {faction.loan_balance}g)",
                        character_id=actor.id)


def process_repay(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """Repay bankers-guild debt."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, RepayOrder) or order.warnings:
                continue
            actor = game_state.characters.get(order.actor_id)
            faction = game_state.factions.get(player_id)
            if not actor or not faction:
                continue

            if faction.loan_balance <= 0:
                turn_log.add("repay", player_id, "repay_failed",
                            f"{actor.name}: no outstanding loan",
                            character_id=actor.id, success=False)
                continue

            if order.gold_amount > 0:
                amount = min(float(order.gold_amount), faction.loan_balance)
            else:
                amount = min(faction.loan_balance, available_gold(actor, faction))

            if amount <= 0:
                turn_log.add("repay", player_id, "repay_failed",
                            f"{actor.name}: nothing to repay with",
                            character_id=actor.id, success=False)
                continue
            if not debit_gold(actor, faction, amount):
                turn_log.add("repay", player_id, "repay_failed",
                            f"{actor.name}: insufficient gold",
                            character_id=actor.id, success=False)
                continue

            faction.loan_balance = round(faction.loan_balance - amount, 2)
            if faction.loan_balance <= 0:
                faction.loan_balance = 0.0
                faction.loan_grace_turns = 0
            turn_log.add("repay", player_id, "repay_success",
                        f"{actor.name} repaid {amount}g "
                        f"(loan balance {faction.loan_balance}g)",
                        character_id=actor.id)


def process_study(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog, rng):
    """Process STUDY orders for character skill training."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, StudyOrder):
                continue

            if order.warnings:
                continue

            actor = game_state.characters.get(order.actor_id)
            if not actor or actor.is_dead:
                continue

            faction = game_state.factions.get(player_id)
            if not faction:
                continue

            # Cost: 1 gold per week
            cost = order.duration_weeks
            if not debit_gold(actor, faction, cost):
                turn_log.add("study", player_id, "study_failed",
                            f"{actor.name}: insufficient gold to study (need {cost}g)",
                            character_id=actor.id, success=False)
                continue

            # Get current skill level
            if order.skill_name == "combat":
                current_skill = actor.combat_skill
            elif order.skill_name == "magic":
                current_skill = actor.magic_skill
            elif order.skill_name == "religion":
                current_skill = actor.religion_skill
            elif order.skill_name == "sailing":
                current_skill = actor.sailing_skill
            else:
                continue

            # Study for each week
            for week in range(order.duration_weeks):
                if current_skill >= 100:
                    break

                # Gain 1-5 points per week (simplified - no partial tracking in alpha)
                gain = rng.randint(1, 5)
                current_skill = min(100, current_skill + gain)

            # Update skill
            if order.skill_name == "combat":
                actor.combat_skill = current_skill
            elif order.skill_name == "magic":
                actor.magic_skill = current_skill
            elif order.skill_name == "religion":
                actor.religion_skill = current_skill
            elif order.skill_name == "sailing":
                actor.sailing_skill = current_skill

            turn_log.add("study", player_id, "study_success",
                        f"{actor.name}: studied {order.skill_name} for {order.duration_weeks} weeks (now level {current_skill})",
                        character_id=actor.id)


def process_teach(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog, rng):
    """Process TEACH orders for character skill training."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, TeachOrder):
                continue

            if order.warnings:
                continue

            teacher = game_state.characters.get(order.teacher_id)
            student = game_state.characters.get(order.student_id)

            if not teacher or teacher.is_dead or not student or student.is_dead:
                continue

            # Check same location
            if teacher.location_city_id != student.location_city_id:
                turn_log.add("teach", player_id, "teach_failed",
                            f"{teacher.name}: {student.name} is not at the same location",
                            character_id=teacher.id, success=False)
                continue

            # Get teacher's skill level
            if order.skill_name == "combat":
                teacher_skill = teacher.combat_skill
                student_skill = student.combat_skill
            elif order.skill_name == "magic":
                teacher_skill = teacher.magic_skill
                student_skill = student.magic_skill
            elif order.skill_name == "religion":
                teacher_skill = teacher.religion_skill
                student_skill = student.religion_skill
            elif order.skill_name == "sailing":
                teacher_skill = teacher.sailing_skill
                student_skill = student.sailing_skill
            else:
                continue

            # Teacher must have higher skill
            if teacher_skill <= student_skill:
                turn_log.add("teach", player_id, "teach_failed",
                            f"{teacher.name}: cannot teach {student.name} {order.skill_name} (teacher skill {teacher_skill} <= student skill {student_skill})",
                            character_id=teacher.id, success=False)
                continue

            # Teach for each week (no cost, better gains than studying)
            for week in range(order.duration_weeks):
                if student_skill >= 100 or student_skill >= teacher_skill:
                    break

                # Gain 2-7 points per week with teacher (better than self-study)
                gain = rng.randint(2, 7)
                student_skill = min(100, min(teacher_skill, student_skill + gain))

            # Update skill
            if order.skill_name == "combat":
                student.combat_skill = student_skill
            elif order.skill_name == "magic":
                student.magic_skill = student_skill
            elif order.skill_name == "religion":
                student.religion_skill = student_skill
            elif order.skill_name == "sailing":
                student.sailing_skill = student_skill

            turn_log.add("teach", player_id, "teach_success",
                        f"{teacher.name}: taught {student.name} {order.skill_name} for {order.duration_weeks} weeks (now level {student_skill})",
                        character_id=teacher.id)


# ============================================================================
# PRISONERS
# ============================================================================

def process_prisoner_escape(game_state: GameState, turn_log: TurnLog, rng: random.Random):
    """Allow prisoners a small chance to escape each turn."""
    for prisoner in game_state.characters.values():
        if not prisoner.is_prisoner or prisoner.is_dead:
            continue

        if rng.random() < 0.1:
            prisoner.is_prisoner = False
            prisoner.captor_id = ""
            turn_log.add("prisoner", prisoner.faction_id, "escape",
                        f"{prisoner.name} escaped captivity", character_id=prisoner.id)


# ============================================================================
# PHASE 8: CLEANUP
# ============================================================================

def cleanup_turn(game_state: GameState):
    """Perform end-of-turn cleanup."""
    # Reset movement points
    for char in game_state.characters.values():
        char.movement_points = config.CHARACTER_MOVEMENT_POINTS_PER_TURN

    # Restore magic and religious power
    for char in game_state.characters.values():
        char.magic_power_current = char.max_magic_power
        char.religious_power_current = char.max_religious_power

    # Natural healing: 1 point per day, weekly turn = 7 points
    for char in game_state.characters.values():
        if not char.is_dead and char.health < 100:
            char.health = min(100, char.health + 7)

    # Increment turn
    game_state.turn_number += 1


# ============================================================================
# MAIN TURN FUNCTION
# ============================================================================

def run_turn(
    game_state: GameState,
    orders_by_player: Dict[str, List[Order]],
    seed: int
) -> Tuple[GameState, TurnLog]:
    """
    Process a complete game turn deterministically.

    Orders are not executed straight from `orders_by_player`. They go onto each
    character's persistent queue first, and the queue decides what this turn
    actually runs -- which for an unblocked character is everything they were
    just given. See `order_queue` for what holds work back.

    Args:
        game_state: Current game state (will be modified in-place)
        orders_by_player: Dict mapping player_id -> list of orders submitted now
        seed: RNG seed for deterministic execution

    Returns:
        Tuple of (updated_game_state, turn_log)
    """
    rng = random.Random(seed)
    turn_log = TurnLog()

    # Phase 0: Order queue. Everything below acts on what the queue released.
    orders_by_player = order_queue.process_order_queue(
        orders_by_player, game_state, turn_log
    )

    # Phase 0b: IF statements. A condition reached on the queue is judged
    # against the world it lands in, and its chosen branch joins the turn.
    process_if_orders(orders_by_player, game_state, turn_log)

    # Phase 1: Validation
    validate_orders(orders_by_player, game_state, turn_log)

    # Phase 1a: Offers. Resolved before group leadership so an accepted
    # independent character joins the faction before any order naming them
    # (the HAVE-promotes-to-leader pass) runs. A refusal fails the chained
    # orders that assumed acceptance.
    refusals = process_offer(orders_by_player, game_state, turn_log)
    for player_id, char_id in refusals:
        for order in orders_by_player.get(player_id, []):
            if (actor_id_of(order) == char_id and order.explicit_actor
                    and not isinstance(order, OfferOrder)):
                order.warnings.append(
                    "The offer to this character was refused, so their "
                    "assumed orders failed")

    # Phase 1b: Group leadership. A character given a direct order becomes a
    # group leader before the order that named them is carried out.
    process_group_leadership(orders_by_player, game_state, turn_log)

    # Phase 2: Movement
    process_movement(orders_by_player, game_state, turn_log, rng)

    # Phase 2b: Sailing, then buying passage (which is sea travel without a
    # ship) -- and elite units follow whoever led them on the way.
    process_sail(orders_by_player, game_state, turn_log, rng)
    process_passage(orders_by_player, game_state, turn_log, rng)
    sync_elite_locations(game_state)

    # Phase 3: Recruit & Buy
    process_recruit_and_buy(orders_by_player, game_state, turn_log, rng)

    # Phase 4: Magic & Summoning. ABSORB runs first so power drawn out of an
    # item is available to this turn's spells, and CHARGE last so what the
    # caster did not spend can be stowed.
    process_absorb(orders_by_player, game_state, turn_log)
    process_magic(orders_by_player, game_state, turn_log, rng)
    process_summon(orders_by_player, game_state, turn_log)
    process_conjure(orders_by_player, game_state, turn_log, rng)
    process_charge(orders_by_player, game_state, turn_log)
    process_religion(orders_by_player, game_state, turn_log, rng)

    # Walking, sailing, flying and teleporting have all resolved by now, so one
    # sweep catches everyone who ended up somewhere magic cannot exist.
    process_magic_free_zones(game_state, turn_log)

    # Phase 5: Combat
    process_combat(orders_by_player, game_state, turn_log, rng)

    # Phase 5b: Capture (prisoner taking)
    process_capture(orders_by_player, game_state, turn_log, rng)

    # Phase 6: Income & Upkeep. The weekly INVEST check runs first so the
    # growth it pays for counts in this turn's income.
    process_invest_weekly(game_state, turn_log, rng)
    process_income_and_upkeep(game_state, turn_log, rng)

    # Phase 7: Location Control & Diplomacy & Unit Management & Economics & Training
    process_secure(orders_by_player, game_state, turn_log)
    process_fortifications(orders_by_player, game_state, turn_log)
    process_diplomacy(orders_by_player, game_state, turn_log)
    process_assign(orders_by_player, game_state, turn_log)
    process_join(orders_by_player, game_state, turn_log)
    process_support(orders_by_player, game_state, turn_log)
    process_name(orders_by_player, game_state, turn_log)
    process_promote(orders_by_player, game_state, turn_log)
    process_tax(orders_by_player, game_state, turn_log)
    process_trade(orders_by_player, game_state, turn_log)
    process_collect(orders_by_player, game_state, turn_log)
    process_mine(orders_by_player, game_state, turn_log)
    process_build(orders_by_player, game_state, turn_log)
    process_free(orders_by_player, game_state, turn_log)
    process_kill(orders_by_player, game_state, turn_log)
    process_enslave(orders_by_player, game_state, turn_log)
    process_interrogate(orders_by_player, game_state, turn_log, rng)
    process_status_orders(orders_by_player, game_state, turn_log)
    process_get(orders_by_player, game_state, turn_log)
    process_transfer(orders_by_player, game_state, turn_log)
    process_unload(orders_by_player, game_state, turn_log)
    process_pay(orders_by_player, game_state, turn_log)
    process_borrow(orders_by_player, game_state, turn_log, rng)
    process_repay(orders_by_player, game_state, turn_log)
    process_study(orders_by_player, game_state, turn_log, rng)
    process_teach(orders_by_player, game_state, turn_log, rng)
    process_probe(orders_by_player, game_state, turn_log, rng)
    process_search(orders_by_player, game_state, turn_log, rng)
    process_scan(orders_by_player, game_state, turn_log)
    process_work(orders_by_player, game_state, turn_log)
    process_train(orders_by_player, game_state, turn_log)
    process_unname(orders_by_player, game_state, turn_log)
    process_create(orders_by_player, game_state, turn_log)
    process_invest(orders_by_player, game_state, turn_log)
    process_preach(orders_by_player, game_state, turn_log, rng)

    # Communication. SECURE has already resolved above, so a POST is judged
    # against who holds the town at the end of this turn, and REPORT last of
    # all so it describes the world the player will actually wake up to.
    process_address_and_password(orders_by_player, game_state, turn_log, rng)
    process_messages(orders_by_player, game_state, turn_log)
    process_post(orders_by_player, game_state, turn_log)
    process_report(orders_by_player, game_state, turn_log, rng)
    report_pending_orders(game_state, turn_log)

    # Phase 8: Fog of war — who noticed whom after all movement and status
    # changes for the turn have settled.
    process_sightings(game_state, turn_log, rng)

    # Phase 9: Cleanup. Item upkeep runs before `cleanup_turn` refills everyone
    # to full power, so a crystal only charges off a possessor who really did
    # end the turn at their natural maximum.
    expire_support(game_state, turn_log)
    expire_postings(game_state, turn_log)
    process_item_upkeep(game_state, turn_log)
    process_prisoner_escape(game_state, turn_log, rng)
    sync_elite_locations(game_state)
    process_elite_upkeep(game_state, turn_log)
    cleanup_turn(game_state)

    return (game_state, turn_log)
