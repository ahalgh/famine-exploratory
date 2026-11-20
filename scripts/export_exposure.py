"""Exposure view data: how many people depend on each food and income source, by livelihood zone and wealth group.

Reads the Explore Livelihood dataset (https://huggingface.co/datasets/ahalgh/explore-livelihood): people per zone
and wealth group (map_zone_groups, WorldPop 2020) and each group's food / income shares (shares). Writes
web/public/data/exposure.json; the page does the arithmetic so the shock size and threshold can be changed live.

    python scripts/export_exposure.py [path/to/explore_livelihood/data]

Rules
- A group's share for a category is the report's mid value, with its low/high band.
- A category the report does not list for a group whose breakdown in that domain exists is 0.
- A group with no shares in a domain is unknown for that domain (counted as "no breakdown", never as 0).
- Specific crops are not quantified in the profiles; `zones[].crops` lists each zone's main crops so the page can
  give an upper bound (everyone living in zones where the crop is a main crop).
"""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "external" / "explore_livelihood" / "data"
OUT = ROOT / "web" / "public" / "data" / "exposure.json"
COUNTRIES = ["Kenya", "Malawi", "Nigeria", "Uganda", "Somalia", "Guatemala"]


def r1(x):
    return None if pd.isna(x) else round(float(x), 1)


def main():
    mz = pd.read_parquet(SRC / "map_zones.parquet")
    groups = pd.read_parquet(SRC / "map_zone_groups.parquet")
    shares = pd.read_parquet(SRC / "shares.parquet")
    shares = shares[shares["domain"].isin(["food", "income"])]
    zones = pd.read_parquet(SRC / "zones.parquet").set_index("record_id")

    by_group = {k: g for k, g in shares.groupby(["record_id", "group_index"])}
    rows = []
    for g in groups.itertuples():
        sh = by_group.get((g.primary_record_id, g.group_index))
        row = {"c": g.country, "fnid": g.fnid, "zone": g.map_zone_name, "g": g.group, "label": g.group_label,
               "p": int(round(g.people_2020))}
        for domain in ("food", "income"):
            d = None if sh is None else sh[sh["domain"] == domain]
            if d is None or d.empty:
                row[domain] = None
                continue
            row[domain] = {r.category: [r1(r.low), r1(r.mid), r1(r.high)] for r in d.itertuples()}
        rows.append(row)

    zone_list = []
    for z in mz.itertuples():
        rec = zones.loc[z.primary_record_id] if isinstance(z.primary_record_id, str) and z.primary_record_id in zones.index else None
        crops = sorted({c.strip().lower() for c in (rec["main_crops"] if rec is not None else [])}) if rec is not None else []
        zone_list.append({"c": z.country, "fnid": z.fnid, "zone": z.map_zone_name, "p": int(round(z.population_2020 or 0)),
                          "crops": crops, "profile_date": None if pd.isna(z.profile_date) else str(z.profile_date)[:7]})

    countries = {}
    for c in COUNTRIES:
        cz = [z for z in zone_list if z["c"] == c]
        cr = [r for r in rows if r["c"] == c]
        countries[c] = {
            "population": sum(z["p"] for z in cz),
            "food": sum(r["p"] for r in cr if r["food"]),
            "income": sum(r["p"] for r in cr if r["income"]),
            "by_wealth_group": sum(r["p"] for r in cr if r["g"] != "all"),
        }

    OUT.write_text(json.dumps({"countries": countries, "rows": rows, "zones": zone_list}, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e3:.0f} kB): {len(rows)} zone x group rows, {len(zone_list)} zones")
    for c, v in countries.items():
        print(f"  {c:9s} pop {v['population'] / 1e6:6.1f}M  food {v['food'] / 1e6:6.1f}M  income {v['income'] / 1e6:6.1f}M")


if __name__ == "__main__":
    main()
