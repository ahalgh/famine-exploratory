"""Export compact, map-ready data for the web app into web/public/data/ (git-ignored).

Outputs
    countries.geojson   ADM0 outlines + per-dataset coverage counts
    admin1.geojson      ADM1 polygons (simplified)
    districts.geojson   ADM2 polygons (simplified); Guatemala districts carry FEWS/ML1 IPC
    markets.geojson     FAO price markets (from reports/market_locations.csv) + series stats
    coverage.json       monthly row counts per country x dataset, plus dataset metadata

Run: python scripts/geocode_markets.py && python scripts/export_map_data.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import geopandas as gpd
import pandas as pd

import famine as fm

OUT = ROOT / "web" / "public" / "data"
SIMPLIFY = {"country": 0.01, "admin1": 0.005, "districts": 0.003}  # degrees

DATASETS = [
    # key, label, group, date column, loader
    ("fews", "FEWS current situation (IPC)", "ground truth", "date", fm.load_fews),
    ("ml1", "FEWS ML1 projection", "outputs", "issued", lambda: fm.load_ml("ml1")),
    ("ml2", "FEWS ML2 projection", "outputs", "issued", lambda: fm.load_ml("ml2")),
    ("smart", "SMART trigger (120)", "outputs", "date", lambda: fm.load_smart(120)),
    ("soil", "Soil moisture (SMAP)", "inputs", "date", fm.load_soil_moisture),
    ("prices", "FAO food prices", "inputs", "date", fm.load_prices),
    ("conflict", "ACLED conflict (monthly)", "inputs", "date", lambda: fm.load_conflict("monthly")),
    ("cpi", "World Bank CPI (annual)", "inputs", "year", fm.load_cpi),
]


def write_geojson(gdf: gpd.GeoDataFrame, name: str, tol: float):
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.simplify(tol, preserve_topology=True)
    path = OUT / f"{name}.geojson"
    path.write_text(gdf.to_json(drop_id=True, to_wgs84=True))
    print(f"  {name}.geojson  {len(gdf):4d} features  {path.stat().st_size / 1e6:.2f} MB")


def coverage():
    months = pd.period_range("2018-12", "2026-09", freq="M")
    out = {"months": [str(m) for m in months], "countries": fm.COUNTRIES, "datasets": [], "counts": {}}
    for key, label, group, dcol, loader in DATASETS:
        df = loader()
        if dcol == "year":  # spread annual rows over their 12 months
            per = df.assign(month=df["year"].map(lambda y: pd.period_range(f"{y}-01", f"{y}-12", freq="M"))).explode("month")
        else:
            per = df.assign(month=df[dcol].dt.to_period("M"))
        per["country"] = per["country"].astype(str)
        tab = per.groupby(["country", "month"]).size()
        counts = {c: [int(tab.get((c, m), 0)) for m in months] for c in fm.COUNTRIES}
        by_country = df["country"].astype(str).value_counts()
        out["datasets"].append({"key": key, "label": label, "group": group, "rows": int(len(df)),
                                "annual": dcol == "year",
                                "rows_by_country": {c: int(by_country.get(c, 0)) for c in fm.COUNTRIES}})
        out["counts"][key] = counts
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    regions = fm.load_regions()
    cov = coverage()

    # countries with dataset coverage summary
    countries = regions[regions["layer"] == "country"][["country", "iso3", "geometry"]].copy()
    for d in cov["datasets"]:
        countries[f"n_{d['key']}"] = countries["country"].map(lambda c: sum(cov["counts"][d["key"]][c]))
    countries["n_datasets"] = countries[[f"n_{d['key']}" for d in cov["datasets"]]].gt(0).sum(axis=1)
    write_geojson(countries, "countries", SIMPLIFY["country"])

    admin1 = regions[regions["layer"] == "admin1"][["country", "region", "region_id", "geometry"]]
    write_geojson(admin1, "admin1", SIMPLIFY["admin1"])

    # districts; Guatemala districts get observed (2019-02) and projected (2018-12 ML1) IPC
    districts = regions[regions["layer"] == "districts"][["country", "region", "region_id", "region_key", "geometry"]].copy()
    fews = fm.load_fews()
    ml1 = fm.load_ml("ml1")
    gt_obs = fews[(fews["country"] == "Guatemala")].groupby("region_key")["ipc"].first().astype(int)
    gt_ml1 = ml1[(ml1["country"] == "Guatemala")].groupby("region_key")["predicted_ipc"].first().astype(int)
    is_gt = districts["country"] == "Guatemala"
    districts["ipc_fews_2019_02"] = districts["region_key"].map(gt_obs).where(is_gt)
    districts["ipc_ml1_2018_12"] = districts["region_key"].map(gt_ml1).where(is_gt)
    write_geojson(districts.drop(columns="region_key"), "districts", SIMPLIFY["districts"])

    # markets with series stats
    loc = pd.read_csv(ROOT / "reports" / "market_locations.csv").dropna(subset=["lat", "lon"])
    prices = fm.load_prices()
    prices["country"] = prices["country"].astype(str)
    prices["region"] = prices["region"].astype(str)
    stats = prices.groupby(["country", "region"]).agg(
        n_rows=("raw_price", "size"),
        n_series=("commodity", lambda s: s.astype(str).nunique()),
        commodities=("commodity", lambda s: ", ".join(sorted(s.astype(str).unique()))),
        first=("date", lambda d: d.min().strftime("%Y-%m")),
        last=("date", lambda d: d.max().strftime("%Y-%m")),
        n_months=("date", lambda d: d.dt.to_period("M").nunique()),
    ).reset_index()
    markets = loc.merge(stats, on=["country", "region"], how="left")
    markets = gpd.GeoDataFrame(markets, geometry=gpd.points_from_xy(markets["lon"], markets["lat"]), crs=4326)
    markets["admin1"] = markets["admin1"].fillna("")
    write_geojson(markets.drop(columns=["lat", "lon"]), "markets", 0)

    (OUT / "coverage.json").write_text(json.dumps(cov))
    print(f"  coverage.json  {len(cov['datasets'])} datasets x {len(cov['months'])} months")


if __name__ == "__main__":
    main()
