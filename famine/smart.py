"""Re-implementation of SMART (Soil Moisture Auto-Regressive Threshold).

Krishnamurthy R et al., "Anticipating drought-related food security changes",
Nature Sustainability 5, 956-964 (2022), https://doi.org/10.1038/s41893-022-00962-0

Two variants are provided:
- ``price_mode="ratio"`` reproduces the shipped ``smart_*_day.csv`` outputs, which scale AR(1) by
  price / first price in the series (reverse-engineered; matches 90-100% of rows to 1e-5).
- ``price_mode="paper"`` follows Eq. 2 of the paper: AR(1) * ln|p| / (1 + ln|p|).

Pipeline (per region):
    ar1            lag-1 autocorrelation of soil moisture over a rolling window of `window` lag pairs (Eq. 1)
    coefficient    ar1 * price_factor                                                      (Eq. 2)
    threshold      c_first + (c_max - c_first) / 2  (uses the whole series => look-ahead)   (Eq. 3)
    days_above     calendar days since the observation before the current above-threshold run
    triggered      days_above > persistence_days (60)
    rolling_mean   mean of soil moisture over `window` observations
    slope          OLS slope per day of rolling_mean over the trailing `slope_days` (60) calendar days
    predicted_change  'improve' if slope > 0 else 'worsen' when triggered, otherwise 'none'
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .loaders import CHANGE_DTYPE, load_smart, load_soil_moisture


def price_factor(price: pd.Series, mode: str = "ratio") -> pd.Series:
    if mode == "ratio":
        return price / price.iloc[0]
    if mode == "paper":
        lp = np.log(price.abs())
        return lp / (1 + lp)
    if mode == "none":
        return pd.Series(1.0, index=price.index)
    raise ValueError("mode must be 'ratio', 'paper' or 'none'")


def _trailing_slope(dates: pd.Series, y: pd.Series, days: int, min_points: int = 3) -> pd.Series:
    x = (dates - dates.iloc[0]).dt.days.to_numpy(float)
    v = y.to_numpy(float)
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        sel = (x > x[i] - days) & (x <= x[i]) & ~np.isnan(v)
        if sel.sum() >= min_points:
            out[i] = np.polyfit(x[sel], v[sel], 1)[0]
    return pd.Series(out, index=y.index)


def compute_smart(soil: pd.Series, price: pd.Series, window: int = 120, *, price_mode: str = "ratio",
                  persistence_days: int = 60, slope_days: int = 60, threshold: float | None = None,
                  output_dates: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Run SMART for one region.

    soil:  soil-moisture series indexed by date (the full series; AR(1) is computed on all of it).
    price: price series indexed by date; forward-filled onto soil dates.
    output_dates: restrict output rows (e.g. to dates where a price exists), after AR(1) is computed.
    threshold: fixed threshold; default is Eq. 3 computed from this run (in-sample, look-ahead).
    """
    soil = soil.sort_index().astype(float)
    ar1 = soil.rolling(window).corr(soil.shift(1))
    rmean = soil.rolling(window).mean()
    rstd = soil.rolling(window).std()

    df = pd.DataFrame({"soil_moisture": soil, "ar1": ar1, "rolling_mean": rmean, "rolling_std": rstd})
    if output_dates is not None:
        df = df.reindex(output_dates)
    df.index.name = "date"
    df = df.reset_index()
    p = price.sort_index()
    df["price"] = pd.merge_asof(df[["date"]], p.rename("price").reset_index().rename(columns={p.index.name or "index": "date"}),
                                on="date", direction="backward")["price"]
    df = df.dropna(subset=["price"]).reset_index(drop=True)

    df["smart_coefficient"] = df["ar1"] * price_factor(df["price"], price_mode)
    c = df["smart_coefficient"].dropna()
    df["smart_threshold"] = threshold if threshold is not None else c.iloc[0] + (c.max() - c.iloc[0]) / 2

    above = df["smart_coefficient"] > df["smart_threshold"]
    run = (above != above.shift()).cumsum()
    run_anchor = df["date"].shift().groupby(run).transform("first")
    df["days_above_threshold"] = (df["date"] - run_anchor).dt.days.where(above, 0).fillna(0).astype(int)
    df["triggered"] = df["days_above_threshold"] > persistence_days

    df["rolling_mean_slope"] = _trailing_slope(df["date"], df["rolling_mean"], slope_days)
    direction = np.where(df["rolling_mean_slope"] > 0, "improve", "worsen")
    df["predicted_change"] = pd.Series(np.where(df["triggered"], direction, "none")).astype(CHANGE_DTYPE)
    return df


def rebuild_from_outputs(window: int, region: str, price_mode: str = "ratio", **kw) -> pd.DataFrame:
    """Recompute SMART for a region using the full soil series and the price column of the shipped output."""
    out = load_smart(window)
    out = out[out["region"] == region]
    soil = load_soil_moisture()
    soil = soil[soil["region"] == region].set_index("date")["soil_moisture"]
    price = out.set_index("date")["raw_price"]
    return compute_smart(soil, price, window, price_mode=price_mode,
                         output_dates=pd.DatetimeIndex(out["date"]), **kw)


def validate(window: int, region: str) -> dict:
    """Share of rows where the rebuild matches the shipped output, per column."""
    ref = load_smart(window)
    ref = ref[ref["region"] == region].reset_index(drop=True)
    new = rebuild_from_outputs(window, region)
    assert (ref["date"].values == new["date"].values).all()

    def close(a, b, tol):
        m = a.notna() | b.notna()
        return float(((a - b).abs() < tol)[m].mean()) if m.any() else 1.0

    return {
        "rolling_mean": close(ref["rolling_mean"], new["rolling_mean"], 1e-5),
        "variance(=std)": close(ref["variance"], new["rolling_std"], 1e-5),
        "smart_coefficient": close(ref["smart_coefficient"], new["smart_coefficient"], 2e-5),
        "smart_threshold": close(ref["smart_threshold"], new["smart_threshold"], 1e-5),
        "days_above_threshold": float((ref["days_above_threshold"] == new["days_above_threshold"]).mean()),
        "rolling_mean_slope": close(ref["rolling_mean_slope"], new["rolling_mean_slope"], 1e-7),
        "triggered": float((ref["triggered"] == new["triggered"]).mean()),
        "predicted_change": float((ref["predicted_change"].astype(str) == new["predicted_change"].astype(str)).mean()),
    }
