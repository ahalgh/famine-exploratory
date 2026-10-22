"""Export compact, map-ready data for the web app into web/public/data/ (git-ignored).

Outputs
    countries.geojson   ADM0 outlines + per-dataset coverage counts
    admin1.geojson      ADM1 polygons (simplified)
    districts.geojson   ADM2 polygons (simplified); Guatemala districts carry FEWS/ML1 IPC
    markets.geojson     FAO price markets (from reports/market_locations.csv) + series stats
    wfp_markets.geojson WFP markets with prices since 2019 + series stats
    fao_areas.geojson   FAO price series that refer to an area, not a town: Kenya county series,
                        Nigerian geopolitical zones (groups of states) and national averages
    access/*.png        1 km travel-time surfaces per country, reprojected to Web Mercator, with
                        minutes packed into R (high byte) and G (low byte), A=0 where no data;
    access/index.json   the corner coordinates of each image
    history.json        per zone: every observed IPC report and every ML1/ML2 projection; per
                        WFP market: a real staple-price index; per country: monthly conflict
    zones.geojson       FEWS NET livelihood zones (simplified) + travel-time access
                        (reports/zone_access_2019.csv) + observed IPC summary since 2020
    coverage.json       monthly row counts per country x dataset, plus dataset metadata

Run: python scripts/geocode_markets.py && python scripts/compute_accessibility.py && python scripts/export_map_data.py
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
SIMPLIFY = {"country": 0.01, "admin1": 0.005, "districts": 0.003, "zones": 0.005}  # degrees

DATASETS = [
    # key, label, group, date column, loader
    ("fews", "FEWS current situation (IPC)", "ground truth", "date", fm.load_fews),
    ("ml1", "FEWS ML1 projection", "outputs", "issued", lambda: fm.load_ml("ml1")),
    ("ml2", "FEWS ML2 projection", "outputs", "issued", lambda: fm.load_ml("ml2")),
    ("smart", "SMART trigger (120)", "outputs", "date", lambda: fm.load_smart(120)),
    ("soil", "Soil moisture (SMAP)", "inputs", "date", fm.load_soil_moisture),
    ("prices", "FAO food prices", "inputs", "date", fm.load_prices),
    ("wfp", "WFP market prices", "inputs", "date", fm.load_wfp_prices),
    ("conflict", "ACLED conflict (monthly)", "inputs", "date", lambda: fm.load_conflict("monthly")),
    ("cpi", "World Bank CPI (annual)", "inputs", "year", fm.load_cpi),
]


def write_geojson(gdf: gpd.GeoDataFrame, name: str, tol: float):
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.simplify(tol, preserve_topology=True)
    path = OUT / f"{name}.geojson"
    path.write_text(gdf.to_json(drop_id=True, to_wgs84=True))
    print(f"  {name}.geojson  {len(gdf):4d} features  {path.stat().st_size / 1e6:.2f} MB")


ACCESS_LAYERS = ["city_motorized", "city_walking", "market_motorized", "market_walking"]


def export_access_rasters():
    """Reproject each country's travel-time raster to EPSG:3857 and pack minutes into a PNG."""
    import numpy as np
    import rasterio
    from PIL import Image
    from rasterio.warp import Resampling, calculate_default_transform, reproject, transform as warp_xy

    out_dir = OUT / "access"
    out_dir.mkdir(parents=True, exist_ok=True)
    index = {}
    for country in fm.COUNTRIES:
        for layer in ACCESS_LAYERS:
            src_path = fm.DATA_DIR / "derived/access" / f"{country.lower()}_tt_{layer}.tif"
            if not src_path.exists():
                continue
            with rasterio.open(src_path) as src:
                t, w, h = calculate_default_transform(src.crs, "EPSG:3857", src.width, src.height, *src.bounds)
                dst = np.full((h, w), np.nan, dtype="float32")
                reproject(rasterio.band(src, 1), dst, src_transform=src.transform, src_crs=src.crs,
                          dst_transform=t, dst_crs="EPSG:3857", resampling=Resampling.nearest, dst_nodata=np.nan)
            valid = np.isfinite(dst)
            minutes = np.clip(np.nan_to_num(dst, nan=0), 0, 65534).round().astype("uint16")
            rgba = np.zeros((h, w, 4), dtype="uint8")
            rgba[..., 0] = minutes >> 8
            rgba[..., 1] = minutes & 0xFF
            rgba[..., 3] = np.where(valid, 255, 0)
            name = f"{country.lower()}_{layer}.png"
            Image.fromarray(rgba, "RGBA").save(out_dir / name, optimize=True)
            left, top = t.c, t.f
            right, bottom = left + t.a * w, top + t.e * h
            lons, lats = warp_xy("EPSG:3857", "EPSG:4326", [left, right, right, left], [top, top, bottom, bottom])
            index.setdefault(country, {})[layer] = {
                "url": f"/data/access/{name}", "width": w, "height": h,
                "coordinates": [[round(x, 6), round(y, 6)] for x, y in zip(lons, lats)],  # TL, TR, BR, BL
            }
    (out_dir / "index.json").write_text(json.dumps(index))
    size = sum(f.stat().st_size for f in out_dir.glob("*.png")) / 1e6
    print(f"  access/*.png  {sum(len(v) for v in index.values())} rasters  {size:.1f} MB")


