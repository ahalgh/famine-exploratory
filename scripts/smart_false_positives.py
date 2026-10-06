"""Backtest SMART false positives on all areas with soil moisture + prices + FEWS ground truth."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from famine.backtest import AREAS, observed_ipc, transitions, smart_for_area, signals

LEADS = {"strict 0–180d, same direction": (0, 180, True), "lenient −60–270d, any direction": (-60, 270, False)}
rng = np.random.default_rng(0)

def hit_table(dates, dirs, ev, lo, hi, directional):
    """For each candidate (date, dir): is there an event in [date+lo, date+hi] (matching direction)?"""
    out = np.zeros(len(dates), bool)
    for i, (d, x) in enumerate(zip(dates, dirs)):
        m = ev[(ev.date >= d + pd.Timedelta(days=lo)) & (ev.date <= d + pd.Timedelta(days=hi))]
        if directional: m = m[m.direction == x]
        out[i] = len(m) > 0
    return out

rows, sig_rows = [], []
for window in [80, 100, 120, 180]:
    for price_mode in ["paper", "ratio"]:
        for realtime in [False, True]:
            for lead_name, (lo, hi, directional) in LEADS.items():
                tot = dict(signals=0, tp=0, events=0, detected=0, years=0.0); null_tp = np.zeros(2000)
                for area in AREAS:
                    obs = observed_ipc(area); ev = transitions(obs); end = obs.index.max()
                    df = smart_for_area(area, window, price_mode, realtime)
                    s = signals(df); s = s[s.date + pd.Timedelta(days=hi) <= end]
                    h = hit_table(s.date, s.direction, ev, lo, hi, directional)
                    # events detected (recall): any event preceded by a matching signal
                    det = sum(any(((e.date - sd).days >= lo) and ((e.date - sd).days <= hi) and (not directional or sx == e.direction)
                                  for sd, sx in zip(s.date, s.direction)) for e in ev[ev.date >= df.date[df.smart_coefficient.notna()].min()].itertuples())
                    ev_in = (ev.date >= df.date[df.smart_coefficient.notna()].min()).sum()
                    span_start = df.date[df.smart_coefficient.notna()].min(); span_end = end - pd.Timedelta(days=hi)
                    tot['signals'] += len(s); tot['tp'] += h.sum(); tot['events'] += ev_in; tot['detected'] += det
                    tot['years'] += max((span_end - span_start).days, 0) / 365.25
                    # null: same number of signals at random eligible SMART dates, random direction (50/50 or observed mix)
                    elig = df.loc[df.smart_coefficient.notna() & (df.date <= span_end), 'date'].reset_index(drop=True)
                    if len(s) and len(elig):
                        hw = hit_table(elig, ['worsen'] * len(elig), ev, lo, hi, directional)
                        hi_ = hit_table(elig, ['improve'] * len(elig), ev, lo, hi, directional)
                        pw = (s.direction == 'worsen').mean()
                        for k in range(2000):
                            idx = rng.choice(len(elig), len(s), replace=False)
                            dirw = rng.random(len(s)) < pw
                            null_tp[k] += np.where(dirw, hw[idx], hi_[idx]).sum()
                    if lead_name.startswith('strict') and window == 120:
                        for (d, x), ok in zip(s.itertuples(index=False), h):
                            sig_rows.append(dict(price_mode=price_mode, threshold='real-time' if realtime else 'in-sample', area=area, date=d.date(), direction=x, true_positive=bool(ok)))
                n, tp = tot['signals'], tot['tp']
                rows.append(dict(window=window, price=price_mode, threshold='real-time' if realtime else 'in-sample', match=lead_name,
                                 signals=n, TP=tp, FP=n - tp, precision=round(tp / n, 2) if n else np.nan,
                                 FP_per_area_year=round((n - tp) / tot['years'], 2), events=tot['events'], recall=round(tot['detected'] / tot['events'], 2) if tot['events'] else np.nan,
                                 random_TP_mean=round(null_tp.mean(), 1), p_vs_random=round((null_tp >= tp).mean(), 3) if n else np.nan))
res = pd.DataFrame(rows)
out = Path(__file__).resolve().parents[1] / 'reports'; out.mkdir(exist_ok=True)
res.to_csv(out / 'smart_false_positive_backtest.csv', index=False)
pd.DataFrame(sig_rows).to_csv(out / 'smart_signals_w120.csv', index=False)
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 100)
print(res.to_string(index=False))
