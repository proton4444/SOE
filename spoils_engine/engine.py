"""
Turn processing engine for Spoils of Empire.

Processes orders in deterministic phases and updates game state.
All randomness is controlled by a seeded RNG for reproducibility.
"""

import random
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import heapq

from spoils_engine.models import (
    GameState, Character, UnitStack, Ship, City,
    UnitType, ShipType, RoadQuality
)
from spoils_engine.orders import (
    Order, MoveOrder, SailOrder, RecruitOrder, BuyShipOrder, AttackOrder, TeleportOrder, HealOrder,
    SecureOrder, AllyOrder, EnemyOrder, NeutralOrder
)
from spoils_engine import config
from spoils_engine.combat import CombatResolver, calculate_faction_power, apply_casualties


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
# PATHFINDING
# ============================================================================

def find_shortest_path(start_city_id: str, end_city_id: str, game_state: GameState) -> Tuple[List[str], float]:
    """
    Find shortest path between two cities using Dijkstra's algorithm.

    Returns:
        Tuple of (path_as_city_ids, total_cost)
    """
    if start_city_id == end_city_id:
        return ([start_city_id], 0.0)

    # Dijkstra's algorithm
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

        # Check neighbors
        for neighbor_city, road in game_state.world_map.neighbors(current_id):
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


def find_sea_route(start_city_id: str, end_city_id: str, game_state: GameState) -> Tuple[List[str], float]:
    """
    Find shortest sea route between two cities using only sea lanes.

    Returns:
        Tuple of (path_as_city_ids, total_cost)
    """
    if start_city_id == end_city_id:
        return ([start_city_id], 0.0)

    # Dijkstra's algorithm (only using SEA roads)
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

        # Check neighbors (only sea lanes)
        for neighbor_city, road in game_state.world_map.neighbors(current_id):
            if road.quality != RoadQuality.SEA:
                continue  # Skip land routes

            if neighbor_city.id in visited:
                continue

            cost = config.get_movement_cost(road.quality)
            new_dist = current_dist + cost

            if neighbor_city.id not in distances or new_dist < distances[neighbor_city.id]:
                distances[neighbor_city.id] = new_dist
                previous[neighbor_city.id] = current_id
                heapq.heappush(pq, (new_dist, neighbor_city.id))

    # No sea route found
    return ([], float('inf'))


# ============================================================================
# PHASE 1: VALIDATION
# ============================================================================

def validate_orders(orders_by_player: Dict[str, List[Order]], game_state: GameState, turn_log: TurnLog):
    """
    Validate all orders and mark invalid ones with warnings.

    This phase checks:
    - Actor exists and belongs to player
    - Cities/targets exist
    - Basic preconditions (e.g., only ports can build ships)
    """
    for player_id, orders in orders_by_player.items():
        for order in orders:
            # Check MoveOrder
            if isinstance(order, MoveOrder):
                if not order.actor_id:
                    order.warnings.append("No actor specified")
                    continue

                actor = game_state.characters.get(order.actor_id)
                if not actor:
                    order.warnings.append(f"Character {order.actor_id} not found")
                    continue

                if actor.faction_id != player_id:
                    order.warnings.append(f"Character does not belong to you")
                    continue

                if not game_state.world_map.cities.get(order.destination_city_id):
                    order.warnings.append(f"Destination city not found")

            # Check SailOrder
            elif isinstance(order, SailOrder):
                if not order.actor_id:
                    order.warnings.append("No actor specified")
                    continue

                actor = game_state.characters.get(order.actor_id)
                if not actor:
                    order.warnings.append(f"Character {order.actor_id} not found")
                    continue

                if actor.faction_id != player_id:
                    order.warnings.append(f"Character does not belong to you")
                    continue

                if not game_state.world_map.cities.get(order.destination_city_id):
                    order.warnings.append(f"Destination city not found")

            # Check RecruitOrder
            elif isinstance(order, RecruitOrder):
                if not order.actor_id:
                    order.warnings.append("No actor specified")
                    continue

                actor = game_state.characters.get(order.actor_id)
                if not actor:
                    order.warnings.append(f"Character {order.actor_id} not found")
                    continue

                if actor.faction_id != player_id:
                    order.warnings.append(f"Character does not belong to you")
                    continue

                if not game_state.world_map.cities.get(order.city_id):
                    order.warnings.append(f"City not found")

                try:
                    UnitType(order.unit_type)
                except ValueError:
                    order.warnings.append(f"Invalid unit type '{order.unit_type}'")

            # Check BuyShipOrder
            elif isinstance(order, BuyShipOrder):
                if not order.actor_id:
                    order.warnings.append("No actor specified")
                    continue

                actor = game_state.characters.get(order.actor_id)
                if not actor:
                    order.warnings.append(f"Character {order.actor_id} not found")
                    continue

                if actor.faction_id != player_id:
                    order.warnings.append(f"Character does not belong to you")
                    continue

                city = game_state.world_map.cities.get(order.city_id)
                if not city:
                    order.warnings.append(f"City not found")
                elif not city.is_port:
                    order.warnings.append(f"City {city.name} is not a port")

                try:
                    ShipType(order.ship_type)
                except ValueError:
                    order.warnings.append(f"Invalid ship type '{order.ship_type}'")

            # Check AttackOrder
            elif isinstance(order, AttackOrder):
                if not order.actor_id:
                    order.warnings.append("No actor specified")
                    continue

                actor = game_state.characters.get(order.actor_id)
                if not actor:
                    order.warnings.append(f"Character {order.actor_id} not found")
                    continue

                if actor.faction_id != player_id:
                    order.warnings.append(f"Character does not belong to you")
                    continue

            # Check TeleportOrder
            elif isinstance(order, TeleportOrder):
                if not order.actor_id:
                    order.warnings.append("No actor specified")
                    continue

                actor = game_state.characters.get(order.actor_id)
                if not actor:
                    order.warnings.append(f"Character {order.actor_id} not found")
                    continue

                if actor.faction_id != player_id:
                    order.warnings.append(f"Character does not belong to you")
                    continue

                if actor.magic_skill <= 0:
                    order.warnings.append(f"Character has no magic skill")


