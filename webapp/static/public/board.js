// Atlas relief board, generated from maps/starter_map.json by
// scripts/build_public_board.py. Do not hand-edit.
//
// Every city at its exact x/y with its population, grid reference, terrain,
// port and magic-free flags and region; the roads with quality, mileage and
// movement cost; and the landmass hulls that webapp/mapview.py draws for this
// map, mapped from its SVG frame into the same 0..1 fractions the cities use.
// A hull is a road-connectivity confine, not a surveyed coast -- these maps
// have no geography file. Sea lanes do not join land, so a city reachable only
// by sea comes out as its own island. See Amendment 2 in
// docs/MARKETING_CLOSED_ALPHA.md.
const ATLAS_BOARD = {
  "map": "starter_map.json",
  "field_miles": [
    1300.0,
    1000.0
  ],
  "frame_units": [
    1180.0,
    680.0
  ],
  "landmasses": [
    {
      "index": 1,
      "name": "Main Continent",
      "kind": "continent",
      "city_ids": [
        "ashford",
        "highfell",
        "oldbarrow",
        "redport",
        "sarnvale"
      ],
      "hull": [
        [
          0.06919,
          0.838627
        ],
        [
          0.241483,
          0.077879
        ],
        [
          0.758017,
          0.247208
        ],
        [
          0.605631,
          0.593494
        ]
      ]
    },
    {
      "index": 2,
      "name": "Northern Island",
      "kind": "island",
      "city_ids": [
        "gullhaven"
      ],
      "hull": [
        [
          0.941017,
          0.12
        ],
        [
          0.936372,
          0.151605
        ],
        [
          0.923145,
          0.178399
        ],
        [
          0.90335,
          0.196302
        ],
        [
          0.88,
          0.202588
        ],
        [
          0.85665,
          0.196302
        ],
        [
          0.836855,
          0.178399
        ],
        [
          0.823628,
          0.151605
        ],
        [
          0.818983,
          0.12
        ],
        [
          0.823628,
          0.088395
        ],
        [
          0.836855,
          0.061601
        ],
        [
          0.85665,
          0.043698
        ],
        [
          0.88,
          0.037412
        ],
        [
          0.90335,
          0.043698
        ],
        [
          0.923145,
          0.061601
        ],
        [
          0.936372,
          0.088395
        ]
      ]
    }
  ],
  "regions": [
    {
      "name": "Main Continent",
      "x": 0.426,
      "y": 0.45,
      "cities": 5
    },
    {
      "name": "Northern Island",
      "x": 0.88,
      "y": 0.12,
      "cities": 1
    }
  ],
  "cities": [
    {
      "id": "highfell",
      "name": "Highfell",
      "x": 0.12,
      "y": 0.78,
      "x_miles": 156.0,
      "y_miles": 780.0,
      "terrain": [
        "coastal",
        "plains"
      ],
      "population": 1200000,
      "population_band": "100k+",
      "grid_ref": "B8",
      "region": "Main Continent",
      "is_ruin": false,
      "is_port": true,
      "is_magic_free": false
    },
    {
      "id": "redport",
      "name": "Redport",
      "x": 0.48,
      "y": 0.48,
      "x_miles": 624.0,
      "y_miles": 480.0,
      "terrain": [
        "river",
        "plains"
      ],
      "population": 420000,
      "population_band": "100k+",
      "grid_ref": "F5",
      "region": "Main Continent",
      "is_ruin": false,
      "is_port": false,
      "is_magic_free": false
    },
    {
      "id": "ashford",
      "name": "Ashford",
      "x": 0.7,
      "y": 0.28,
      "x_miles": 910.0,
      "y_miles": 280.0,
      "terrain": [
        "forest",
        "river"
      ],
      "population": 45000,
      "population_band": "10k-99k",
      "grid_ref": "H3",
      "region": "Main Continent",
      "is_ruin": false,
      "is_port": false,
      "is_magic_free": false
    },
    {
      "id": "gullhaven",
      "name": "Gullhaven",
      "x": 0.88,
      "y": 0.12,
      "x_miles": 1144.0,
      "y_miles": 120.0,
      "terrain": [
        "coastal",
        "mountains"
      ],
      "population": 280000,
      "population_band": "100k+",
      "grid_ref": "K2",
      "region": "Northern Island",
      "is_ruin": false,
      "is_port": true,
      "is_magic_free": false
    },
    {
      "id": "sarnvale",
      "name": "Sarnvale",
      "x": 0.28,
      "y": 0.16,
      "x_miles": 364.0,
      "y_miles": 160.0,
      "terrain": [
        "desert"
      ],
      "population": 6800,
      "population_band": "1k-9k",
      "grid_ref": "D2",
      "region": "Main Continent",
      "is_ruin": false,
      "is_port": false,
      "is_magic_free": true
    },
    {
      "id": "oldbarrow",
      "name": "Oldbarrow",
      "x": 0.55,
      "y": 0.55,
      "x_miles": 715.0,
      "y_miles": 550.0,
      "terrain": [
        "mountains"
      ],
      "population": 0,
      "population_band": "< 1k",
      "grid_ref": "G6",
      "region": "Main Continent",
      "is_ruin": true,
      "is_port": false,
      "is_magic_free": false
    }
  ],
  "roads": [
    {
      "from": "highfell",
      "to": "redport",
      "quality": "excellent",
      "distance_miles": 94,
      "move_cost": 4.7
    },
    {
      "from": "redport",
      "to": "ashford",
      "quality": "fair",
      "distance_miles": 59,
      "move_cost": 8.9
    },
    {
      "from": "ashford",
      "to": "sarnvale",
      "quality": "poor",
      "distance_miles": 102,
      "move_cost": 20.4
    },
    {
      "from": "sarnvale",
      "to": "highfell",
      "quality": "fair",
      "distance_miles": 92,
      "move_cost": 13.8
    },
    {
      "from": "redport",
      "to": "oldbarrow",
      "quality": "poor",
      "distance_miles": 20,
      "move_cost": 4.0
    },
    {
      "from": "highfell",
      "to": "gullhaven",
      "quality": "sea",
      "distance_miles": 201,
      "move_cost": 20.1
    }
  ]
};
