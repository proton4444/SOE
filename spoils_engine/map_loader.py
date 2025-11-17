"""
Map loading utilities for reading map data from JSON files.

Maps define the world geography: cities, roads, and sea lanes.
"""

import json
from pathlib import Path
from typing import Optional

from spoils_engine.models import WorldMap, City, Road, PopulationBand, RoadQuality


def load_map_from_json(map_file: Path) -> WorldMap:
    """
    Load a WorldMap from a JSON file.

    Expected JSON format:
    {
      "cities": [
        {
          "id": "madegi_doy",
          "name": "Madegi Doy",
          "population_band": "100k-999k",
          "terrain": ["coastal", "plains"],
          "region": "Main Continent",
          "is_port": true
        },
        ...
      ],
      "roads": [
        {
          "id": "road_1",
          "from": "madegi_doy",
          "to": "kitesta",
          "quality": "good",
          "bidirectional": true
        },
        ...
      ]
    }

    Args:
        map_file: Path to JSON map file

    Returns:
        WorldMap instance
    """
    with open(map_file, 'r') as f:
        data = json.load(f)

    world_map = WorldMap()

    # Load cities
    for city_data in data.get('cities', []):
        city = City(
            id=city_data['id'],
            name=city_data['name'],
            population_band=PopulationBand(city_data['population_band']),
            terrain=set(city_data.get('terrain', [])),
            region=city_data.get('region'),
            is_port=city_data.get('is_port', False)
        )
        world_map.cities[city.id] = city

    # Load roads
    for road_data in data.get('roads', []):
        road = Road(
            id=road_data['id'],
            from_city_id=road_data['from'],
            to_city_id=road_data['to'],
            quality=RoadQuality(road_data['quality']),
            bidirectional=road_data.get('bidirectional', True)
        )
        world_map.roads[road.id] = road

    return world_map


def create_sample_map() -> WorldMap:
    """
    Create a small sample map for testing and demos.

    This map has 5 cities connected by roads and sea lanes,
    suitable for 2-3 player games.
    """
    world_map = WorldMap()

    # Create cities
    cities_data = [
        {
            "id": "madegi_doy",
            "name": "Madegi Doy",
            "population_band": PopulationBand.LARGE,
            "terrain": {"coastal", "plains"},
            "region": "Main Continent",
            "is_port": True
        },
        {
            "id": "kitesta",
            "name": "Kitesta",
            "population_band": PopulationBand.MEDIUM,
            "terrain": {"plains", "river"},
            "region": "Main Continent",
            "is_port": False
        },
        {
            "id": "riverton",
            "name": "Riverton",
            "population_band": PopulationBand.SMALL,
            "terrain": {"forest", "river"},
            "region": "Main Continent",
            "is_port": False
        },
        {
            "id": "albatross_city",
            "name": "Albatross City",
            "population_band": PopulationBand.MEDIUM,
            "terrain": {"coastal", "mountains"},
            "region": "Northern Island",
            "is_port": True
        },
        {
            "id": "peshandi",
            "name": "Peshandi",
            "population_band": PopulationBand.TINY,
            "terrain": {"desert"},
            "region": "Main Continent",
            "is_port": False
        }
    ]

    for city_data in cities_data:
        city = City(**city_data)
        world_map.cities[city.id] = city

    # Create roads
    roads_data = [
        {
            "id": "road_1",
            "from_city_id": "madegi_doy",
            "to_city_id": "kitesta",
            "quality": RoadQuality.GOOD,
            "bidirectional": True
        },
        {
            "id": "road_2",
            "from_city_id": "kitesta",
            "to_city_id": "riverton",
            "quality": RoadQuality.FAIR,
            "bidirectional": True
        },
        {
            "id": "road_3",
            "from_city_id": "riverton",
            "to_city_id": "peshandi",
            "quality": RoadQuality.POOR,
            "bidirectional": True
        },
        {
            "id": "road_4",
            "from_city_id": "peshandi",
            "to_city_id": "madegi_doy",
            "quality": RoadQuality.FAIR,
            "bidirectional": True
        },
        {
            "id": "sea_1",
            "from_city_id": "madegi_doy",
            "to_city_id": "albatross_city",
            "quality": RoadQuality.SEA,
            "bidirectional": True
        }
    ]

    for road_data in roads_data:
        road = Road(**road_data)
        world_map.roads[road.id] = road

    return world_map


def save_map_to_json(world_map: WorldMap, map_file: Path) -> None:
    """
    Save a WorldMap to a JSON file.

    Args:
        world_map: The map to save
        map_file: Path to output JSON file
    """
    data = {
        "cities": [],
        "roads": []
    }

    # Serialize cities
    for city in world_map.cities.values():
        data["cities"].append({
            "id": city.id,
            "name": city.name,
            "population_band": city.population_band.value,
            "terrain": list(city.terrain),
            "region": city.region,
            "is_port": city.is_port
        })

    # Serialize roads
    for road in world_map.roads.values():
        data["roads"].append({
            "id": road.id,
            "from": road.from_city_id,
            "to": road.to_city_id,
            "quality": road.quality.value,
            "bidirectional": road.bidirectional
        })

    with open(map_file, 'w') as f:
        json.dump(data, f, indent=2)