# ============================================================================
# PHASE 2: MOVEMENT
# ============================================================================

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
                order.warnings.append(f"No path found to destination")
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

            # Move character
            start_city = game_state.world_map.cities[actor.location_city_id]
            end_city = game_state.world_map.cities[order.destination_city_id]
            actor.location_city_id = order.destination_city_id
            actor.movement_points -= int(cost)

            turn_log.add("movement", player_id, "move",
                        f"{actor.name} moved from {start_city.name} to {end_city.name} (cost: {cost:.1f})",
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

            # Move all units at the same location (simplified - assumes they're on the ship)
            for stack in game_state.unit_stacks.values():
                if stack.faction_id == player_id and stack.location_city_id == start_city.id:
                    stack.location_city_id = order.destination_city_id

            efficiency_note = f" (rowing efficiency: {rowing_efficiency * 100:.0f}%)" if rowing_efficiency < 1.0 else ""
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

                # Check cost
                unit_type_enum = UnitType(order.unit_type)
                cost = config.get_recruit_cost(unit_type_enum) * order.count

                if faction.treasury < cost:
                    order.warnings.append(f"Insufficient gold (need {cost}, have {faction.treasury})")
                    turn_log.add("recruit", player_id, "recruit_failed",
                                f"Insufficient gold to recruit {order.count} {order.unit_type}",
                                location=city.id, character_id=actor.id, success=False)
                    continue

                # Deduct gold
                faction.treasury -= cost

                # Create unit stack
                stack_id = f"stack_{player_id}_{len(game_state.unit_stacks)}_{rng.randint(1000, 9999)}"
                new_stack = UnitStack(
                    id=stack_id,
                    faction_id=player_id,
                    location_city_id=order.city_id,
                    unit_type=unit_type_enum,
                    count=order.count
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

                if faction.treasury < cost:
                    order.warnings.append(f"Insufficient gold (need {cost}, have {faction.treasury})")
                    turn_log.add("buy_ship", player_id, "buy_failed",
                                f"Insufficient gold to buy {order.count} {order.ship_type}",
                                location=city.id, character_id=actor.id, success=False)
                    continue

                # Deduct gold
                faction.treasury -= cost

                # Create ships
                for i in range(order.count):
                    ship_id = f"ship_{player_id}_{len(game_state.ships)}_{rng.randint(1000, 9999)}"
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

                if wizard.magic_power_current < power_cost:
                    order.warnings.append(f"Insufficient magic power (need {power_cost}, have {wizard.magic_power_current})")
                    turn_log.add("magic", player_id, "teleport_failed",
                                f"{wizard.name} lacks magic power to teleport {target.name}",
                                character_id=wizard.id, success=False)
                    continue

                # Deduct magic power
                wizard.magic_power_current -= power_cost

                # Teleport target
                old_city = game_state.world_map.cities[target.location_city_id]
                target.location_city_id = order.destination_city_id

                turn_log.add("magic", player_id, "teleport",
                            f"{wizard.name} teleported {target.name} from {old_city.name} to {dest_city.name}",
                            location=dest_city.id, character_id=wizard.id)

            # Process Heal
            elif isinstance(order, HealOrder):
                if order.warnings:
                    continue

                healer = game_state.characters.get(order.actor_id)
                if not healer or healer.religion_skill <= 0:
                    turn_log.add("magic", player_id, "heal_failed",
                                f"Healer has no religion skill",
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


# ============================================================================
# PHASE 5: COMBAT
# ============================================================================

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

            # Calculate powers
            attacker_power = calculate_faction_power(attacker_player_id, city_id, game_state)
            defender_power = calculate_faction_power(defender_faction_id, city_id, game_state)

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

            # Apply casualties
            attacker_losses = apply_casualties(
                attacker_player_id, city_id, result.attacker_casualties, game_state, rng
            )
            defender_losses = apply_casualties(
                defender_faction_id, city_id, result.defender_casualties, game_state, rng
            )

            # Log results
            if result.winner_id == attacker_player_id:
                turn_log.add("combat", attacker_player_id, "victory",
                            f"{attacker.name} defeated {attack_order.target_name} in {city.name} "
                            f"(lost {attacker_losses['units']} units)",
                            location=city_id, character_id=attacker.id)
                turn_log.add("combat", defender_faction_id, "defeat",
                            f"Your forces were defeated by {attacker.name} in {city.name} "
                            f"(lost {defender_losses['units']} units)",
                            location=city_id)
            else:
                turn_log.add("combat", attacker_player_id, "defeat",
                            f"{attacker.name} was defeated in {city.name} "
                            f"(lost {attacker_losses['units']} units)",
                            location=city_id, character_id=attacker.id)
                turn_log.add("combat", defender_faction_id, "victory",
                            f"Your forces successfully defended {city.name} "
                            f"(lost {defender_losses['units']} units)",
                            location=city_id)


# ============================================================================
# PHASE 6: INCOME & UPKEEP
# ============================================================================

def process_income_and_upkeep(game_state: GameState, turn_log: TurnLog):
    """Award income and deduct upkeep."""
    for faction in game_state.factions.values():
        # Calculate income from controlled cities
        income = 0
        for city_id in faction.controlled_city_ids:
            city = game_state.world_map.cities.get(city_id)
            if city:
                income += config.get_income_for_city(city.population_band)

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

        # Named character salaries (excluding leader)
        character_count = 0
        for char in game_state.characters.values():
            if char.faction_id == faction.id:
                character_count += 1
                # Skip the first character (leader) - they don't get a salary
                if character_count > 1:
                    salary = config.calculate_character_salary(
                        char.combat_skill, char.magic_skill
                    )
                    upkeep += salary

        # Round upkeep to 1 decimal place
        upkeep = round(upkeep, 1)

        # Apply income and upkeep
        faction.treasury += income
        faction.treasury -= upkeep

        # Log events
        if income > 0:
            turn_log.add("income", faction.id, "income",
                        f"Collected {income}g from controlled cities")

        if upkeep > 0:
            turn_log.add("income", faction.id, "upkeep",
                        f"Paid {upkeep}g in upkeep (units, ships, salaries)")

        # Warn if treasury goes negative
        if faction.treasury < 0:
            turn_log.add("income", faction.id, "debt",
                        f"WARNING: Treasury is negative ({faction.treasury}g)! Units may desert.",
                        success=False)


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

    Args:
        game_state: Current game state (will be modified in-place)
        orders_by_player: Dict mapping player_id -> list of orders
        seed: RNG seed for deterministic execution

    Returns:
        Tuple of (updated_game_state, turn_log)
    """
    rng = random.Random(seed)
    turn_log = TurnLog()

    # Phase 1: Validation
    validate_orders(orders_by_player, game_state, turn_log)

    # Phase 2: Movement
    process_movement(orders_by_player, game_state, turn_log, rng)

    # Phase 2b: Sailing
    process_sail(orders_by_player, game_state, turn_log, rng)

    # Phase 3: Recruit & Buy
    process_recruit_and_buy(orders_by_player, game_state, turn_log, rng)

    # Phase 4: Magic
    process_magic(orders_by_player, game_state, turn_log, rng)

    # Phase 5: Combat
    process_combat(orders_by_player, game_state, turn_log, rng)

    # Phase 6: Income & Upkeep
    process_income_and_upkeep(game_state, turn_log)

    # Phase 7: Location Control & Diplomacy
    process_secure(orders_by_player, game_state, turn_log)
    process_diplomacy(orders_by_player, game_state, turn_log)

    # Phase 8: Cleanup
    cleanup_turn(game_state)

    return (game_state, turn_log)
