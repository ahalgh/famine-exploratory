"""False-positive backtest of SMART triggers against observed FEWS NET transitions.

Ground-truth transition (Krishnamurthy R et al. 2022, Methods): the area-averaged IPC class changes by more
than 0.5 relative to the previous report and stays beyond that margin for at least two consecutive reports
(>150 days); a gradual same-direction drift that crosses the margin counts too, with onset at its first step.

A SMART signal is the onset of a triggered run (direction = predicted_change at onset). It is a true
positive if a transition in the same direction has its onset (first FEWS report showing the change) within
[onset + min_lead, onset + max_lead] days; otherwise a false positive. Signals too close to the end of the
FEWS record to be verified are dropped, as in the paper.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .loaders import load_fews, load_smart, load_soil_moisture
from .smart import compute_smart

# Area definitions: SMART soil region -> (country, FEWS livelihood zones or None for all zones).
AREAS = {
    "kenya_mandera2": ("Kenya", ["Mandera Riverine Zone", "Northeastern Pastoral Zone", "Northeastern Agropastoral Zone"]),
    "uganda_karamoja": ("Uganda", "Karamoja"),
    "malawi": ("Malawi", None),
    "nigeria": ("Nigeria", None),
    "kenya:national": ("Kenya", None),
    "uganda:national": ("Uganda", None),
    "malawi:national": ("Malawi", None),
    "nigeria:national": ("Nigeria", None),
}
# Price series per country = the staple used in the shipped SMART outputs.
PRICE_REGION = {"Kenya": "kenya_mandera2", "Uganda": "uganda_karamoja", "Malawi": "malawi", "Nigeria": "nigeria"}


def observed_ipc(area: str) -> pd.Series:
    country, zones = AREAS[area]
    f = load_fews()
    f = f[(f["area_type"] == "livelihood zone") & (f["country"] == country)]
    if isinstance(zones, str):
        f = f[f["region"].str.contains(zones)]
    elif zones is not None:
        f = f[f["region"].isin(zones)]
    return f.groupby("date")["ipc"].apply(lambda s: s.astype(int).mean()).sort_index()


def transitions(level: pd.Series, margin: float = 0.5, sustain: int = 2) -> pd.DataFrame:
    """Onsets of sustained IPC shifts. Returns date, direction ('worsen'/'improve'), size."""
    v, d = level.to_numpy(), level.index
    out, k = [], 1
    while k < len(v) - sustain + 1:
        base, step = v[k - 1], v[k] - v[k - 1]
        if step == 0:
            k += 1
            continue
        sign = np.sign(step)
        j = k
        # follow the monotone same-direction drift until the margin is crossed
        while j < len(v) and np.sign(v[j] - v[j - 1]) in (0, sign) and sign * (v[j] - base) <= margin:
            j += 1
        if j <= len(v) - sustain and all(sign * (v[j + s] - base) > margin for s in range(sustain)):
            out.append({"date": d[k], "direction": "worsen" if sign > 0 else "improve", "size": v[j] - base})
            k = j + sustain  # skip past this event
        else:
            k += 1
    return pd.DataFrame(out, columns=["date", "direction", "size"])


def smart_for_area(area: str, window: int, price_mode: str = "paper", realtime: bool = False) -> pd.DataFrame:
    country = AREAS[area][0]
    soil_region = "national" if area.endswith(":national") else area
    soil = load_soil_moisture()
    soil = soil[(soil["country"] == country) & (soil["region"] == soil_region)].set_index("date")["soil_moisture"]
    out = load_smart(120)
    price = out[out["region"] == PRICE_REGION[country]].set_index("date")["raw_price"]
    soil = soil[soil.index >= price.index.min()]
    df = compute_smart(soil, price, window, price_mode=price_mode)
    if realtime:  # threshold from past data only: c_first + (running max - c_first) / 2
        c = df["smart_coefficient"]
        c1 = c.dropna().iloc[0]
        df["smart_threshold"] = c1 + (c.cummax() - c1) / 2
        above = c > df["smart_threshold"]
        run = (above != above.shift()).cumsum()
        anchor = df["date"].shift().groupby(run).transform("first")
        df["days_above_threshold"] = (df["date"] - anchor).dt.days.where(above, 0).fillna(0).astype(int)
        df["triggered"] = df["days_above_threshold"] > 60
        df["predicted_change"] = np.where(df["triggered"], np.where(df["rolling_mean_slope"] > 0, "improve", "worsen"), "none")
    return df


def signals(df: pd.DataFrame) -> pd.DataFrame:
    on = df["triggered"] & ~df["triggered"].shift(fill_value=False)
    return df.loc[on, ["date", "predicted_change"]].rename(columns={"predicted_change": "direction"}).reset_index(drop=True)


@dataclass
class Score:
    signals: int
    tp: int
    fp: int
    events: int
    detected: int
    years: float

    @property
    def precision(self):
        return self.tp / self.signals if self.signals else np.nan

    @property
    def recall(self):
        return self.detected / self.events if self.events else np.nan


def score(sig: pd.DataFrame, ev: pd.DataFrame, fews_end: pd.Timestamp, min_lead=0, max_lead=180,
          span: tuple | None = None, directional=True) -> Score:
    sig = sig[sig["date"] + pd.Timedelta(days=max_lead) <= fews_end]
    hits = set()
    tp = 0
    for _, s in sig.iterrows():
        lo, hi = s["date"] + pd.Timedelta(days=min_lead), s["date"] + pd.Timedelta(days=max_lead)
        m = ev[(ev["date"] >= lo) & (ev["date"] <= hi)]
        if directional:
            m = m[m["direction"] == s["direction"]]
        if len(m):
            tp += 1
            hits.update(m.index)
    years = (span[1] - span[0]).days / 365.25 if span else np.nan
    return Score(len(sig), tp, len(sig) - tp, len(ev), len(hits), years)


def random_baseline(n_signals: int, dir_share_worsen: float, dates: pd.Series, ev: pd.DataFrame,
                    fews_end, n_sims=2000, seed=0, **kw) -> np.ndarray:
    """Precision of randomly timed signals (same count and direction mix) on the same eligible dates."""
    rng = np.random.default_rng(seed)
    elig = dates[dates + pd.Timedelta(days=kw.get("max_lead", 180)) <= fews_end].to_numpy()
    res = np.empty(n_sims)
    for i in range(n_sims):
        if n_signals == 0 or len(elig) == 0:
            res[i] = np.nan
            continue
        d = pd.to_datetime(rng.choice(elig, n_signals, replace=False))
        dirs = np.where(rng.random(n_signals) < dir_share_worsen, "worsen", "improve")
        res[i] = score(pd.DataFrame({"date": d, "direction": dirs}), ev, fews_end, **kw).tp
    return res
