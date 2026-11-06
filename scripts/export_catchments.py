"""Price catchments: the area each market's price is generalised to when prices are borrowed by
nearest market.

Every 1 km cell (MAP 2019 motorized friction surface, within the country) is assigned to the market it
reaches fastest by road. Two sets, computed separately:
    wfp   WFP markets with prices since 2019
    fao   FAO GIEWS town series (FAO area series already name their area: county, group of states, nation)

Outputs (boundary-vis/public/data/)
    catchments_wfp.geojson, catchments_fao.geojson   one polygon per market: area, travel-time median/p90
    hfid_prices.json                                  per HFID unit: road hours to the nearest WFP / FAO market
                                                      (median over the unit) and the market whose catchment
                                                      covers most of it
Run after scripts/export_boundaries.py:  python scripts/export_catchments.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio.features import rasterize, shapes
from shapely.geometry import shape

import famine as fm
from famine.access import CostGrid

OUT = ROOT / "boundary-vis" / "public" / "data"


def allocate(grid, points):
    """Running minimum over per-market travel-time surfaces: (hours to nearest, index of nearest)."""
    best = np.full(grid.shape, np.inf)
    label = np.full(grid.shape, -1, dtype=np.int32)
    for k, (lon, lat) in enumerate(points):
        px = grid.pixel(lon, lat)
        if px is None:
            continue
        tt = grid.travel_time([px])
        better = np.isfinite(tt) & (tt < best)
        best[better] = tt[better]
        label[better] = k
    best[~np.isfinite(best)] = np.nan
    return best / 60, label


def polygons(label, hours, grid, markets, source, country):
    rows = []
    for geom, k in shapes(label, mask=label >= 0, transform=grid.transform):
        rows.append({"k": int(k), "geometry": shape(geom)})
    if not rows:
        return gpd.GeoDataFrame(columns=["geometry"], crs=4326)
    g = gpd.GeoDataFrame(rows, crs=4326).dissolve("k", as_index=False)
    out = []
    for r in g.itertuples():
        h = hours[label == r.k]
        h = h[np.isfinite(h)]
        m = markets.iloc[r.k]
        out.append({"source": source, "country": country, "market": m["name"],
                    "median_h": round(float(np.median(h)), 2) if h.size else None,
                    "p90_h": round(float(np.percentile(h, 90)), 2) if h.size else None,
                    "geometry": r.geometry})
    g = gpd.GeoDataFrame(out, crs=4326)
    g["area_km2"] = (g.to_crs(6933).area / 1e6).round(0)
    return g


def main():
    countries = fm.load_regions(layer="country").set_index("country")
    wfp = fm.load_wfp_markets().rename(columns={"market": "name", "longitude": "lon", "latitude": "lat"})
    loc = pd.read_csv(ROOT / "reports" / "market_locations.csv")
    fao = loc[loc["kind"] == "town"].rename(columns={"region": "name"})
    hfid = gpd.read_file(OUT / "hfid.geojson")[["hfid", "country", "geometry"]]

    catch = {"wfp": [], "fao": []}
    unit_stats = {}
    for country in fm.COUNTRIES:
        grid = CostGrid(countries.loc[country, "geometry"], "motorized")
        units = hfid[hfid["country"] == country].reset_index(drop=True)
        unit_id = rasterize(((g, i + 1) for i, g in enumerate(units.geometry)), out_shape=grid.shape,
                            transform=grid.transform, fill=0, dtype="int32")
        for source, mk in (("wfp", wfp), ("fao", fao)):
            m = mk[mk["country"] == country].reset_index(drop=True)
            if m.empty:
                continue
            hours, label = allocate(grid, zip(m["lon"], m["lat"]))
            catch[source].append(polygons(label, hours, grid, m, source, country))
            for i, u in units.iterrows():
                sel = unit_id == i + 1
                h, lab = hours[sel], label[sel]
                ok = np.isfinite(h) & (lab >= 0)
                st = unit_stats.setdefault(u["hfid"], {})
                if ok.any():
                    st[f"{source}_h"] = round(float(np.median(h[ok])), 2)
                    st[f"{source}_market"] = str(m.iloc[np.bincount(lab[ok]).argmax()]["name"])
                    st[f"{source}_n_catchments"] = int(np.unique(lab[ok]).size)
            print(f"  {country:9s} {source}: {len(m)} markets")

    for source, parts in catch.items():
        g = pd.concat(parts, ignore_index=True)
        g = gpd.GeoDataFrame(g, crs=4326)
        g["geometry"] = g.geometry.simplify(0.005, preserve_topology=True)
        path = OUT / f"catchments_{source}.geojson"
        path.write_text(g.to_json(drop_id=True))
        print(f"  catchments_{source}.geojson  {len(g)} catchments  {path.stat().st_size / 1e6:.2f} MB")
    (OUT / "hfid_prices.json").write_text(json.dumps(unit_stats))
    print(f"  hfid_prices.json  {len(unit_stats)} units")
    # fold the price fields into hfid.geojson so the map can fill units by them
    full = gpd.read_file(OUT / "hfid.geojson")
    extra = pd.DataFrame.from_dict(unit_stats, orient="index")
    full = full.drop(columns=[c for c in extra.columns if c in full.columns]).merge(extra, left_on="hfid", right_index=True, how="left")
    (OUT / "hfid.geojson").write_text(full.to_json(drop_id=True))
    print(f"  hfid.geojson updated with {', '.join(extra.columns)}")


if __name__ == "__main__":
    main()
