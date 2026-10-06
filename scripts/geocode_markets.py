"""Locate FAO price markets offline with GeoNames (data/external/geonames/<CC>.txt).

Writes reports/market_locations.csv with one row per (country, region) in fao_prices.csv:
    kind        town | admin1 | aggregate
    lat, lon    point for towns; polygon centroid for admin1; country/zone centroid for aggregates
    admin1      matching admin1 polygon from data/regions (for admin1 and zone aggregates, ';'-separated)
    source      geonames:<id> | geojson | manual
    note        how the match was made / ambiguity

Run: python scripts/geocode_markets.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

import famine as fm
from famine.loaders import norm_region

ISO2 = {"Guatemala": "GT", "Kenya": "KE", "Malawi": "MW", "Nigeria": "NG", "Somalia": "SO", "Uganda": "UG"}
GEONAMES_COLS = ["geonameid", "name", "asciiname", "alternatenames", "lat", "lon", "fclass", "fcode",
                 "cc", "cc2", "admin1", "admin2", "admin3", "admin4", "population", "elevation", "dem",
                 "timezone", "modified"]

# Nigeria's six geopolitical zones (used as FAO "regions") -> states as named in nigeria.geojson.
NIGERIA_ZONES = {
    "North Central": ["Benue", "Kogi", "Kwara", "Nasarawa", "Niger", "Plateau", "Abuja Federal Capital Territory"],
    "North East": ["Adamawa", "Bauchi", "Borno", "Gombe", "Taraba", "Yobe"],
    "North West": ["Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Sokoto", "Zamfara"],
    "South East": ["Abia", "Anambra", "Ebonyi", "Enugu", "Imo"],
    "South South": ["Akwa Ibom", "Bayelsa", "Cross River", "Delta", "Edo", "Rivers"],
    "South West": ["Ekiti", "Lagos", "Ogun", "Ondo", "Osun", "Oyo"],
}
# Kenya price "regions" that are counties/districts rather than towns -> admin1 polygon name.
KENYA_ADMIN1 = {"Turkana": "Turkana", "Tana River": "Tana River", "Makueni": "Makueni",
                "Taita Taveta": "Taita Taveta", "Tharaka Nithi": "Tharaka", "Embu-Mbeere": "Embu"}


def load_geonames(cc: str) -> pd.DataFrame:
    g = pd.read_csv(ROOT / "data/external/geonames" / f"{cc}.txt", sep="\t", names=GEONAMES_COLS,
                    dtype={"admin1": str}, keep_default_na=False, quoting=3)
    return g[g["fclass"] == "P"]  # populated places only


def find_town(gn: pd.DataFrame, name: str):
    key = norm_region(name)
    exact = gn[(gn["name"].map(norm_region) == key) | (gn["asciiname"].map(norm_region) == key)]
    how = "name"
    if exact.empty:
        alt = gn[gn["alternatenames"].str.split(",").map(lambda xs: key in {norm_region(x) for x in xs if x})]
        exact, how = alt, "alternate name"
    if exact.empty:
        return None
    exact = exact.sort_values("population", ascending=False)
    best = exact.iloc[0]
    note = f"GeoNames {how} match ({best.fcode}, pop {best.population:,})"
    if len(exact) > 1:
        note += f"; {len(exact)} candidates, took most populous"
    return best, note


def main():
    prices = fm.load_prices()
    regions = fm.load_regions()
    admin1 = regions[regions["layer"] == "admin1"].copy()
    admin1["centroid"] = admin1.to_crs(6933).centroid.to_crs(4326)
    countries = regions[regions["layer"] == "country"].set_index("country")
    country_centroid = countries.to_crs(6933).centroid.to_crs(4326)

    rows = []
    for (country, region), _ in prices.groupby(["country", "region"], observed=True):
        country, region = str(country), str(region)
        a1 = admin1[admin1["country"] == country]
        rec = dict(country=country, region=region, kind=None, lat=None, lon=None, admin1="", source="", note="")
        if region == "National Average":
            c = country_centroid[country]
            rec.update(kind="aggregate", lat=c.y, lon=c.x, source="geojson", note="national average")
        elif country == "Nigeria" and region in NIGERIA_ZONES:
            states = NIGERIA_ZONES[region]
            zone = a1[a1["region"].isin(states)]
            assert len(zone) == len(states), f"missing states for {region}"
            pt = zone.dissolve().to_crs(6933).centroid.to_crs(4326).iloc[0]
            rec.update(kind="aggregate", lat=pt.y, lon=pt.x, admin1=";".join(states), source="manual",
                       note="Nigerian geopolitical zone (group of states)")
        elif country == "Kenya" and region in KENYA_ADMIN1:
            poly = a1[a1["region"] == KENYA_ADMIN1[region]]
            pt = poly["centroid"].iloc[0]
            rec.update(kind="admin1", lat=pt.y, lon=pt.x, admin1=KENYA_ADMIN1[region], source="geojson",
                       note="county/district name, not a town; centroid of admin1 polygon")
        else:
            hit = find_town(load_geonames(ISO2[country]), region)
            if hit is None:
                rec.update(kind="unmatched", note="no GeoNames populated place found")
            else:
                best, note = hit
                rec.update(kind="town", lat=float(best.lat), lon=float(best.lon),
                           source=f"geonames:{best.geonameid}", note=note)
                # record which admin1 polygon the point falls in

                from shapely.geometry import Point
                inside = a1[a1.contains(Point(rec["lon"], rec["lat"]))]
                rec["admin1"] = inside["region"].iloc[0] if len(inside) else ""
                if not len(inside):
                    rec["note"] += "; point outside all admin1 polygons"
        rows.append(rec)

    out = pd.DataFrame(rows)
    out[["lat", "lon"]] = out[["lat", "lon"]].astype(float).round(5)
    path = ROOT / "reports" / "market_locations.csv"
    out.to_csv(path, index=False)
    print(out.to_string(index=False))
    print(f"\nwrote {path}  |  kinds: {out['kind'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
