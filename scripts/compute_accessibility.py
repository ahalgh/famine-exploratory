"""Travel-time accessibility per livelihood zone from the MAP 2019 friction surfaces.

Targets
    market   WFP markets (HDX) with coordinates and at least one price since 2019
    city     GeoNames populated places with population >= 50,000 (data/external/geonames/<CC>.txt)

Travel is within each country only (cross-border markets are not modelled); see famine/access.py
for the cost-surface details.

Outputs
    data/derived/access/<country>_tt_{market,city}_{motorized,walking}.tif   (minutes, git-ignored)
    reports/zone_access_2019.csv   one row per livelihood zone: area-weighted median / p90 travel
        time (hours) to the nearest market and nearest 50k+ city, motorized and walking;
        number of WFP markets inside the zone

Run: python scripts/compute_accessibility.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio.features import rasterize

import famine as fm
from famine.access import MODES, CostGrid

OUT_DIR = fm.DATA_DIR / "derived/access"
ISO2 = {"Guatemala": "GT", "Kenya": "KE", "Malawi": "MW", "Nigeria": "NG", "Somalia": "SO", "Uganda": "UG"}
CITY_MIN_POP = 50_000
GEONAMES_COLS = ["geonameid", "name", "asciiname", "alternatenames", "lat", "lon", "fclass", "fcode", "cc", "cc2",
                 "admin1", "admin2", "admin3", "admin4", "population", "elevation", "dem", "timezone", "modified"]


def load_cities(country):
    g = pd.read_csv(fm.DATA_DIR / "external/geonames" / f"{ISO2[country]}.txt", sep="\t", names=GEONAMES_COLS,
                    keep_default_na=False, quoting=3, usecols=["name", "lat", "lon", "fclass", "population"])
    return g[(g["fclass"] == "P") & (g["population"] >= CITY_MIN_POP)]


def main():
    countries = fm.load_regions(layer="country").set_index("country")
    zones_all = fm.load_livelihood_zones()
    markets_all = fm.load_wfp_markets()

    rows = []
    for country in fm.COUNTRIES:
        geom = countries.loc[country, "geometry"]
        mk = markets_all[markets_all["country"] == country]
        cities = load_cities(country)
        zones = zones_all[zones_all["country"] == country].reset_index(drop=True)
        print(f"{country}: {len(zones)} zones, {len(mk)} WFP markets, {len(cities)} cities >= {CITY_MIN_POP:,}")

        surfaces = {}
        for mode in MODES:
            grid = CostGrid(geom, mode)
            for name, pts in [("market", zip(mk["longitude"], mk["latitude"])), ("city", zip(cities["lon"], cities["lat"]))]:
                tt = grid.travel_time([grid.pixel(x, y) for x, y in pts])
                grid.save(tt, OUT_DIR / f"{country.lower()}_tt_{name}_{mode}.tif")
                surfaces[(name, mode)] = tt
        zone_id = rasterize(((g, i + 1) for i, g in enumerate(zones.geometry)), out_shape=grid.shape,
                            transform=grid.transform, fill=0, dtype="int32")
        areas = zones.to_crs(6933).area / 1e6
        mk_pts = gpd.GeoDataFrame(mk, geometry=gpd.points_from_xy(mk["longitude"], mk["latitude"]), crs=4326)
        n_inside = gpd.sjoin(mk_pts, zones[["geometry"]], predicate="within").groupby("index_right").size()

        for i, z in zones.iterrows():
            sel = zone_id == i + 1
            rec = dict(country=country, zone=z["zone"], zone_key=z["zone_key"], fnid=z["fnid"], lzcode=z["lzcode"],
                       map_version=z["map_version"], eff_year=z["eff_year"], area_km2=round(areas[i]),
                       pixels=int(sel.sum()), wfp_markets_in_zone=int(n_inside.get(i, 0)))
            for (name, mode), arr in surfaces.items():
                v = arr[sel]
                v = v[np.isfinite(v)]
                rec[f"{name}_{mode}_median_h"] = round(float(np.median(v)) / 60, 2) if v.size else np.nan
                rec[f"{name}_{mode}_p90_h"] = round(float(np.percentile(v, 90)) / 60, 2) if v.size else np.nan
            rows.append(rec)

    out = pd.DataFrame(rows)
    path = ROOT / "reports" / "zone_access_2019.csv"
    out.to_csv(path, index=False)
    print(f"\nwrote {path} ({len(out)} zones)")


if __name__ == "__main__":
    main()
