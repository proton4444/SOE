"""Pathfinding helpers for land and sea movement."""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import List, Tuple, Optional

from spoils_engine.models import GameState, RoadQuality
from spoils_engine import config


@dataclass
class Route:
    """
    A journey over the map: the cities passed, its cost, and the roads used.

    Carrying the road ids means mileage is summed from the routes actually
    travelled, rather than guessed at afterwards from the pairs of city names.
    """
    city_ids: List[str]
    cost: float
    road_ids: List[str]

    def __bool__(self) -> bool:
        return bool(self.city_ids) and self.cost != float("inf")

    def miles(self, game_state: GameState) -> Optional[float]:
        """Total length in map miles, or None if any leg has no mileage."""
        total = 0.0
        for road_id in self.road_ids:
            road = game_state.world_map.roads.get(road_id)
            if road is None or not road.distance_miles:
                return None
            total += road.distance_miles
        return total


def find_route(start_city_id: str, end_city_id: str, game_state: GameState, *,
               allow_land: bool = True, allow_sea: bool = False) -> Route:
    """
    Cheapest route between two cities over the chosen networks.

    Marching and sailing each use one network -- rules.md keeps them disjoint,
    so an army cannot ford a sea lane and a galley cannot sail up a road. Magic
    is the exception: an orb looking at a distant place does not care which,
    so it asks for both.
    """
    return _dijkstra(start_city_id, end_city_id, game_state,
                     allow_land=allow_land, allow_sea=allow_sea)


def _dijkstra(start_city_id: str, end_city_id: str, game_state: GameState,
              *, allow_land: bool, allow_sea: bool) -> Route:
    """
    Shortest path between two cities over the road graph.

    Args:
        allow_land: Traverse land roads.
        allow_sea: Traverse sea lanes.

    Returns:
        A Route; falsy when no journey exists.
    """
    if start_city_id == end_city_id:
        return Route([start_city_id], 0.0, [])

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
            # Reconstruct path, remembering which road carried each leg.
            path = []
            roads = []
            node = end_city_id
            while node in previous:
                prior, road_id = previous[node]
                path.append(node)
                roads.append(road_id)
                node = prior
            path.append(start_city_id)
            path.reverse()
            roads.reverse()
            return Route(path, current_dist, roads)

        for neighbor_city, road in game_state.world_map.neighbors(current_id):
            is_sea_lane = road.quality == RoadQuality.SEA
            if is_sea_lane and not allow_sea:
                continue
            if not is_sea_lane and not allow_land:
                continue

            if neighbor_city.id in visited:
                continue

            cost = config.get_hop_cost(road)
            new_dist = current_dist + cost

            if neighbor_city.id not in distances or new_dist < distances[neighbor_city.id]:
                distances[neighbor_city.id] = new_dist
                previous[neighbor_city.id] = (current_id, road.id)
                heapq.heappush(pq, (new_dist, neighbor_city.id))

    # No path found
    return Route([], float('inf'), [])


def find_shortest_path(start_city_id: str, end_city_id: str, game_state: GameState) -> Tuple[List[str], float]:
    """Find the shortest overland route between two cities."""
    route = _dijkstra(start_city_id, end_city_id, game_state,
                      allow_land=True, allow_sea=False)
    return (route.city_ids, route.cost)


def find_sea_route(start_city_id: str, end_city_id: str, game_state: GameState) -> Tuple[List[str], float]:
    """Find the shortest route between two cities using only sea lanes."""
    route = _dijkstra(start_city_id, end_city_id, game_state,
                      allow_land=False, allow_sea=True)
    return (route.city_ids, route.cost)


def route_miles(path_city_ids: List[str], game_state: GameState,
                *, sea_only: bool = False) -> Optional[float]:
    """
    Total length of a path in map miles.

    Sums `distance_miles` over every hop of the path. Returns None if any hop
    lacks a mileage (hand-built maps), so callers can fall back.

    Args:
        sea_only: Which network the path was found on. Two cities may be joined
            by both a road and a sea lane, and the two are priced differently --
            without this the shorter-to-find road would be billed for a voyage.
            Defaults to land, matching `find_shortest_path`.
    """
    if not path_city_ids or len(path_city_ids) < 2:
        return 0.0
    total = 0.0
    for start_id, end_id in zip(path_city_ids, path_city_ids[1:]):
        road = _road_for_hop(start_id, end_id, game_state, sea_only)
        if road is None or not road.distance_miles:
            return None
        total += road.distance_miles
    return total


def _road_for_hop(start_id: str, end_id: str, game_state: GameState,
                  sea_only: bool) -> Optional[object]:
    """
    The route actually traversable from start to end on the given network.

    Honours direction: a one-way road pointing the other way is not this hop.
    Where several routes qualify, the cheapest wins -- the same one Dijkstra
    would have taken.
    """
    best = None
    best_cost = float("inf")
    for road in game_state.world_map.roads.values():
        if (road.quality == RoadQuality.SEA) != sea_only:
            continue
        forward = road.from_city_id == start_id and road.to_city_id == end_id
        backward = (road.bidirectional
                    and road.to_city_id == start_id
                    and road.from_city_id == end_id)
        if not (forward or backward):
            continue
        cost = config.get_hop_cost(road)
        if cost < best_cost:
            best, best_cost = road, cost
    return best

