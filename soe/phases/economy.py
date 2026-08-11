"""Turn phase handlers — extracted from engine without behavior change."""

from __future__ import annotations

import random
from typing import Dict, List, Optional

from soe.models import (
    GameState, Ship, UnitType, ShipType,
    available_gold, debit_gold, credit_gold,
)
from soe.orders import (
    Order, TaxOrder, CollectOrder,
    BuildOrder, MineOrder, TradeOrder,
    InvestOrder,
)
from soe import config, items, territory
from soe.parser import get_player_leader
from soe.turn_log import TurnLog
from soe.phases.common import allocate_id


def _extract_resource(city, resource_type: str, requested: int) -> int:
    """Take renewable stock from a city, lazily initializing old maps."""
    capacity = max(1.0, city.resource_richness.get(resource_type, 1.0)
                   * config.RESOURCE_CAPACITY_PER_RICHNESS)
    remaining = city.resource_reserves.setdefault(resource_type, capacity)
    gathered = min(max(0, requested), int(remaining))
    city.resource_reserves[resource_type] = max(0.0, remaining - gathered)
    return gathered


def recover_resources(game_state: GameState) -> None:
    """Regenerate a fraction of every known resource stock each week."""
    for city in game_state.world_map.cities.values():
        for resource_type, remaining in list(city.resource_reserves.items()):
            capacity = max(1.0, city.resource_richness.get(resource_type, 1.0)
                           * config.RESOURCE_CAPACITY_PER_RICHNESS)
            city.resource_reserves[resource_type] = min(
                capacity, remaining + capacity * config.RESOURCE_WEEKLY_RECOVERY_RATE)


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

def process_invest_weekly(game_state: GameState, turn_log: TurnLog,
                          rng: Optional[random.Random] = None):
    """
    The weekly INVEST check (the design): for each town with invested gold,
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
        city.population_band = config.population_band_for(city.population)

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

        # Elite troop salary: soldiers times combat level per month (the design),
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

            # TAX collects where the character stands. When the order named a
            # city, that has to be this one -- otherwise the player asked to
            # tax one town and would silently have taxed another.
            if order.stated_city_id and order.stated_city_id != city.id:
                named = game_state.world_map.cities.get(order.stated_city_id)
                named_name = named.name if named else "that location"
                turn_log.add("tax", player_id, "tax_failed",
                            f"{actor.name}: TAX collects in the character's own "
                            f"location, and {actor.name} is in {city.name}, "
                            f"not {named_name}",
                            character_id=actor.id, success=False)
                continue

            authority_id = territory.administrative_faction_id(game_state, city.id)
            if authority_id != player_id:
                turn_log.add("tax", player_id, "tax_failed",
                            f"{actor.name}: cannot tax {city.name} — "
                            + territory.administration_denial(
                                game_state, city.id, player_id),
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
            resources_gathered = _extract_resource(
                city, resource_type,
                int(worker_count * order.duration_days * daily_rate * richness),
            )

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
                        owner_character_id=actor.id,
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
            resources_mined = _extract_resource(
                city, resource_type,
                int(worker_count * order.duration_days * daily_rate * richness),
            )

            # Add resources to character's inventory
            if resource_type not in actor.resources:
                actor.resources[resource_type] = 0
            actor.resources[resource_type] += resources_mined

            turn_log.add("mine", player_id, "mine_success",
                        f"{actor.name}: mined {resources_mined} {resource_type} at {city.name} "
                        f"({worker_count} workers, {order.duration_days} days)",
                        character_id=actor.id)

