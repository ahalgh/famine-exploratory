"""Export the extracted livelihood-profile features for the web app (web/public/data/livelihood.json).

Reads the per-zone records written by scripts/extract_zone_features.py (or by hand / agent extraction,
validated with scripts/validate_zone_json.py) from data/derived/livelihood/zones/ and joins them to the
current livelihood-zone map by (country, zone code). A record joins only if its report is at least as
recent as that zone map's effective year: older reports describe older zone boundaries, whose codes can
mean a different area today.

Output, keyed by the zone map's FNID:
    zones[fnid] = {source, system, crops, livestock, rainfall_mm, irrigation, market_access, migration,
                   months: {rainy, harvest, lean, labor}, hazards, chronic, coping, groups[...], notes,
                   metrics: {lh_purchase_poorest, lh_labour_poorest, lh_lean_months}}
    groups[i] = {group, households_pct, size, land_ha, cattle, shoats, staple_months,
                 food: {source: [mid, evidence]}, income: {source: [mid, evidence]}}

Run: python scripts/export_livelihood.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

import famine as fm
from famine import livelihood as lv

OUT = ROOT / "web" / "public" / "data" / "livelihood.json"
GROUP_ORDER = ["very poor", "poor", "middle", "better off", "all"]
LABOUR = ["agricultural_labor", "other_casual_labor"]


def mid(share):
    if not share:
        return None
    lo, hi = share.get("low"), share.get("high")
    v = (lo + hi) / 2 if lo is not None and hi is not None else (lo if lo is not None else hi)
    # a chart reading is a ±2.5 band around the measured value; at 0 or 100 the band is clipped
    if share.get("evidence") == "chart_visual" and lo is not None and hi is not None and hi - lo < 5:
        v = 100.0 if hi >= 100 else 0.0 if lo <= 0 else v
    return None if v is None else round(v, 1)


def shares(block):
    """{source: [midpoint %, evidence]} for the sources the report gives, largest first."""
    out = {k: [mid(s), s["evidence"]] for k, s in (block or {}).items() if s and mid(s) is not None}
    return dict(sorted(out.items(), key=lambda kv: -kv[1][0]))


def group_labels(groups):
    """Display labels; a repeated group (e.g. lower and upper middle mapped to 'middle') gets a suffix."""
    names = [g["group"] for g in groups]
    out = []
    for i, n in enumerate(names):
        label = n[0].upper() + n[1:]
        if names.count(n) > 1:
            k = names[:i].count(n)
            label += [" (lower)", " (upper)"][k] if names.count(n) == 2 else f" {k + 1}"
        out.append(label)
    return out


def doc_year(doc):
    m = re.search(r"(\d{4})", doc.split("__")[-1])
    return int(m.group(1)) if m else None


def main():
    manifest = pd.read_csv(lv.DOC_DIR / "manifest.csv")
    manifest["doc"] = manifest["file"].map(lv.doc_id)
    docs = manifest.set_index("doc")
    zmap = fm.load_livelihood_zones()
    zmap["lzcode_n"] = zmap["lzcode"].str.replace(r"\s+", "", regex=True).str.upper()

    zones, unmatched = {}, []
    for path in sorted((lv.OUT_DIR / "zones").glob("*.json")):
        rec = json.loads(path.read_text())
        p = rec["profile"]
        meta = docs.loc[rec["doc"]]
        country = meta["country"].replace("-", " ").title()
        code = re.sub(r"\s+", "", (p["zone_code"] or rec["zone_code"] or "")).upper()
        hit = zmap[(zmap["country"] == country) & (zmap["lzcode_n"] == code)]
        year = doc_year(rec["doc"])
        hit = hit[hit["eff_year"].isna() | (hit["eff_year"] <= (year or 0))]
        if hit.empty:
            unmatched.append(f"{rec['doc']} {code or '?'} {p['zone_name']}")
            continue

        groups = sorted(p["wealth_groups"], key=lambda g: GROUP_ORDER.index(g["group"]))
        poorest = groups[0] if groups else None
        food_p = shares(poorest["food_sources"]) if poorest else {}
        inc_p = shares(poorest["income_sources"]) if poorest else {}
        labour = [inc_p[k][0] for k in LABOUR if k in inc_p]
        entry = {
            "source": {
                "doc": rec["doc"], "url": meta["url"], "type": meta["doc_type"].replace("livelihoods-", "").replace("livelihood-", ""),
                "date": meta["slug"], "pages": [rec["first_page"], rec["last_page"]], "zone_name": p["zone_name"],
            },
            "system": p["livelihood_system"], "crops": p["main_crops"], "livestock": p["main_livestock"],
            "rainfall_mm": [p["annual_rainfall_mm_low"], p["annual_rainfall_mm_high"]],
            "irrigation": p["irrigation_importance"], "market_access": p["market_access"],
            "migration": p["migration_importance"],
            "months": {"rainy": p["rainy_season_months"], "harvest": p["main_harvest_months"],
                       "lean": p["lean_season_months"], "labor": p["peak_labor_demand_months"]},
            "hazards": p["hazards"], "chronic": p["chronic_hazards"], "coping": p["coping_strategies"],
            "reference_year": p["food_sources_reference_year"], "notes": p["notes"],
            "groups": [{
                "group": g["group"],
                "households_pct": [g["pct_households_low"], g["pct_households_high"]],
                "size": g["household_size"], "land_ha": g["land_cultivated_ha"], "cattle": g["cattle"],
                "shoats": g["shoats"], "staple_months": g["staple_self_sufficiency_months"],
                "food": shares(g["food_sources"]), "income": shares(g["income_sources"]),
            } for g in groups],
            "group_labels": group_labels(groups),
            "metrics": {
                "lh_purchase_poorest": food_p.get("purchase", [None])[0] if food_p else None,
                "lh_labour_poorest": round(sum(labour), 1) if labour else None,
                "lh_lean_months": len(p["lean_season_months"]) or None,
                "lh_poorest_group": poorest["group"] if poorest else None,
            },
        }
        for fnid in hit["fnid"]:
            prev = zones.get(fnid)
            if prev is None or prev["source"]["date"] < entry["source"]["date"]:  # newest report wins
                zones[fnid] = entry

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"zones": zones}, separators=(",", ":")))
    print(f"livelihood.json: {len(zones)} map zones with a profile, {OUT.stat().st_size / 1e3:.0f} kB")
    for u in unmatched:
        print(f"  not on the current map: {u}")


if __name__ == "__main__":
    main()
