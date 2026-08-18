"""The poster's texture tiles and the renderer's are the same tiles.

`webapp/static/public/` is deliberately self-contained -- the closed-alpha
poster promises static files and no build step -- so the four tiles the 3D
board loads exist twice on purpose. What is not on purpose is the two copies
drifting: regenerate one without the other and the poster quietly renders a
different ground than every map beside it. `scripts/build_textures.py` writes
both; this is what notices when someone bypasses it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MAP_TEXTURES = REPO_ROOT / "maps" / "textures"
WEB_TEXTURES = REPO_ROOT / "webapp" / "static" / "public" / "textures"
# The tiles the poster's renderer actually loads: the ground's grain, the
# sheet's tooth, and the water's. desert and hills went with the terrain
# mounds -- the ground is one grain tile coloured by elevation now, so a tile
# per terrain label was shipping bytes nothing would ever ask for.
SHARED = ("paper", "plain", "sea")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", SHARED)
def test_shared_texture_tiles_match(name):
    renderer = MAP_TEXTURES / f"{name}.jpg"
    poster = WEB_TEXTURES / f"{name}.jpg"
    assert renderer.is_file(), f"{renderer} is missing"
    assert poster.is_file(), f"{poster} is missing"
    assert _digest(renderer) == _digest(poster), (
        f"{name}.jpg differs between maps/textures and the poster's copy. "
        "Regenerate with scripts/build_textures.py, which writes both."
    )


def test_the_poster_ships_exactly_the_shared_tiles():
    """SHARED is the whole list, so the check above cannot miss a tile.

    A further tile dropped into the poster's directory without being added
    here would be unguarded: it could drift from the renderer's copy
    indefinitely and nothing would say so.
    """
    present = sorted(path.stem for path in WEB_TEXTURES.glob("*.jpg"))
    assert present == sorted(SHARED)
