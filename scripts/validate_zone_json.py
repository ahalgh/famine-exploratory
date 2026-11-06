"""Validate hand- or agent-written zone records against famine.livelihood.ZoneProfile.

Run: python scripts/validate_zone_json.py data/derived/livelihood/zones/<doc>__NN.json [...]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from famine.livelihood import ZoneProfile

ok = True
for f in sys.argv[1:]:
    rec = json.loads(Path(f).read_text())
    missing = {"doc", "section", "zone_code", "zone_name", "first_page", "last_page", "profile"} - set(rec)
    try:
        if missing:
            raise ValueError(f"record keys missing: {sorted(missing)}")
        p = ZoneProfile.model_validate(rec["profile"])
        print(f"OK   {f}: {p.zone_code} {len(p.wealth_groups)} wealth groups")
    except Exception as e:
        ok = False
        print(f"FAIL {f}: {e}")
sys.exit(0 if ok else 1)
