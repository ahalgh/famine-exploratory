"""Download every FEWS NET livelihood profile / description / baseline / fact sheet as PDF.

The document list comes from the fews.net sitemap (the site has no index page for these). Each
document page has a `/print` variant that serves the full report as a PDF.

Outputs (git-ignored)
    data/external/fews_livelihood/pdf/<country>__<doc_type>__<slug>.pdf
    data/external/fews_livelihood/manifest.csv   one row per document: url, region, country,
        doc_type, slug, file, bytes, pages, status

Already-downloaded files are skipped, so the script can be re-run after a failure.

Run: python scripts/fetch_livelihood_docs.py [--workers 4]
"""

import argparse
import re
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

import famine as fm

SITEMAP = "https://fews.net/sitemap.xml"
DOC_TYPES = ["livelihood-profile", "livelihood-description", "livelihood-baseline", "livelihoods-fact-sheets"]
UA = "famine-exploratory research crawler (python urllib)"
OUT = fm.DATA_DIR / "external/fews_livelihood"
URL_RE = re.compile(r"https://fews\.net/([^/]+)/([^/]+)/(" + "|".join(DOC_TYPES) + r")/([^/<\s]+)$")


def get(url, timeout=180, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), r.headers.get_content_type()
        except Exception as e:  # network hiccups: back off and retry
            if i == tries - 1:
                raise
            print(f"  retry {url}: {e}")
            time.sleep(5 * (i + 1))


def list_documents():
    index, _ = get(SITEMAP)
    pages = re.findall(rb"<loc>([^<]+)</loc>", index)
    with ThreadPoolExecutor(4) as ex:
        bodies = list(ex.map(lambda u: get(u.decode().replace("&amp;", "&"))[0], pages))
    urls = sorted({u.decode() for b in bodies for u in re.findall(rb"<loc>([^<]+)</loc>", b)})
    rows = []
    for u in urls:
        m = URL_RE.match(u)
        if m:
            region, country, doc_type, slug = m.groups()
            rows.append(dict(url=u, region=region, country=country, doc_type=doc_type, slug=slug,
                             file=f"pdf/{country}__{doc_type}__{slug}.pdf"))
    return pd.DataFrame(rows)


def pdf_pages(path):
    out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True).stdout
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    return int(m.group(1)) if m else None


def fetch(row):
    path = OUT / row["file"]
    if path.exists() and path.stat().st_size > 0:
        return "cached"
    try:
        body, ctype = get(row["url"] + "/print")
    except Exception as e:
        return f"error: {e}"
    if not body.startswith(b"%PDF"):
        return f"not a pdf ({ctype})"
    path.write_bytes(body)
    return "downloaded"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    (OUT / "pdf").mkdir(parents=True, exist_ok=True)
    docs = list_documents()
    print(f"{len(docs)} documents in the sitemap, {docs['country'].nunique()} countries")

    with ThreadPoolExecutor(args.workers) as ex:
        docs["status"] = list(ex.map(fetch, docs.to_dict("records")))
    ok = docs["status"].isin(["cached", "downloaded"])
    docs["bytes"] = [(OUT / f).stat().st_size if o else None for f, o in zip(docs["file"], ok)]
    docs["pages"] = [pdf_pages(OUT / f) if o else None for f, o in zip(docs["file"], ok)]
    docs.to_csv(OUT / "manifest.csv", index=False)

    print(docs["status"].value_counts().to_string())
    print(f"{docs['pages'].sum():.0f} pages, {docs['bytes'].sum() / 1e6:.0f} MB -> {OUT}")
    for _, r in docs[~ok].iterrows():
        print(f"  FAILED {r['url']}: {r['status']}")


if __name__ == "__main__":
    main()
