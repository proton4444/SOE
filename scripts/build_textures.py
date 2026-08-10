"""
Turn generated terrain textures into seamless tiles for the map renderer.

The textures are the one part of the map that is not derived from the
gamemaster's data -- they carry no information, only surface. They are
generated as neutral greyscale and applied with a multiply blend, so the
map's palette and every position, label and route stay exactly as the
deterministic layers produced them. An image model can change how the
ground *looks*; it can never move a coastline or rename a town.

Tiles are made seamless by four-way mirroring, which is exact rather than
approximate, and each is normalised to sit near white so the multiply
darkens only where the texture has detail.

Usage:
    python scripts/build_textures.py --manifest docs/texture_sources.json
"""

from __future__ import annotations

import argparse
import io
import json
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO_ROOT / "maps" / "textures"

# Mean brightness each tile is normalised to, and how much contrast it
# keeps. Ground textures carry more tooth than the paper and sea washes.
TUNING = {
    "paper": (238, 10),
    "sea": (242, 7),
    "plain": (232, 13),
    "forest": (222, 20),
    "swamp": (228, 16),
    "desert": (234, 12),
    "hills": (226, 18),
    "mountains": (214, 26),
}


def seamless(img: Image.Image, size: int) -> Image.Image:
    """Four-way mirror: the tile matches itself on every edge, exactly."""
    quad = img.resize((size // 2, size // 2), Image.LANCZOS)
    a = np.asarray(quad, dtype=np.uint8)
    top = np.concatenate([a, np.fliplr(a)], axis=1)
    return Image.fromarray(np.concatenate([top, np.flipud(top)], axis=0))


def normalise(img: Image.Image, mean: float, spread: float) -> Image.Image:
    a = np.asarray(img, dtype=np.float32)
    centred = a - a.mean()
    scale = spread / max(centred.std(), 1e-6)
    return Image.fromarray(np.clip(centred * scale + mean, 0, 255).astype(np.uint8))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--quality", type=int, default=82)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)

    for name, source in manifest["textures"].items():
        raw = urllib.request.urlopen(source["url"], timeout=120).read()
        img = Image.open(io.BytesIO(raw)).convert("L")
        original = img.size
        mean, spread = TUNING.get(name, (230, 14))
        tile = normalise(seamless(img, args.size), mean, spread)
        path = args.out / f"{name}.jpg"
        tile.save(path, "JPEG", quality=args.quality, optimize=True)
        print(
            f"  {name:<10} {original[0]}x{original[1]} -> {tile.size[0]}x"
            f"{tile.size[1]}  {path.stat().st_size / 1024:5.0f} KB"
        )

    print(f"wrote {len(manifest['textures'])} tiles to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
