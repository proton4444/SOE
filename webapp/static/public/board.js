// Atlas relief board, generated from maps/calib_12.json by
// scripts/build_public_board.py. Do not hand-edit.
//
// Twelve cities at their exact x/y with their populations, grid references,
// terrain, port and magic-free flags and regions; the roads with quality,
// mileage and movement cost; and the landmass hull that webapp/mapview.py
// draws for this map, mapped from its SVG frame into the same 0..1 fractions
// the cities use. The hull is a road-connectivity confine, not a surveyed
// coast -- calib_12.json has no geography file. See Amendment 2 in
// docs/MARKETING_CLOSED_ALPHA.md.
const ATLAS_BOARD = {
  "map": "calib_12.json",
  "field_miles": [
    1300.0,
    1000.0
  ],
  "landmasses": [
    {
      "index": 1,
      "name": "Barathfell vale",
      "kind": "continent",
      "city_ids": [
        "barunburn",
        "drelerford",
        "dreliwick",
        "dunaen",
        "ephunyn",
        "garmere",
        "garoath",
        "joreththorpe",
        "narunon",
        "rhaethdale",
        "zelahold",
        "zelothvale"
      ],
      "hull": [
        [
          0.13975,
          0.500067
        ],
        [
          0.345077,
          0.330857
        ],
        [
          0.783811,
          0.228183
        ],
        [
          0.863593,
          0.41286
        ],
        [
          0.852457,
          0.617344
        ],
        [
          0.685246,
          0.882125
        ],
        [
          0.171775,
          0.765744
        ]
      ]
    }
  ],
  "regions": [
    {
      "name": "Barathfell vale",
      "x": 0.7674,
      "y": 0.4611,
      "cities": 4
    },
    {
      "name": "Eshormere march",
      "x": 0.5876,
      "y": 0.7087,
      "cities": 4
    },
    {
      "name": "Lunistead reach",
      "x": 0.3162,
      "y": 0.5151,
      "cities": 4
    }
  ],
  "cities": [
    {
      "id": "zelothvale",
      "name": "Zelothvale",
      "x": 0.4665,
      "y": 0.7424,
      "x_miles": 606.4,
      "y_miles": 742.4,
      "terrain": [
        "plain"
      ],
      "population": 352,
      "population_band": "< 1k",
      "grid_ref": "H7",
      "region": "Eshormere march",
      "is_ruin": false,
      "is_port": false,
      "is_magic_free": false
    },
    {
      "id": "garmere",
      "name": "Garmere",
      "x": 0.6501,
      "y": 0.7956,
      "x_miles": 845.1,
      "y_miles": 795.6,
      "terrain": [
        "desert"
      ],
      "population": 0,
      "population_band": "< 1k",
      "grid_ref": "H9",
      "region": "Eshormere march",
      "is_ruin": true,
      "is_port": false,
      "is_magic_free": false
    },
    {
      "id": "drelerford",
      "name": "Drelerford",
      "x": 0.2292,
      "y": 0.7301,
      "x_miles": 298.0,
      "y_miles": 730.1,
      "terrain": [
        "hills"
      ],
      "population": 782,
      "population_band": "< 1k",
      "grid_ref": "H3",
      "region": "Lunistead reach",
      "is_ruin": false,
      "is_port": true,
      "is_magic_free": false
    },
    {
      "id": "rhaethdale",
      "name": "Rhaethdale",
      "x": 0.2007,
      "y": 0.5053,
      "x_miles": 260.9,
      "y_miles": 505.3,
      "terrain": [
        "plain"
      ],
      "population": 681,
      "population_band": "< 1k",
      "grid_ref": "F3",
      "region": "Lunistead reach",
      "is_ruin": false,
      "is_port": false,
      "is_magic_free": false
    },
    {
      "id": "dreliwick",
      "name": "Dreliwick",
      "x": 0.3976,
      "y": 0.3847,
      "x_miles": 516.9,
      "y_miles": 384.7,
      "terrain": [
        "plain"
      ],
      "population": 559,
      "population_band": "< 1k",
      "grid_ref": "D6",
      "region": "Lunistead reach",
      "is_ruin": false,
      "is_port": false,
      "is_magic_free": false
    },
    {
      "id": "zelahold",
      "name": "Zelahold",
      "x": 0.566,
      "y": 0.613,
      "x_miles": 735.8,
      "y_miles": 613.0,
      "terrain": [
        "plain"
      ],
      "population": 0,
      "population_band": "< 1k",
      "grid_ref": "G8",
      "region": "Eshormere march",
      "is_ruin": true,
      "is_port": false,
      "is_magic_free": false
    },
    {
      "id": "garoath",
      "name": "Garoath",
      "x": 0.6677,
      "y": 0.684,
      "x_miles": 868.0,
      "y_miles": 684.0,
      "terrain": [
        "plain"
      ],
      "population": 796,
      "population_band": "< 1k",
      "grid_ref": "G9",
      "region": "Eshormere march",
      "is_ruin": false,
      "is_port": false,
      "is_magic_free": true
    },
    {
      "id": "dunaen",
      "name": "Dunaen",
      "x": 0.7922,
      "y": 0.6012,
      "x_miles": 1029.8,
      "y_miles": 601.2,
      "terrain": [
        "hills"
      ],
      "population": 182,
      "population_band": "< 1k",
      "grid_ref": "G11",
      "region": "Barathfell vale",
      "is_ruin": false,
      "is_port": true,
      "is_magic_free": false
    },
    {
      "id": "narunon",
      "name": "Narunon",
      "x": 0.4373,
      "y": 0.4405,
      "x_miles": 568.5,
      "y_miles": 440.5,
      "terrain": [
        "plain"
      ],
      "population": 837,
      "population_band": "< 1k",
      "grid_ref": "E6",
      "region": "Lunistead reach",
      "is_ruin": false,
      "is_port": false,
      "is_magic_free": false
    },
    {
      "id": "ephunyn",
      "name": "Ephunyn",
      "x": 0.7388,
      "y": 0.5165,
      "x_miles": 960.4,
      "y_miles": 516.5,
      "terrain": [
        "plain"
      ],
      "population": 397,
      "population_band": "< 1k",
      "grid_ref": "F10",
      "region": "Barathfell vale",
      "is_ruin": false,
      "is_port": false,
      "is_magic_free": false
    },
    {
      "id": "joreththorpe",
      "name": "Joreththorpe",
      "x": 0.804,
      "y": 0.4356,
      "x_miles": 1045.2,
      "y_miles": 435.6,
      "terrain": [
        "plain"
      ],
      "population": 398,
      "population_band": "< 1k",
      "grid_ref": "E11",
      "region": "Barathfell vale",
      "is_ruin": false,
      "is_port": false,
      "is_magic_free": false
    },
    {
      "id": "barunburn",
      "name": "Barunburn",
      "x": 0.7347,
      "y": 0.291,
      "x_miles": 955.1,
      "y_miles": 291.0,
      "terrain": [
        "plain"
      ],
      "population": 601,
      "population_band": "< 1k",
      "grid_ref": "C10",
      "region": "Barathfell vale",
      "is_ruin": false,
      "is_port": false,
      "is_magic_free": true
    }
  ],
  "roads": [
    {
      "from": "zelothvale",
      "to": "zelahold",
      "quality": "fair",
      "distance_miles": 210,
      "move_cost": 31.5
    },
    {
      "from": "garmere",
      "to": "garoath",
      "quality": "poor",
      "distance_miles": 131,
      "move_cost": 26.2
    },
    {
      "from": "rhaethdale",
      "to": "drelerford",
      "quality": "good",
      "distance_miles": 262,
      "move_cost": 26.2
    },
    {
      "from": "dreliwick",
      "to": "rhaethdale",
      "quality": "fair",
      "distance_miles": 325,
      "move_cost": 48.8
    },
    {
      "from": "dreliwick",
      "to": "narunon",
      "quality": "good",
      "distance_miles": 87,
      "move_cost": 8.7
    },
    {
      "from": "zelahold",
      "to": "garoath",
      "quality": "good",
      "distance_miles": 173,
      "move_cost": 17.3
    },
    {
      "from": "narunon",
      "to": "zelothvale",
      "quality": "fair",
      "distance_miles": 350,
      "move_cost": 52.5
    },
    {
      "from": "narunon",
      "to": "zelahold",
      "quality": "fair",
      "distance_miles": 276,
      "move_cost": 41.4
    },
    {
      "from": "ephunyn",
      "to": "garoath",
      "quality": "good",
      "distance_miles": 220,
      "move_cost": 22.0
    },
    {
      "from": "ephunyn",
      "to": "dunaen",
      "quality": "good",
      "distance_miles": 126,
      "move_cost": 12.6
    },
    {
      "from": "ephunyn",
      "to": "joreththorpe",
      "quality": "good",
      "distance_miles": 135,
      "move_cost": 13.5
    },
    {
      "from": "barunburn",
      "to": "dunaen",
      "quality": "good",
      "distance_miles": 367,
      "move_cost": 36.7
    },
    {
      "from": "barunburn",
      "to": "ephunyn",
      "quality": "fair",
      "distance_miles": 259,
      "move_cost": 38.8
    },
    {
      "from": "barunburn",
      "to": "joreththorpe",
      "quality": "good",
      "distance_miles": 196,
      "move_cost": 19.6
    }
  ]
};
