// Atlas relief board topology, generated from maps/calib_12.json.
// Coordinate topology only: twelve cities at their exact x/y, the roads as
// listed, and one terrain label per city. No coastline, no landmass, no
// elevation. Regenerate with scripts/build_public_board.py.
const ATLAS_BOARD = {
  "map": "calib_12.json",
  "cities": [
    {
      "id": "zelothvale",
      "name": "Zelothvale",
      "x": 0.4665,
      "y": 0.7424,
      "terrain": "plain",
      "is_ruin": false
    },
    {
      "id": "garmere",
      "name": "Garmere",
      "x": 0.6501,
      "y": 0.7956,
      "terrain": "desert",
      "is_ruin": true
    },
    {
      "id": "drelerford",
      "name": "Drelerford",
      "x": 0.2292,
      "y": 0.7301,
      "terrain": "hills",
      "is_ruin": false
    },
    {
      "id": "rhaethdale",
      "name": "Rhaethdale",
      "x": 0.2007,
      "y": 0.5053,
      "terrain": "plain",
      "is_ruin": false
    },
    {
      "id": "dreliwick",
      "name": "Dreliwick",
      "x": 0.3976,
      "y": 0.3847,
      "terrain": "plain",
      "is_ruin": false
    },
    {
      "id": "zelahold",
      "name": "Zelahold",
      "x": 0.566,
      "y": 0.613,
      "terrain": "plain",
      "is_ruin": true
    },
    {
      "id": "garoath",
      "name": "Garoath",
      "x": 0.6677,
      "y": 0.684,
      "terrain": "plain",
      "is_ruin": false
    },
    {
      "id": "dunaen",
      "name": "Dunaen",
      "x": 0.7922,
      "y": 0.6012,
      "terrain": "hills",
      "is_ruin": false
    },
    {
      "id": "narunon",
      "name": "Narunon",
      "x": 0.4373,
      "y": 0.4405,
      "terrain": "plain",
      "is_ruin": false
    },
    {
      "id": "ephunyn",
      "name": "Ephunyn",
      "x": 0.7388,
      "y": 0.5165,
      "terrain": "plain",
      "is_ruin": false
    },
    {
      "id": "joreththorpe",
      "name": "Joreththorpe",
      "x": 0.804,
      "y": 0.4356,
      "terrain": "plain",
      "is_ruin": false
    },
    {
      "id": "barunburn",
      "name": "Barunburn",
      "x": 0.7347,
      "y": 0.291,
      "terrain": "plain",
      "is_ruin": false
    }
  ],
  "roads": [
    {
      "from": "zelothvale",
      "to": "zelahold",
      "quality": "fair"
    },
    {
      "from": "garmere",
      "to": "garoath",
      "quality": "poor"
    },
    {
      "from": "rhaethdale",
      "to": "drelerford",
      "quality": "good"
    },
    {
      "from": "dreliwick",
      "to": "rhaethdale",
      "quality": "fair"
    },
    {
      "from": "dreliwick",
      "to": "narunon",
      "quality": "good"
    },
    {
      "from": "zelahold",
      "to": "garoath",
      "quality": "good"
    },
    {
      "from": "narunon",
      "to": "zelothvale",
      "quality": "fair"
    },
    {
      "from": "narunon",
      "to": "zelahold",
      "quality": "fair"
    },
    {
      "from": "ephunyn",
      "to": "garoath",
      "quality": "good"
    },
    {
      "from": "ephunyn",
      "to": "dunaen",
      "quality": "good"
    },
    {
      "from": "ephunyn",
      "to": "joreththorpe",
      "quality": "good"
    },
    {
      "from": "barunburn",
      "to": "dunaen",
      "quality": "good"
    },
    {
      "from": "barunburn",
      "to": "ephunyn",
      "quality": "fair"
    },
    {
      "from": "barunburn",
      "to": "joreththorpe",
      "quality": "good"
    }
  ]
};
