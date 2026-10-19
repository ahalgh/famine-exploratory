"""Validate the MAP 2019 friction surface against market integration.

If the surface captures real access, pairs of markets that are closer in travel time should have more
strongly co-moving prices. For each country:

    1. staple = staple-grain/pulse series (commodity x unit x price type) with the most WFP markets
       having >= 24 months of prices since 2019. Rows flagged 'aggregate' are kept: they are
       market-level monthly averages of that market's own observations, and most recent WFP data
       carries that flag. Forecasts, if present, are dropped.
    2. monthly log price per market; subtract the cross-market mean each month (removes national
       inflation and shared shocks, leaving local deviations); take first differences
    3. price co-movement for each market pair = Pearson correlation of those differences
       (pairs with >= 18 overlapping months)
    4. travel time between markets (motorized cost distance) and great-circle distance
    5. Mantel tests (999 permutations of market labels; pairs are not independent):
       co-movement vs log travel time, vs log distance, and vs travel time after removing distance

Outputs
    reports/access_validation_pairs.csv     one row per market pair
    reports/access_validation_summary.csv   one row per country x test
    reports/figures/access_validation.png

Run: python scripts/validate_access_prices.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import famine as fm
from famine.access import CostGrid
from famine.plotting import COUNTRY_COLORS, set_style

MIN_MONTHS, MIN_OVERLAP, N_PERM = 24, 18, 999
STAPLES = r"maize|sorghum|millet|rice|beans|cassava|wheat"
rng = np.random.default_rng(0)


def staple_panel(prices: pd.DataFrame):
    flag = prices["priceflag"].astype(str)
    staple = prices["commodity"].astype(str).str.contains(STAPLES, case=False)
    p = prices[staple & ~flag.str.contains("forecast") & (prices["date"] >= "2019-01-01")].copy()
    p["month"] = p["date"].dt.to_period("M")
    p["series"] = p["commodity"].astype(str) + " | " + p["unit"].astype(str) + " | " + p["pricetype"].astype(str)
    months = p.groupby(["series", "market_id"])["month"].nunique()
    good = months[months >= MIN_MONTHS].reset_index()
    if good.empty:
        return None, None
    series = good.groupby("series").size().idxmax()
    keep = good.loc[good["series"] == series, "market_id"]
    q = p[(p["series"] == series) & p["market_id"].isin(keep)]
    wide = q.groupby(["month", "market_id"])["price"].median().unstack().sort_index()
    return series, np.log(wide)


def comovement(logp: pd.DataFrame) -> pd.DataFrame:
    local = logp.sub(logp.mean(axis=1), axis=0)  # remove national/common component each month
    d = local.diff()
    return d.corr(min_periods=MIN_OVERLAP)


def haversine_km(lat, lon):
    la, lo = np.radians(lat)[:, None], np.radians(lon)[:, None]
    a = np.sin((la - la.T) / 2) ** 2 + np.cos(la) * np.cos(la.T) * np.sin((lo - lo.T) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def mantel(y, x, n_perm=N_PERM):
    """Pearson r between upper triangles of two square matrices; permutation p-value (two-sided)."""
    iu = np.triu_indices_from(y, 1)
    ok = np.isfinite(y[iu]) & np.isfinite(x[iu])
    r0 = np.corrcoef(y[iu][ok], x[iu][ok])[0, 1]
    n, hits = y.shape[0], 0
    for _ in range(n_perm):
        perm = rng.permutation(n)
        yp = y[np.ix_(perm, perm)][iu]
        okp = np.isfinite(yp) & np.isfinite(x[iu])
        hits += abs(np.corrcoef(yp[okp], x[iu][okp])[0, 1]) >= abs(r0)
    return r0, (hits + 1) / (n_perm + 1), int(ok.sum())


def residualize(x, z):
    """Residual of x on z (upper-triangle regression), returned as a square matrix."""
    iu = np.triu_indices_from(x, 1)
    ok = np.isfinite(x[iu]) & np.isfinite(z[iu])
    b = np.polyfit(z[iu][ok], x[iu][ok], 1)
    r = np.full_like(x, np.nan)
    r[iu] = x[iu] - np.polyval(b, z[iu])
    r.T[iu] = r[iu]
    return r


def main():
    prices = fm.load_wfp_prices()
    markets = fm.load_wfp_markets().set_index("market_id")
    countries = fm.load_regions(layer="country").set_index("country")
    pairs, summary = [], []

    for country in fm.COUNTRIES:
        series, logp = staple_panel(prices[prices["country"] == country])
        if logp is None or logp.shape[1] < 8:
            print(f"{country}: too few markets with long series, skipped")
            continue
        ids = [m for m in logp.columns if m in markets.index]
        logp = logp[ids]
        mk = markets.loc[ids]
        grid = CostGrid(countries.loc[country, "geometry"], "motorized")
        px = [grid.pixel(x, y) for x, y in zip(mk["longitude"], mk["latitude"])]
        tt = np.full((len(ids), len(ids)), np.nan)
        for i, s in enumerate(px):
            if s is None:
                continue
            surf = grid.travel_time([s])
            tt[i] = [surf[p] if p is not None else np.nan for p in px]
        tt = (tt + tt.T) / 2 / 60  # hours, symmetrised
        dist = haversine_km(mk["latitude"].to_numpy(), mk["longitude"].to_numpy())
        co = comovement(logp).to_numpy()
        np.fill_diagonal(tt, np.nan); np.fill_diagonal(dist, np.nan)

        ltt, ldist = np.log1p(tt), np.log1p(dist)
        tests = {
            "co-movement vs log travel time": (co, ltt),
            "co-movement vs log distance": (co, ldist),
            "co-movement vs travel time beyond distance": (residualize(co, ldist), residualize(ltt, ldist)),
        }
        print(f"{country}: {series}, {len(ids)} markets")
        for name, (y, x) in tests.items():
            r, p, n = mantel(y, x)
            summary.append(dict(country=country, staple=series, markets=len(ids), pairs=n, test=name, mantel_r=round(r, 3), p=round(p, 3)))
            print(f"   {name:45s} r={r:+.3f}  p={p:.3f}  pairs={n}")
        iu = np.triu_indices(len(ids), 1)
        pairs.append(pd.DataFrame(dict(country=country, staple=series, market_a=mk.iloc[iu[0]]["market"].values,
                                       market_b=mk.iloc[iu[1]]["market"].values, travel_h=tt[iu], distance_km=dist[iu],
                                       comovement=co[iu])).dropna())

    pairs = pd.concat(pairs, ignore_index=True)
    summary = pd.DataFrame(summary)
    pairs.to_csv(ROOT / "reports/access_validation_pairs.csv", index=False)
    summary.to_csv(ROOT / "reports/access_validation_summary.csv", index=False)

    set_style()
    fig, axes = plt.subplots(1, 2, figsize=(12, 3.8), sharey=True)
    for ax, (col, label) in zip(axes, [("travel_h", "Travel time between markets (hours, log scale)"),
                                       ("distance_km", "Straight-line distance (km, log scale)")]):
        for c, g in pairs.groupby("country"):
            bins = np.unique(np.quantile(g[col], np.linspace(0, 1, 9)))
            b = pd.cut(g[col], bins, include_lowest=True)
            m = g.groupby(b, observed=True).agg(x=(col, "median"), y=("comovement", "mean"))
            ax.plot(m["x"], m["y"], marker="o", ms=4, color=COUNTRY_COLORS[c], label=c)
        ax.set_xscale("log"); ax.set_xlabel(label); ax.axhline(0, color="#52514e", lw=0.8)
    axes[0].set_ylabel("Mean price co-movement\n(corr. of local monthly changes)")
    axes[0].set_title("Market price co-movement by travel time")
    axes[1].set_title("… and by straight-line distance")
    axes[0].legend(fontsize=8)
    fig.tight_layout()
    (ROOT / "reports/figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(ROOT / "reports/figures/access_validation.png", dpi=150)
    print("\nwrote reports/access_validation_{pairs,summary}.csv and reports/figures/access_validation.png")


if __name__ == "__main__":
    main()
