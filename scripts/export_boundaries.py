"""Compare the spatial units behind every dataset, and export them for the boundary-vis app.

Unit systems compared, per country:
    hfid        HFID admin-2 units (data/external/hfid/hfid_all_geom.gpkg): the harmonised target units
    zones       FEWS NET livelihood zones: the units FEWS IPC and the ML1/ML2 projections are reported on
    admin1/2    geoBoundaries provinces/states and districts (data/regions/<country>.geojson)
    smap        the SMAP L3 36 km EASE-Grid 2.0 cells (reference grid only: the cells actually averaged
                into data/inputs/soil_moisture.csv are not recorded anywhere in the data)
    markets     FAO price series (town, county, state group, national) and WFP markets

All areas and overlaps are computed in EPSG:6933 (equal area).

Outputs
    boundary-vis/public/data/*.geojson, summary.json      map layers and per-country comparison
    reports/crosswalk_hfid_zone.csv                       share of each HFID unit inside each zone
    reports/crosswalk_hfid_geoboundaries.csv              best geoBoundaries district per HFID unit

Run: python scripts/export_boundaries.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

import famine as fm

OUT = ROOT / "boundary-vis" / "public" / "data"
EA = 6933
SMAP_CELL = 36032.220840584  # EASE-Grid 2.0 global 36 km (SPL3SMP)
SMAP_X0, SMAP_Y0 = -17367530.44516138, 7314540.830638444
SMAP_CELL_KM2 = SMAP_CELL**2 / 1e6
NEST = 0.8  # a unit "nests" in a zone when at least this share of its area is inside it


def km2(g):
    return g.to_crs(EA).area / 1e6


def write(gdf, name, tol):
    gdf = gdf.to_crs(4326).copy()
    if tol:
        gdf["geometry"] = gdf.geometry.simplify(tol, preserve_topology=True)
    path = OUT / f"{name}.geojson"
    path.write_text(gdf.to_json(drop_id=True))
    print(f"  {name}.geojson  {len(gdf):5d} features  {path.stat().st_size / 1e6:.2f} MB")


def load_hfid():
    g = gpd.read_file(fm.DATA_DIR / "external/hfid/hfid_all_geom.gpkg",
                      where="ADMIN0 IN ({})".format(",".join(f"'{c}'" for c in fm.COUNTRIES)))
    g = g.rename(columns={"ADMIN0": "country", "ADMIN1": "admin1", "ADMIN2": "admin2"})
    g["hfid"] = g["country"] + "|" + g["admin1"].fillna("") + "|" + g["admin2"].fillna("")
    g = g.dissolve("hfid", as_index=False, aggfunc="first")  # one row per unit
    t = pd.read_csv(fm.DATA_DIR / "external/hfid/hfid_hv1.csv", low_memory=False)
    t = t[t["ADMIN0"].isin(fm.COUNTRIES)].copy()
    t["hfid"] = t["ADMIN0"] + "|" + t["ADMIN1"].fillna("") + "|" + t["ADMIN2"].fillna("")
    months = lambda col: t.loc[t[col].notna()].groupby("hfid")["year_month"].nunique()
    stats = pd.DataFrame({
        "months_fews": months("ipc_phase_fews"),
        "months_ipcch": months("ipc_phase_ipcch"),
        "months_fcs": months("fcs_rt mean"),
        "first": t.groupby("hfid")["year_month"].min(),
        "last": t.groupby("hfid")["year_month"].max(),
    })
    latest = t.dropna(subset=["ipc_phase_fews"]).sort_values("year_month").groupby("hfid").tail(1).set_index("hfid")
    stats["fews_latest"] = latest["ipc_phase_fews"]
    stats["fews_latest_month"] = latest["year_month"]
    g = g.merge(stats.reset_index(), on="hfid", how="left")
    for c in ["months_fews", "months_ipcch", "months_fcs"]:
        g[c] = g[c].fillna(0).astype(int)
    return g


def smap_grid(country_geom_ea, country):
    minx, miny, maxx, maxy = country_geom_ea.bounds
    i0, i1 = int((minx - SMAP_X0) // SMAP_CELL), int((maxx - SMAP_X0) // SMAP_CELL)
    j0, j1 = int((SMAP_Y0 - maxy) // SMAP_CELL), int((SMAP_Y0 - miny) // SMAP_CELL)
    rows = []
    for i in range(i0, i1 + 1):
        for j in range(j0, j1 + 1):
            cell = box(SMAP_X0 + i * SMAP_CELL, SMAP_Y0 - (j + 1) * SMAP_CELL, SMAP_X0 + (i + 1) * SMAP_CELL, SMAP_Y0 - j * SMAP_CELL)
            if not cell.intersects(country_geom_ea):
                continue
            frac = cell.intersection(country_geom_ea).area / cell.area
            rows.append({"country": country, "cell": f"{j}-{i}", "row": j, "col": i, "in_country": round(frac, 3), "geometry": cell})
    return gpd.GeoDataFrame(rows, crs=EA)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    regions = fm.load_regions()
    countries = regions[regions["layer"] == "country"][["country", "geometry"]]
    admin1 = regions[regions["layer"] == "admin1"][["country", "region", "geometry"]]
    admin2 = regions[regions["layer"] == "districts"][["country", "region", "geometry"]]
    zones = fm.load_livelihood_zones()[["country", "fnid", "zone", "map_version", "geometry"]]
    hfid = load_hfid()
    for g in (admin1, admin2, zones, hfid):
        g["area_km2"] = km2(g).round(0)

    # SMAP reference grid
    ce = countries.to_crs(EA)
    grid = pd.concat([smap_grid(geom, c) for c, geom in zip(ce["country"], ce.geometry)], ignore_index=True)
    grid = gpd.GeoDataFrame(grid, crs=EA)

    # markets: FAO towns as points, FAO area series as polygons, WFP markets as points
    loc = pd.read_csv(ROOT / "reports" / "market_locations.csv")
    towns = loc[loc["kind"] == "town"]
    fao_pts = gpd.GeoDataFrame(towns[["country", "region"]], geometry=gpd.points_from_xy(towns["lon"], towns["lat"]), crs=4326)
    area_rows = []
    for r in loc[loc["kind"] != "town"].itertuples():
        if r.region == "National Average":
            continue
        names = str(r.admin1).split(";")
        part = admin1[(admin1["country"] == r.country) & admin1["region"].isin(names)]
        area_rows.append({"country": r.country, "region": r.region, "scope": "states" if r.kind == "aggregate" else "county",
                          "geometry": part.union_all()})
    fao_areas = gpd.GeoDataFrame(area_rows, crs=4326)
    wfp = fm.load_wfp_markets()
    wfp_pts = gpd.GeoDataFrame(wfp[["country", "market"]], geometry=gpd.points_from_xy(wfp["longitude"], wfp["latitude"]), crs=4326)

    # ---- overlaps (equal area) ---------------------------------------------------------------
    H, Z, A2, G = (x.to_crs(EA) for x in (hfid, zones, admin2, grid))
    hz = gpd.overlay(H[["hfid", "country", "geometry"]], Z[["fnid", "zone", "geometry"]], how="intersection", keep_geom_type=True)
    hz["share"] = hz.area / hz["hfid"].map(H.set_index("hfid").area)
    hz = hz[hz["share"] >= 0.01]
    xw = hz[["hfid", "country", "fnid", "zone", "share"]].sort_values(["hfid", "share"], ascending=[True, False])
    xw.assign(share=xw["share"].round(3)).to_csv(ROOT / "reports/crosswalk_hfid_zone.csv", index=False)
    dom = xw.groupby("hfid").first()
    hfid["dominant_zone"] = hfid["hfid"].map(dom["zone"])
    hfid["dominant_fnid"] = hfid["hfid"].map(dom["fnid"])
    hfid["dominant_share"] = hfid["hfid"].map(dom["share"]).round(3)
    hfid["n_zones"] = hfid["hfid"].map(xw[xw["share"] >= 0.05].groupby("hfid").size()).fillna(0).astype(int)
    hfid["smap_cells"] = (hfid["area_km2"] / SMAP_CELL_KM2).round(2)  # area in SMAP-cell units
    # zones: how many HFID units, and how cleanly they nest
    zone_units = xw[xw["share"] >= 0.05].groupby("fnid")["hfid"].nunique()
    zones["n_hfid"] = zones["fnid"].map(zone_units).fillna(0).astype(int)
    nested = xw[xw["share"] >= NEST].groupby("fnid")["hfid"].nunique()
    zones["n_hfid_nested"] = zones["fnid"].map(nested).fillna(0).astype(int)
    zones["smap_cells"] = (zones["area_km2"] / SMAP_CELL_KM2).round(1)

    # HFID vs geoBoundaries districts: best-overlap district and its intersection-over-union
    ha = gpd.overlay(H[["hfid", "geometry"]], A2.reset_index()[["index", "region", "geometry"]], how="intersection", keep_geom_type=True)
    ha["inter"] = ha.area
    ha["iou"] = ha["inter"] / (ha["hfid"].map(H.set_index("hfid").area) + ha["index"].map(A2.area) - ha["inter"])
    best = ha.sort_values("iou", ascending=False).groupby("hfid").first()
    hfid["gb_district"] = hfid["hfid"].map(best["region"])
    hfid["gb_iou"] = hfid["hfid"].map(best["iou"]).round(3)
    best.reset_index()[["hfid", "region", "iou"]].rename(columns={"region": "geoboundaries_district"}).round(3).to_csv(
        ROOT / "reports/crosswalk_hfid_geoboundaries.csv", index=False)

    # markets per HFID unit and per zone
    def count_in(points, polys, key):
        j = gpd.sjoin(points.to_crs(EA), polys[[key, "geometry"]], predicate="within")
        return j.groupby(key).size()
    hfid["n_wfp"] = hfid["hfid"].map(count_in(wfp_pts, H, "hfid")).fillna(0).astype(int)
    hfid["n_fao"] = hfid["hfid"].map(count_in(fao_pts, H, "hfid")).fillna(0).astype(int)
    zones["n_wfp"] = zones["fnid"].map(count_in(wfp_pts, Z, "fnid")).fillna(0).astype(int)
    zones["n_fao"] = zones["fnid"].map(count_in(fao_pts, Z, "fnid")).fillna(0).astype(int)

    # SMAP regions present in the data (names only: their footprints are not recorded)
    sm = fm.load_soil_moisture()
    sm_regions = (sm.assign(country=sm["country"].astype(str), region=sm["region"].astype(str))
                  .groupby(["country", "region"]).agg(obs=("date", "size"), median_cells=("valid_cells", "median"),
                                                      max_cells=("valid_cells", "max")).reset_index())
    smart_regions = set(fm.load_smart(120)["region"].astype(str))

    # ---- per-country summary -------------------------------------------------------------------
    summary = {}
    for c in fm.COUNTRIES:
        h = hfid[hfid["country"] == c]
        z = zones[zones["country"] == c]
        g = grid[grid["country"] == c]
        summary[c] = {
            "units": {
                "hfid": {"n": len(h), "median_km2": float(h["area_km2"].median()), "median_smap_cells": float(h["smap_cells"].median())},
                "zones": {"n": len(z), "median_km2": float(z["area_km2"].median()) if len(z) else None,
                          "median_smap_cells": float(z["smap_cells"].median()) if len(z) else None},
                "admin1": {"n": int((admin1["country"] == c).sum()), "median_km2": float(admin1.loc[admin1["country"] == c, "area_km2"].median())},
                "admin2": {"n": int((admin2["country"] == c).sum()), "median_km2": float(admin2.loc[admin2["country"] == c, "area_km2"].median())},
                "smap": {"n": len(g), "full_cells": int((g["in_country"] >= 0.99).sum()), "cell_km2": round(SMAP_CELL_KM2)},
                "fao": {"towns": int((fao_pts["country"] == c).sum()), "areas": int((fao_areas["country"] == c).sum())},
                "wfp": {"n": int((wfp_pts["country"] == c).sum())},
            },
            "hfid_nested_share": float((h["dominant_share"] >= NEST).mean()),
            "hfid_median_dominant_share": float(h["dominant_share"].median()),
            "hfid_multi_zone_share": float((h["n_zones"] >= 2).mean()),
            "zone_median_hfid": float(z["n_hfid"].median()) if len(z) else None,
            "hfid_below_one_smap_cell": float((h["smap_cells"] < 1).mean()),
            "hfid_with_wfp": float((h["n_wfp"] > 0).mean()),
            "hfid_with_any_market": float(((h["n_wfp"] + h["n_fao"]) > 0).mean()),
            "hfid_gb_median_iou": float(h["gb_iou"].median()),
            "hfid_months": {k: int(h[k].max()) for k in ["months_fews", "months_ipcch", "months_fcs"]},
            "hfid_span": [str(h["first"].dropna().min()), str(h["last"].dropna().max())],
            "hfid_without_data": int(h["first"].isna().sum()),
            "smap_regions": [
                {"region": r.region, "obs": int(r.obs), "median_cells": float(r.median_cells), "max_cells": int(r.max_cells),
                 "smart": r.region in smart_regions}
                for r in sm_regions[sm_regions["country"] == c].itertuples()
            ],
        }

    write(countries, "countries", 0.01)
    write(admin1, "admin1", 0.004)
    write(admin2, "admin2", 0.002)
    write(zones, "zones", 0.003)
    keep = ["hfid", "country", "admin1", "admin2", "area_km2", "smap_cells", "dominant_zone", "dominant_fnid", "dominant_share",
            "n_zones", "gb_district", "gb_iou", "n_wfp", "n_fao", "months_fews", "months_ipcch", "months_fcs", "first", "last",
            "fews_latest", "fews_latest_month", "geometry"]
    write(hfid[keep], "hfid", 0.002)
    write(grid, "smap_grid", 0)
    write(fao_pts, "fao_towns", 0)
    write(fao_areas, "fao_areas", 0.004)
    write(wfp_pts, "wfp_markets", 0)
    (OUT / "summary.json").write_text(json.dumps(summary))
    print("  summary.json")
    for c in fm.COUNTRIES:
        s = summary[c]
        print(f"  {c:9s} HFID {s['units']['hfid']['n']} (median {s['units']['hfid']['median_km2']:.0f} km2, "
              f"{s['units']['hfid']['median_smap_cells']:.2f} SMAP cells) | nested in a zone {s['hfid_nested_share']:.0%} | "
              f"<1 SMAP cell {s['hfid_below_one_smap_cell']:.0%} | with a market {s['hfid_with_any_market']:.0%} | "
              f"geoBoundaries IoU {s['hfid_gb_median_iou']:.2f}")


if __name__ == "__main__":
    main()