def export_fao_areas(regions):
    """FAO series priced over an area: draw the area itself, not a point at its centre."""
    loc = pd.read_csv(ROOT / "reports" / "market_locations.csv")
    prices = fm.load_prices()
    prices["country"] = prices["country"].astype(str)
    prices["region"] = prices["region"].astype(str)
    stats = prices.groupby(["country", "region"]).agg(
        n_rows=("raw_price", "size"),
        n_series=("commodity", lambda s: s.astype(str).nunique()),
        commodities=("commodity", lambda s: ", ".join(sorted(s.astype(str).unique()))),
        first=("date", lambda d: d.min().strftime("%Y-%m")),
        last=("date", lambda d: d.max().strftime("%Y-%m")),
    ).reset_index()
    admin1 = regions[regions["layer"] == "admin1"]
    countries = regions[regions["layer"] == "country"].set_index("country")
    rows = []
    for r in loc[loc["kind"] != "town"].itertuples():
        if r.region == "National Average":
            geom, scope = countries.loc[r.country, "geometry"], "national average"
        else:
            names = str(r.admin1).split(";")
            part = admin1[(admin1["country"] == r.country) & admin1["region"].isin(names)]
            geom = part.union_all()
            scope = "Nigerian geopolitical zone" if r.kind == "aggregate" else "county or district series"
        rows.append({"country": r.country, "region": r.region, "scope": scope, "admin1": r.admin1 if isinstance(r.admin1, str) else "",
                     "geometry": geom})
    areas = gpd.GeoDataFrame(rows, crs=4326).merge(stats, on=["country", "region"], how="left")
    write_geojson(areas, "fao_areas", SIMPLIFY["admin1"])


STAPLES = r"maize|sorghum|millet|rice|beans|cassava|wheat"


