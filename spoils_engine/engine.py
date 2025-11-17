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
    Order, MoveOrder, RecruitOrder, BuyShipOrder, AttackOrder, TeleportOrder
)
from spoils_engine import config


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
    """Process magic orders (simplified teleport)."""
    for player_id, orders in orders_by_player.items():
        for order in orders:
            if not isinstance(order, TeleportOrder):
                continue

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


# ============================================================================
# PHASE 5: COMBAT
# ============================================================================

def process_combat(orders_by_player: Dict[str, List[Order]], game_state: GameState,
                   turn_log: TurnLog, rng: random.Random):
    """Process combat orders."""
    # Group attacks by location
    attacks_by_location = defaultdict(list)

    for player_id, orders in orders_by_player.items():
        for order in orders:
            if isinstance(order, AttackOrder) and not order.warnings:
                attacks_by_location[order.location_city_id].append((player_id, order))

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

            # Calculate attacker power
            attacker_power = calculate_faction_power(attacker_player_id, city_id, game_state)

            # Calculate defender power
            defender_power = calculate_faction_power(defender_faction_id, city_id, game_state)

            if defender_power == 0:
                turn_log.add("combat", attacker_player_id, "attack_failed",
                            f"{attacker.name} found no defenders in {city.name}",
                            location=city_id, character_id=attacker.id, success=False)
                continue

            # Check if attacker wants to engage
            if attacker_power < defender_power * config.COMBAT_MINIMUM_ATTACK_RATIO:
                turn_log.add("combat", attacker_player_id, "attack_declined",
                            f"{attacker.name} declined to attack (odds too poor)",
                            location=city_id, character_id=attacker.id, success=False)
                continue

            # Resolve combat (simplified)
            # Add randomness
            attacker_roll = attacker_power * (0.8 + rng.random() * 0.4)  # 0.8x to 1.2x
            defender_roll = defender_power * (0.8 + rng.random() * 0.4)

            if attacker_roll > defender_roll:
                # Attacker wins
                winner_id = attacker_player_id
                loser_id = defender_faction_id
                apply_casualties(loser_id, city_id, config.COMBAT_CASUALTY_RATE_LOSER, game_state, rng)
                apply_casualties(winner_id, city_id, config.COMBAT_CASUALTY_RATE_WINNER, game_state, rng)

                turn_log.add("combat", attacker_player_id, "victory",
                            f"{attacker.name} defeated {attack_order.target_name} in {city.name}",
                            location=city_id, character_id=attacker.id)
                turn_log.add("combat", defender_faction_id, "defeat",
                            f"Your forces were defeated by {attacker.name} in {city.name}",
                            location=city_id)
            else:
                # Defender wins
                winner_id = defender_faction_id
                loser_id = attacker_player_id
                apply_casualties(loser_id, city_id, config.COMBAT_CASUALTY_RATE_LOSER, game_state, rng)
                apply_casualties(winner_id, city_id, config.COMBAT_CASUALTY_RATE_WINNER, game_state, rng)

                turn_log.add("combat", attacker_player_id, "defeat",
                            f"{attacker.name} was defeated in {city.name}",
                            location=city_id, character_id=attacker.id)
                turn_log.add("combat", defender_faction_id, "victory",
                            f"Your forces successfully defended {city.name}",
                            location=city_id)


def calculate_faction_power(faction_id: str, city_id: str, game_state: GameState) -> float:
    """Calculate total combat power of a faction at a location."""
    power = 0.0

    # Add character combat skills
    best_combat_skill = 0
    for char in game_state.characters.values():
        if char.faction_id == faction_id and char.location_city_id == city_id:
            best_combat_skill = max(best_combat_skill, char.combat_skill)

    # Add unit attack values
    for stack in game_state.unit_stacks.values():
        if stack.faction_id == faction_id and stack.location_city_id == city_id:
            power += stack.attack_value

    # Add ship attack values
    for ship in game_state.ships.values():
        if ship.faction_id == faction_id and ship.location_city_id == city_id:
            power += ship.attack_value

    # Apply skill multiplier
    skill_multiplier = 1.0 + (best_combat_skill * config.COMBAT_SKILL_BONUS_PER_POINT)
    power *= skill_multiplier

    return power


def apply_casualties(faction_id: str, city_id: str, casualty_rate: float,
                     game_state: GameState, rng: random.Random):
    """Apply casualties to a faction's forces at a location."""
    # Apply to unit stacks
    for stack in list(game_state.unit_stacks.values()):
        if stack.faction_id == faction_id and stack.location_city_id == city_id:
            casualties = int(stack.count * casualty_rate)
            stack.count -= casualties
            if stack.count <= 0:
                del game_state.unit_stacks[stack.id]

    # Ships have chance to be destroyed
    for ship in list(game_state.ships.values()):
        if ship.faction_id == faction_id and ship.location_city_id == city_id:
            if rng.random() < casualty_rate:
                del game_state.ships[ship.id]


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

        # Add income
        faction.treasury += income

        if income > 0:
            turn_log.add("income", faction.id, "income",
                        f"Collected {income}g from controlled cities")

        # TODO: Deduct upkeep (simplified to 0 in alpha)


# ============================================================================
# PHASE 7: CLEANUP
# ============================================================================

def cleanup_turn(game_state: GameState):
    """Perform end-of-turn cleanup."""
    # Reset movement points
    for char in game_state.characters.values():
        char.movement_points = config.CHARACTER_MOVEMENT_POINTS_PER_TURN

    # Restore magic power
    for char in game_state.characters.values():
        char.magic_power_current = char.max_magic_power

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

    # Phase 3: Recruit & Buy
    process_recruit_and_buy(orders_by_player, game_state, turn_log, rng)

    # Phase 4: Magic
    process_magic(orders_by_player, game_state, turn_log, rng)

    # Phase 5: Combat
    process_combat(orders_by_player, game_state, turn_log, rng)

    # Phase 6: Income & Upkeep
    process_income_and_upkeep(game_state, turn_log)

    # Phase 7: Cleanup
    cleanup_turn(game_state)

    return (game_state, turn_log)
