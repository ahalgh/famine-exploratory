"""Extract zone features from the FEWS NET livelihood reports with Claude (see famine/livelihood.py).

Stages (each cached per document / zone under data/derived/livelihood/, so re-runs only fill gaps):
    segment    one call per report  -> segments/<doc>.json
    extract    one call per zone    -> zones/<doc>__<NN>.json
    assemble   no API calls         -> reports/livelihood_zones.csv            one row per report x zone
                                       reports/livelihood_wealth_groups.csv    one row per report x zone x wealth group

Run:
    python scripts/extract_zone_features.py --dry-run                  # token and cost estimate, no API calls
    python scripts/extract_zone_features.py segment --countries guatemala nigeria
    python scripts/extract_zone_features.py extract --countries guatemala nigeria
    python scripts/extract_zone_features.py assemble

Credentials: ANTHROPIC_API_KEY (or any credential the anthropic SDK resolves).
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from famine import livelihood as lv

MODEL = "claude-opus-5-5"
PRICE_PER_MTOK = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}
CHARS_PER_TOKEN = 3.5          # rough, for --dry-run only
OUT_TOKENS = {"segment": 3_000, "extract": 6_000}   # rough output + thinking per call, for --dry-run only


def manifest(countries):
    m = pd.read_csv(lv.DOC_DIR / "manifest.csv")
    m = m[m["status"].isin(["cached", "downloaded"])]
    if countries:
        m = m[m["country"].isin(countries)]
    m["doc"] = m["file"].map(lv.doc_id)
    return m.reset_index(drop=True)


def pages_of(doc):
    return lv.page_texts(lv.DOC_DIR / "txt" / f"{doc}.txt")


# --------------------------------------------------------------------------- API

def make_client():
    import anthropic
    return anthropic.Anthropic(max_retries=5)


def call(client, model, system, user, schema, effort):
    """One structured-output call. Returns the parsed pydantic object and the usage."""
    with client.messages.stream(
        model=model,
        max_tokens=32_000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": _schema(schema)}},
        # Re-run on Anthropic's recommended fallback model if a safety classifier declines.
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
        extra_body={"fallbacks": "default"},
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"refused: {msg.stop_details}")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("hit max_tokens")
    text = "".join(b.text for b in msg.content if b.type == "text")
    return schema.model_validate_json(text), msg.usage


def _schema(model_cls):
    from anthropic import transform_schema  # strict-mode compatible JSON schema from pydantic
    return transform_schema(model_cls)


# --------------------------------------------------------------------------- stages

def run_segment(client, docs, model, workers):
    out = lv.OUT_DIR / "segments"
    out.mkdir(parents=True, exist_ok=True)
    todo = [d for d in docs["doc"] if not (out / f"{d}.json").exists()]
    print(f"segment: {len(todo)} of {len(docs)} reports to index")

    def one(doc):
        meta = docs.set_index("doc").loc[doc]
        user = (f"Report: {meta['country']} livelihood {meta['doc_type']} ({meta['slug']}), "
                f"{int(meta['pages'])} physical pages.\n\n" + lv.page_index(pages_of(doc)))
        seg, usage = call(client, model, lv.SEGMENT_SYSTEM, user, lv.DocumentSegments, effort="medium")
        (out / f"{doc}.json").write_text(seg.model_dump_json(indent=1))
        return doc, len(seg.zones), usage

    _pool(one, todo, workers)


def run_extract(client, docs, model, workers):
    out = lv.OUT_DIR / "zones"
    out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for doc in docs["doc"]:
        seg = lv.load_json(lv.OUT_DIR / "segments" / f"{doc}.json")
        if seg is None:
            print(f"  skip {doc}: not segmented yet")
            continue
        for i, z in enumerate(seg["zones"]):
            if not (out / f"{doc}__{i:02d}.json").exists():
                jobs.append((doc, i, z))
    print(f"extract: {len(jobs)} zones to extract")

    cache = {}

    def one(job):
        doc, i, z = job
        pages = cache.setdefault(doc, pages_of(doc))
        meta = docs.set_index("doc").loc[doc]
        user = (f"Report: {meta['country']} livelihood {meta['doc_type']} ({meta['slug']}).\n"
                f"Zone: {z['zone_code'] or ''} {z['zone_name']} (pages {z['first_page']}-{z['last_page']}).\n\n"
                + lv.section_text(pages, z["first_page"], z["last_page"]))
        prof, usage = call(client, model, lv.EXTRACT_SYSTEM, user, lv.ZoneProfile, effort="medium")
        rec = {"doc": doc, "section": i, **z, "profile": prof.model_dump()}
        (out / f"{doc}__{i:02d}.json").write_text(json.dumps(rec, indent=1))
        return f"{doc} #{i}", len(prof.wealth_groups), usage

    _pool(one, jobs, workers)


def _pool(fn, items, workers):
    tin = tout = 0
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(fn, it): it for it in items}
        for f in as_completed(futs):
            try:
                name, n, usage = f.result()
                tin += usage.input_tokens
                tout += usage.output_tokens
                print(f"  ok {name}: {n}")
            except Exception as e:
                print(f"  FAILED {futs[f] if isinstance(futs[f], str) else futs[f][:2]}: {e}")
    print(f"tokens: {tin:,} in, {tout:,} out")


# --------------------------------------------------------------------------- assemble

SHARE_FIELDS = {"food": list(lv.FoodSources.model_fields), "income": list(lv.IncomeSources.model_fields)}


def run_assemble(docs):
    zones, groups = [], []
    for path in sorted((lv.OUT_DIR / "zones").glob("*.json")):
        rec = json.loads(path.read_text())
        meta = docs.set_index("doc").loc[rec["doc"]] if rec["doc"] in set(docs["doc"]) else None
        if meta is None:
            continue
        p = rec.pop("profile")
        seg = lv.load_json(lv.OUT_DIR / "segments" / f"{rec['doc']}.json")
        base = dict(doc=rec["doc"], country=meta["country"], doc_type=meta["doc_type"], doc_date=meta["slug"],
                    reference_year=seg["reference_year"], section=rec["section"],
                    zone_code=p["zone_code"] or rec["zone_code"], zone_name=p["zone_name"],
                    first_page=rec["first_page"], last_page=rec["last_page"])
        row = dict(base)
        for k, v in p.items():
            if k in ("zone_code", "zone_name", "wealth_groups"):
                continue
            row[k] = ";".join(map(str, v)) if isinstance(v, list) else v
        row["n_wealth_groups"] = len(p["wealth_groups"])
        zones.append(row)
        for g in p["wealth_groups"]:
            grow = dict(base, **{k: v for k, v in g.items() if k not in ("food_sources", "income_sources")})
            for kind in ("food", "income"):
                block = g.get(f"{kind}_sources") or {}
                for f in SHARE_FIELDS[kind]:
                    s = block.get(f) or {}
                    lo, hi = s.get("low"), s.get("high")
                    grow[f"{kind}_{f}"] = (lo + hi) / 2 if lo is not None and hi is not None else (lo if lo is not None else hi)
                    grow[f"{kind}_{f}_evidence"] = s.get("evidence")
            groups.append(grow)
    zdf, gdf = pd.DataFrame(zones), pd.DataFrame(groups)
    (ROOT / "reports").mkdir(exist_ok=True)
    zdf.to_csv(ROOT / "reports/livelihood_zones.csv", index=False)
    gdf.to_csv(ROOT / "reports/livelihood_wealth_groups.csv", index=False)
    print(f"assemble: {len(zdf)} zone rows from {zdf['doc'].nunique() if len(zdf) else 0} reports, "
          f"{len(gdf)} wealth-group rows -> reports/livelihood_zones.csv, reports/livelihood_wealth_groups.csv")


# --------------------------------------------------------------------------- dry run

def dry_run(docs, model):
    seg_chars = sum(len(lv.page_index(pages_of(d))) for d in docs["doc"])
    ext_chars = sum(sum(len(lv._squash(p)) for p in pages_of(d)) for d in docs["doc"])  # upper bound: every page once
    n_docs = len(docs)
    n_zones = 10 * n_docs  # rough until segmentation has run
    pin, pout = PRICE_PER_MTOK[model]
    seg_in, ext_in = seg_chars / CHARS_PER_TOKEN, ext_chars / CHARS_PER_TOKEN
    seg_out, ext_out = n_docs * OUT_TOKENS["segment"], n_zones * OUT_TOKENS["extract"]
    cost = (seg_in + ext_in) / 1e6 * pin + (seg_out + ext_out) / 1e6 * pout
    print(f"{n_docs} reports, {docs['pages'].sum():.0f} pages, model {model}")
    print(f"  segment: ~{seg_in / 1e6:.1f}M input tokens, ~{seg_out / 1e6:.2f}M output")
    print(f"  extract: <= ~{ext_in / 1e6:.1f}M input tokens, ~{ext_out / 1e6:.1f}M output (assuming ~{n_zones} zones)")
    print(f"  rough cost: ${cost:,.0f} (estimate from character counts; segmentation pins down the zone count)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", nargs="?", choices=["segment", "extract", "assemble", "all"], default="all")
    ap.add_argument("--countries", nargs="*", help="fews.net country slugs, e.g. guatemala nigeria somalia")
    ap.add_argument("--model", default=MODEL, choices=list(PRICE_PER_MTOK))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    docs = manifest(args.countries)
    if args.dry_run:
        return dry_run(docs, args.model)
    if args.stage in ("segment", "extract", "all"):
        client = make_client()
        if args.stage in ("segment", "all"):
            run_segment(client, docs, args.model, args.workers)
        if args.stage in ("extract", "all"):
            run_extract(client, docs, args.model, args.workers)
    run_assemble(docs)


if __name__ == "__main__":
    main()
