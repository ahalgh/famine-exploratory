"""Travel-time (cost-distance) helpers on the MAP 2019 friction surfaces.

Friction rasters live in data/external/map_accessibility/friction_2019_{motorized,walking}_{africa,guatemala}.tif
(minutes per metre, 30 arc-seconds, EPSG:4326), downloaded from the MAP GeoServer
(layers Accessibility__202001_Global_{Motorized,Walking_Only}_Friction_Surface).

The MAP surface assigns oceans a travel speed (~19 km/h), so costs are restricted to a land polygon
(normally the country) to stop least-cost paths shortcutting by sea; inland lakes inside the polygon
are kept. Pixel size varies with latitude, so each row's cost is scaled by sqrt(dx * dy) in metres
(diagonal moves are slightly mis-weighted; error < 3% at these latitudes).
"""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds
from skimage.graph import MCP_Geometric

from .loaders import DATA_DIR

MAP_DIR = DATA_DIR / "external/map_accessibility"
MODES = ("motorized", "walking")


class CostGrid:
    """Cost surface (minutes to cross each pixel) for one land polygon and travel mode."""

    def __init__(self, land_geom, mode: str = "motorized", pad: float = 0.05):
        region = "guatemala" if land_geom.bounds[0] < -60 else "africa"
        with rasterio.open(MAP_DIR / f"friction_2019_{mode}_{region}.tif") as src:
            minx, miny, maxx, maxy = land_geom.buffer(pad).bounds
            win = from_bounds(minx, miny, maxx, maxy, src.transform).round_offsets().round_lengths()
            fr = src.read(1, window=win).astype("float64")
            self.transform = src.window_transform(win)
        land = ~geometry_mask([land_geom], fr.shape, self.transform, all_touched=True)
        rows = np.arange(fr.shape[0])
        lat = self.transform.f + (rows + 0.5) * self.transform.e
        dy = abs(self.transform.e) * 111_320.0
        dx = abs(self.transform.a) * 111_320.0 * np.cos(np.radians(lat))
        cost = fr * np.sqrt(dx * dy)[:, None]
        cost[~land | ~np.isfinite(cost) | (fr <= 0)] = np.inf
        self.cost, self.mode, self.shape = cost, mode, cost.shape

    def pixel(self, lon: float, lat: float):
        col, row = ~self.transform * (lon, lat)
        r, c = int(row), int(col)
        if 0 <= r < self.shape[0] and 0 <= c < self.shape[1] and np.isfinite(self.cost[r, c]):
            return r, c
        return None

    def travel_time(self, starts) -> np.ndarray:
        """Minutes from the nearest of `starts` (pixel tuples) to every pixel; NaN outside the land mask."""
        starts = [s for s in starts if s is not None]
        if not starts:
            return np.full(self.shape, np.nan)
        tt, _ = MCP_Geometric(self.cost, fully_connected=True).find_costs(starts)
        tt[~np.isfinite(self.cost)] = np.nan
        return tt

    def save(self, arr: np.ndarray, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1,
                           dtype="float32", crs="EPSG:4326", transform=self.transform, nodata=np.nan,
                           compress="deflate", predictor=3) as dst:
            dst.write(arr.astype("float32"), 1)


def load_zone_access():
    """Zone-level travel times written by scripts/compute_accessibility.py (reports/zone_access_2019.csv)."""
    import pandas as pd

    from pathlib import Path

    return pd.read_csv(Path(__file__).resolve().parents[1] / "reports" / "zone_access_2019.csv")


def attach_zone_access(df, region_col: str = "region"):
    """Left-join zone access onto FEWS/ML rows (needs `country` and a zone-name column)."""
    from .loaders import zone_key

    acc = load_zone_access().drop(columns=["zone"])
    out = df.copy()
    out["zone_key"] = [zone_key(str(c), r) for c, r in zip(out["country"], out[region_col])]
    return out.merge(acc, on=["country", "zone_key"], how="left")