def export_history():
    """Time series for the zone view: IPC reports and projections, market prices, conflict."""
    import numpy as np

    lz = fm.load_livelihood_zones()
    key_to_fnid = {(c, k): f for c, k, f in zip(lz["country"], lz["zone_key"], lz["fnid"])}
    month = lambda d: d.strftime("%Y-%m")

    def fnids(df):
        return [key_to_fnid.get((str(c), fm.zone_key(str(c), r))) for c, r in zip(df["country"], df["region"])]

    zones = {f: {"obs": [], "ml1": [], "ml2": [], "markets": []} for f in lz["fnid"]}
    obs = fm.load_fews()
    obs = obs[obs["area_type"] == "livelihood zone"].assign(fnid=lambda d: fnids(d)).dropna(subset=["fnid"])
    for r in obs.sort_values("date").itertuples():
        zones[r.fnid]["obs"].append([month(r.date), int(r.ipc)])
    for h in ("ml1", "ml2"):
        ml = fm.load_ml(h)
        ml = ml[ml["area_type"] == "livelihood zone"].assign(fnid=lambda d: fnids(d)).dropna(subset=["fnid"])
        for r in ml.sort_values("issued").itertuples():
            zones[r.fnid][h].append([month(r.issued), month(r.valid_from), month(r.valid_until), int(r.predicted_ipc)])

    # report dates per country (zone-level reports only)
    report_dates = {c: sorted({month(d) for d in g["date"]}) for c, g in obs.groupby(obs["country"].astype(str))}

    # WFP markets: one staple series each, as a real price index (nominal / annual CPI, mean = 100)
    prices = fm.load_wfp_prices()
    prices = prices[(prices["date"] >= "2019-01-01") & prices["commodity"].astype(str).str.contains(STAPLES, case=False)
                    & ~prices["priceflag"].astype(str).str.contains("forecast")].copy()
    prices["month"] = prices["date"].dt.to_period("M")
    prices["series"] = prices["commodity"].astype(str) + " | " + prices["unit"].astype(str) + " | " + prices["pricetype"].astype(str)
    cpi = fm.load_cpi()
    cpi_by = {(c, y): v for c, y, v in zip(cpi["country"].astype(str), cpi["year"], cpi["cpi"])}
    cpi_last = cpi.groupby(cpi["country"].astype(str))["year"].max().to_dict()
    markets = fm.load_wfp_markets()
    out_markets = {}
    for mid, g in prices.groupby("market_id"):
        months_per = g.groupby("series")["month"].nunique()
        if months_per.max() < 6:
            continue
        series = months_per.idxmax()
        s_ = g[g["series"] == series].groupby("month")["price"].median().sort_index()
        country = str(g["country"].iloc[0])
        real = country in cpi_last
        if real:
            defl = [cpi_by.get((country, min(m.year, cpi_last[country]))) for m in s_.index]
            s_ = s_ / np.array(defl, dtype=float)
        idx = 100 * s_ / s_.mean()
        out_markets[int(mid)] = {
            "name": str(g["market"].iloc[0]), "country": country, "series": series.replace(" | ", ", "),
            "real": real, "points": [[str(m), round(float(v), 1)] for m, v in idx.items()],
        }

    # attach markets to zones: those inside the zone, else the two nearest in the same country
    mk = markets[markets["market_id"].isin(out_markets)]
    mk = gpd.GeoDataFrame(mk, geometry=gpd.points_from_xy(mk["longitude"], mk["latitude"]), crs=4326).to_crs(6933)
    zz = lz.to_crs(6933)
    inside = gpd.sjoin(mk[["market_id", "geometry"]], zz[["fnid", "geometry"]], predicate="within")
    for z in zz.itertuples():
        ids = inside.loc[inside["fnid"] == z.fnid, "market_id"].tolist()
        if ids:
            picks = [(int(i), 0.0) for i in ids[:4]]
        else:
            same = mk[mk["country"] == z.country]
            if same.empty:
                continue
            d = same.distance(z.geometry.representative_point()) / 1000
            picks = [(int(same.loc[i, "market_id"]), round(float(d[i]))) for i in d.nsmallest(2).index]
        zones[z.fnid]["markets"] = [{"id": i, "km": km} for i, km in picks]

    cf = fm.load_conflict("monthly")
    conflict = {str(c): [[month(r.date), int(r.political_violence_events), int(r.political_violence_fatalities)]
                         for r in g.sort_values("date").itertuples()] for c, g in cf.groupby(cf["country"].astype(str))}

    payload = {"reportDates": report_dates, "zones": zones, "markets": out_markets, "conflict": conflict,
               "cpiLastYear": cpi_last}
    path = OUT / "history.json"
    path.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"  history.json  {len(zones)} zones, {len(out_markets)} markets  {path.stat().st_size / 1e6:.2f} MB")


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
    markets = loc[loc["kind"] == "town"].merge(stats, on=["country", "region"], how="left")
    markets = gpd.GeoDataFrame(markets, geometry=gpd.points_from_xy(markets["lon"], markets["lat"]), crs=4326)
    markets["admin1"] = markets["admin1"].fillna("")
    write_geojson(markets.drop(columns=["lat", "lon"]), "markets", 0)

    # WFP markets active since 2019
    wfp = fm.load_wfp_prices()
    wfp = wfp[wfp["date"] >= "2019-01-01"]
    wstats = wfp.groupby("market_id").agg(
        n_rows=("price", "size"),
        n_commodities=("commodity", lambda s: s.astype(str).nunique()),
        first=("date", lambda d: d.min().strftime("%Y-%m")),
        last=("date", lambda d: d.max().strftime("%Y-%m")),
        n_months=("date", lambda d: d.dt.to_period("M").nunique()),
    ).reset_index()
    wm = fm.load_wfp_markets().merge(wstats, on="market_id", how="left")
    wm = gpd.GeoDataFrame(wm, geometry=gpd.points_from_xy(wm["longitude"], wm["latitude"]), crs=4326)
    write_geojson(wm[["market_id", "market", "country", "admin1", "admin2", "n_rows", "n_commodities",
                      "first", "last", "n_months", "geometry"]], "wfp_markets", 0)

    # livelihood zones with access and observed IPC (2020+, when every zone joins)
    zones = fm.load_livelihood_zones()
    access = pd.read_csv(ROOT / "reports" / "zone_access_2019.csv").drop(columns=["zone", "fnid", "lzcode", "map_version", "eff_year"])
    zones = zones.merge(access, on=["country", "zone_key"], how="left")
    obs = fews[(fews["area_type"] == "livelihood zone") & (fews["date"] >= "2020-01-01")].copy()
    obs["country"] = obs["country"].astype(str)
    obs["zone_key"] = [fm.zone_key(c, r) for c, r in zip(obs["country"], obs["region"])]
    obs["ipc_i"] = obs["ipc"].astype(int)
    latest = obs.sort_values("date").groupby(["country", "zone_key"]).tail(1).set_index(["country", "zone_key"])
    ipc = obs.groupby(["country", "zone_key"]).agg(
        ipc_mean=("ipc_i", "mean"), ipc3_share=("ipc_i", lambda s: (s >= 3).mean()), ipc_reports=("ipc_i", "size"))
    ipc["ipc_latest"] = latest["ipc_i"]
    ipc["ipc_latest_date"] = latest["date"].dt.strftime("%Y-%m")
    zones = zones.merge(ipc.round(2).reset_index(), on=["country", "zone_key"], how="left")
    write_geojson(zones.drop(columns=["zone_key"]), "zones", SIMPLIFY["zones"])

    export_fao_areas(regions)
    export_history()
    export_access_rasters()

    (OUT / "coverage.json").write_text(json.dumps(cov))
    print(f"  coverage.json  {len(cov['datasets'])} datasets x {len(cov['months'])} months")


if __name__ == "__main__":
    main()
