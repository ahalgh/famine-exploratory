"""Generate notebooks/eda.ipynb. Run: python scripts/build_eda_notebook.py && jupyter nbconvert --execute --inplace notebooks/eda.ipynb"""

from pathlib import Path

import nbformat as nbf

cells = []
md = lambda s: cells.append(nbf.v4.new_markdown_cell(s.strip()))
code = lambda s: cells.append(nbf.v4.new_code_cell(s.strip()))

md("""
# Famine early-warning: exploratory data analysis

Covers the **outputs** (FEWS NET Most-Likely projections `ml1`/`ml2` and the SMART soil-moisture trigger
at 80/120/180-observation windows) and the **inputs** feeding them (FEWS current situation, soil moisture,
FAO prices, ACLED conflict, World Bank CPI, admin boundaries). The full column-level data dictionary is in `FEATURES.md`.
""")
code("""
import sys; sys.path.insert(0, '..')
import numpy as np, pandas as pd, matplotlib.pyplot as plt, matplotlib.dates as mdates
import famine as fm
from famine.plotting import COUNTRY_COLORS, IPC_COLORS, CHANGE_COLORS, set_style, ipc_legend, facet
set_style(); pd.set_option('display.width', 200); pd.set_option('display.max_columns', 40)
data = fm.load_all()
""")

md("## 1. Inventory")
code("""
def summarize(name, df):
    dcol = next((c for c in ['date', 'issued', 'year'] if c in df), None)
    return dict(dataset=name, rows=len(df), cols=df.shape[1],
                start=df[dcol].min(), end=df[dcol].max(),
                countries=', '.join(sorted(df['country'].astype(str).unique())),
                n_regions=df['region'].nunique() if 'region' in df else None,
                null_cells=int(df.isna().sum().sum()))
pd.DataFrame([summarize(k, v) for k, v in data.items()]).set_index('dataset')
""")
code("""
# Country coverage: rows per dataset x country
cov = pd.DataFrame({k: v.groupby(v['country'].astype(str)).size() for k, v in data.items()}).reindex(fm.COUNTRIES).fillna(0).astype(int)
fig, ax = plt.subplots(figsize=(11, 3))
ax.imshow(np.log1p(cov.values), cmap='Blues', aspect='auto')
ax.set_xticks(range(cov.shape[1]), cov.columns, rotation=30, ha='right'); ax.set_yticks(range(len(cov)), cov.index)
for (i, j), v in np.ndenumerate(cov.values):
    ax.text(j, i, f'{v:,}' if v else '—', ha='center', va='center', fontsize=7.5, color='#0b0b0b' if v < 2000 else 'white')
ax.grid(False); ax.set_title('Rows per dataset and country (— = not covered)'); plt.show()
""")
md("""
**Coverage gaps:** Somalia appears only in soil moisture, prices (80 rows, one series) and conflict, with no IPC
labels or CPI. Guatemala has IPC data only for a single 2018-12 projection and one 2019-02 observation.
SMART covers Kenya, Malawi, Nigeria and Uganda, with one region each.
""")

md("## 2. Outputs: FEWS NET Most-Likely projections (ml1, ml2)")
code("""
ml = fm.load_ml_all()
ml.groupby(['horizon', 'country'], observed=True).agg(
    rows=('region', 'size'), zones=('region', 'nunique'), issues=('issued', 'nunique'),
    first_issue=('issued', 'min'), last_issue=('issued', 'max'),
    mean_lead_days=('lead_days', 'mean'), mean_window_days=('window_days', 'mean'),
    share_ipc3plus=('predicted_ipc', lambda s: (s.astype(int) >= 3).mean().round(3))).round(1)
""")
code("""
fig, axes = plt.subplots(1, 2, figsize=(12, 3))
for ax, (h, g) in zip(axes, ml.groupby('horizon')):
    ax.hist([g['lead_days'], g['window_days']], bins=20, label=['lead (valid_from − issued)', 'window length'], color=['#2a78d6', '#eb6834'], rwidth=0.9)
    ax.set_title(f'{h}: lead time & validity window (days)'); ax.legend()
plt.show()
""")
md("`ml1` always starts on the issue date (lead 0) and covers 1–4 months. `ml2` starts 1–4 months later, right where the matching ml1 window ends.")
code("""
# Share of zones in each predicted IPC phase over time (by valid_from), per country
for h in ['ml1', 'ml2']:
    g = ml[(ml.horizon == h) & (ml.country != 'Guatemala')]
    cs = sorted(g.country.astype(str).unique())
    fig, axs = facet(len(cs), ncols=2, w=6.2, h=2.4, sharey=True)
    for ax, c in zip(axs, cs):
        sh = pd.crosstab(g[g.country == c].valid_from, g[g.country == c].predicted_ipc, normalize='index')
        ax.stackplot(sh.index, sh.T.values, colors=[IPC_COLORS[p] for p in sh.columns], step='post', edgecolor='#fcfcfb', linewidth=0.3)
        ax.set_title(f'{h} · {c}: share of zones by predicted phase'); ax.set_ylim(0, 1); ax.grid(False)
    fig.tight_layout(); ipc_legend(fig, loc='lower center', bbox_to_anchor=(0.5, 1.0), ncol=4); plt.show()
""")

md("### 2a. Projection skill against observed FEWS current situation")
code("""
pairs = {h: fm.ml_vs_observed(h) for h in ['ml1', 'ml2']}
def skill(m):
    p, o = m.predicted_ipc.astype(int), m.ipc.astype(int)
    return pd.Series(dict(pairs=len(m), exact=(p == o).mean(), within_1=((p - o).abs() <= 1).mean(),
        mean_error=(p - o).mean(), over=(p > o).mean(), under=(p < o).mean(),
        ipc3plus_recall=((p >= 3) & (o >= 3)).sum() / max((o >= 3).sum(), 1),
        ipc3plus_precision=((p >= 3) & (o >= 3)).sum() / max((p >= 3).sum(), 1)))
pd.concat({h: m.groupby('country', observed=True).apply(skill, include_groups=False).assign() for h, m in pairs.items()}).round(3)
""")
code("""
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
for ax, (h, m) in zip(axes, pairs.items()):
    cm = pd.crosstab(m.ipc.astype(int), m.predicted_ipc.astype(int), normalize='index')
    ax.imshow(cm.values, cmap='Blues', vmin=0, vmax=1); ax.grid(False)
    ax.set_xticks(range(cm.shape[1]), cm.columns); ax.set_yticks(range(cm.shape[0]), cm.index)
    ax.set_xlabel('predicted IPC'); ax.set_ylabel('observed IPC'); ax.set_title(f'{h}: row-normalised confusion (n={len(m):,})')
    for (i, j), v in np.ndenumerate(cm.values):
        ax.text(j, i, f'{v:.0%}', ha='center', va='center', color='white' if v > .5 else '#0b0b0b', fontsize=8)
fig.tight_layout(); plt.show()
""")
code("""
# How does ml2 skill degrade with lead time?
m = pairs['ml2'].assign(lead_m=lambda d: (d.lead_days / 30.4).round().astype(int))
m.groupby('lead_m').apply(lambda g: pd.Series(dict(n=len(g), exact=(g.error == 0).mean(), bias=g.error.mean())), include_groups=False).round(3)
""")
code("""
# Consistency: when ml1 and ml2 cover the same zone & valid_from, do they agree?
k = ['country', 'region', 'valid_from']
both = ml[ml.horizon == 'ml1'].merge(ml[ml.horizon == 'ml2'], on=k, suffixes=('_ml1', '_ml2'))
both['revision'] = both.predicted_ipc_ml1.astype(int) - both.predicted_ipc_ml2.astype(int)
print(f'{len(both):,} matched zone-periods; agreement {(both.revision == 0).mean():.1%}')
both.revision.value_counts().sort_index().rename('ml1 − ml2 (later revision)')
""")

md("## 3. Outputs: SMART soil-moisture trigger")
md("""
Each `smart_{w}_day.csv` shares the same base columns (`date, country, region, soil_moisture, raw_price,
real_price_2025`). Only the derived columns change with the window. Behaviour checked against the data:
- `rolling_mean`, `variance`, `rolling_mean_slope` and `smart_coefficient` are null for the first **w−1 observations** of each region, so the window counts observations, not days.
- `triggered` is True **iff `days_above_threshold` > 60**: the coefficient has stayed above `smart_threshold` for more than 60 consecutive calendar days.
- `predicted_change` is `none` when not triggered. When triggered it is `improve` if `rolling_mean_slope` > 0 (soil getting wetter) and `worsen` if the slope is < 0.
- `smart_threshold` is one constant per region × window.
""")
code("""
smart = fm.load_smart_all()
smart.groupby(['window', 'region'], observed=True).agg(
    obs=('date', 'size'), start=('date', 'min'), end=('date', 'max'),
    median_gap_days=('date', lambda d: d.diff().dt.days.median()),
    threshold=('smart_threshold', 'first'), coef_median=('smart_coefficient', 'median'),
    share_above=('above_threshold', 'mean'), share_triggered=('triggered', 'mean'),
    n_worsen=('predicted_change', lambda s: (s == 'worsen').sum()),
    n_improve=('predicted_change', lambda s: (s == 'improve').sum())).round(3)
""")
code("""
# Check the stated rules hold
for w, g in smart.groupby('window'):
    rule_trig = (g.days_above_threshold > 60) == g.triggered
    rule_dir = np.where(~g.triggered, 'none', np.where(g.rolling_mean_slope > 0, 'improve', 'worsen')) == g.predicted_change.astype(str)
    print(f'window {w}: trigger rule holds {rule_trig.mean():.2%}, direction rule holds {rule_dir.mean():.2%}')
""")
code("""
# Coefficient vs threshold through time, triggered periods shaded (120-obs window)
s = smart[smart.window == 120]
regions = list(s.region.cat.categories)
fig, axs = facet(len(regions), ncols=1, w=12, h=2.3, sharex=True)
for ax, r in zip(axs, regions):
    g = s[s.region == r]; c = COUNTRY_COLORS[str(g.country.iloc[0])]
    ax.plot(g.date, g.smart_coefficient, color=c, lw=1.4)
    ax.axhline(g.smart_threshold.iloc[0], color='#52514e', ls='--', lw=1)
    for ch, col in [('worsen', CHANGE_COLORS['worsen']), ('improve', CHANGE_COLORS['improve'])]:
        ax.fill_between(g.date, 0, 1, where=g.predicted_change == ch, color=col, alpha=0.15, transform=ax.get_xaxis_transform(), step='post', lw=0)
    ax.set_title(f'{r}: smart_coefficient (line) vs threshold (dashed); shaded = triggered (red worsen / blue improve)')
fig.tight_layout(); plt.show()
""")
code("""
# Trigger episodes (contiguous triggered runs) per region and window
def episodes(g):
    run = (g.triggered != g.triggered.shift()).cumsum()
    e = g[g.triggered].groupby(run).agg(start=('date', 'min'), end=('date', 'max'), change=('predicted_change', 'first'))
    return e.assign(days=(e.end - e.start).dt.days)
ep = smart.groupby(['window', 'region'], observed=True).apply(episodes, include_groups=False).reset_index(level=-1, drop=True).reset_index()
ep.groupby(['window', 'region'], observed=True).agg(episodes=('start', 'size'), median_days=('days', 'median'),
    worsen=('change', lambda s: (s == 'worsen').sum()), improve=('change', lambda s: (s == 'improve').sum()))
""")
code("""
# How often do the three windows agree on a given date?
wide = smart.pivot_table(index=['region', 'date'], columns='window', values='predicted_change', aggfunc='first', observed=True).dropna()
print('all three windows agree:', f'{(wide.nunique(axis=1) == 1).mean():.1%}')
pd.crosstab(wide[80], wide[180], rownames=['80'], colnames=['180'])
""")
code("""
# SMART triggers vs country-level FEWS deterioration: share of zones in projected IPC3+ (ml1) per country
ipc3 = (ml[ml.horizon == 'ml1'].assign(p3=lambda d: d.predicted_ipc.astype(int) >= 3)
        .groupby(['country', 'issued'], observed=True).p3.mean().rename('share_ipc3plus').reset_index())
fig, axs = facet(len(regions), ncols=1, w=12, h=2.1, sharex=True)
for ax, r in zip(axs, regions):
    g = s[s.region == r]; c = str(g.country.iloc[0])
    q = ipc3[ipc3.country == c]
    ax.step(q.issued, q.share_ipc3plus, where='post', color=COUNTRY_COLORS[c])
    ax.fill_between(g.date, 0, 1, where=g.predicted_change == 'worsen', color=CHANGE_COLORS['worsen'], alpha=.15, transform=ax.get_xaxis_transform(), lw=0)
    ax.fill_between(g.date, 0, 1, where=g.predicted_change == 'improve', color=CHANGE_COLORS['improve'], alpha=.15, transform=ax.get_xaxis_transform(), lw=0)
    ax.set_ylim(0, 1); ax.set_title(f'{c}: share of zones projected IPC3+ (ml1) with SMART-120 trigger periods for {r}')
fig.tight_layout(); plt.show()
""")
md("These are country-level comparisons only. Each SMART region is a single sub-national area, and FEWS livelihood zones do not map onto it directly.")

md("## 4. Inputs")
code("""
fews = data['fews']
print(fews.groupby(['country', 'area_type'], observed=True).agg(rows=('ipc', 'size'), regions=('region', 'nunique'), dates=('date', 'nunique'), first=('date', 'min'), last=('date', 'max')))
pd.crosstab(fews.country, fews.ipc.astype(int), normalize='index').round(3)
""")
code("""
sm = data['soil_moisture']
nat = sm[sm.region == 'national'].assign(month=lambda d: d.date.dt.month)
fig, axes = plt.subplots(1, 2, figsize=(12, 3.2))
for c, g in nat.groupby('country', observed=True):
    g2 = g.set_index('date').soil_moisture.resample('MS').mean()
    axes[0].plot(g2.index, g2, color=COUNTRY_COLORS[c], label=c, lw=1.2)
    clim = g.groupby('month').soil_moisture.mean(); axes[1].plot(clim.index, clim, color=COUNTRY_COLORS[c], marker='o', ms=4, label=c)
axes[0].set_title('National soil moisture, monthly mean (m³/m³)'); axes[1].set_title('Seasonal climatology by month')
axes[1].legend(ncol=2, fontsize=7.5); fig.tight_layout(); plt.show()
sm.groupby(['country', 'region'], observed=True).agg(obs=('date', 'size'), median_cells=('valid_cells', 'median'), mean_sm=('soil_moisture', 'mean')).round(3).T
""")
code("""
pr = data['prices']
print(pr.groupby(['country', 'price_type'], observed=True).agg(series=('commodity', lambda s: s.nunique()), markets=('region', 'nunique'), rows=('raw_price', 'size')))
# Real price index (first 12 months = 100) for the staple series used by SMART
staples = {'Kenya': ('Nairobi', 'Maize meal'), 'Malawi': ('Lunzu', 'Maize'), 'Nigeria': ('North East', 'Rice (imported)'), 'Uganda': ('National Average', 'Cassava (flour)')}
fig, ax = plt.subplots(figsize=(12, 3.2))
for c, (r, com) in staples.items():
    g = pr[(pr.country == c) & (pr.region == r) & (pr.commodity == com) & (pr.price_type == 'Retail')].set_index('date')[fm.REAL_PRICE].sort_index()
    ax.plot(g.index, 100 * g / g.iloc[:12].mean(), color=COUNTRY_COLORS[c], label=f'{c}: {com}, {r}')
ax.axhline(100, color='#52514e', lw=.8); ax.set_title('Real (2025) staple price index, 2019 = 100'); ax.legend(fontsize=7.5); plt.show()
""")
code("""
cf = data['conflict_monthly']
fig, axes = plt.subplots(1, 2, figsize=(12, 3.2))
for c, g in cf.groupby('country', observed=True):
    axes[0].plot(g.date, g.conflict_index, color=COUNTRY_COLORS[c], label=c, lw=1.2)
    axes[1].plot(g.date, g.political_violence_fatalities.rolling(3).mean(), color=COUNTRY_COLORS[c], lw=1.2)
axes[0].set_title('ACLED monthly conflict_index'); axes[1].set_title('Political-violence fatalities (3-mo mean)'); axes[0].legend(ncol=3, fontsize=7.5)
fig.tight_layout(); plt.show()
cf.drop(columns='date').groupby('country', observed=True).corr().round(2).xs('conflict_index', level=1)
""")
code("""
data['conflict_annual'].dropna(subset=['index_level'])[['year', 'country', 'conflict_index', 'index_level', 'index_ranking']]
""")
code("""
cpi = data['cpi'].pivot(index='year', columns='country', values='cpi')
(cpi.pct_change() * 100).round(1).rename_axis(columns='YoY inflation %')
""")
code("""
# Admin boundary coverage and joinability of IPC region names
regs = fm.load_regions()
print(regs.groupby(['country', 'layer']).size().unstack())
keys = set(zip(regs.country, regs.region_key))
fews.assign(joins=[(c, k) in keys for c, k in zip(fews.country.astype(str), fews.region_key)]).groupby(['country', 'area_type'], observed=True).joins.mean().round(3)
""")

md("## 5. Data-quality notes")
code("""
notes = []
pr_null = pr[pr[fm.REAL_PRICE].isna()]
notes.append(f'prices: {len(pr_null)} rows missing real_price_2025, all in {sorted(pr_null.country.astype(str).unique())} (no CPI for Somalia)')
notes.append(f"prices: raw_price spans {pr.raw_price.min():,.0f}–{pr.raw_price.max():,.0f}. Units vary ({pr.unit.nunique()} units, e.g. NGN/100 kg vs NGN/Kg), so normalise before comparing across series")
z = cf[cf.conflict_index == 0]; notes.append(f'conflict: {len(z)} months with conflict_index == 0 ({sorted(z.country.astype(str).unique())})')
notes.append(f"conflict_annual: index_level/index_ranking only populated for 2023–2025; index_ranking null for Malawi 2023–24")
notes.append(f"soil moisture: region == 'national' and region == '<country>' are distinct series (median valid_cells {sm[sm.region=='national'].valid_cells.median():.0f} vs far fewer), so don't treat them as duplicates")
notes.append(f'fews: area_type == "country" rows (one per country, {len(fews[fews.area_type=="country"])} total, 2023+) have region == country name and no ml1/ml2 counterpart')
notes.append('ml/fews: livelihood-zone names have no geometry in data/regions; only Guatemala districts join (316/323 after accent normalisation)')
notes.append('smart: files labelled *_day use an observation-count window. Observations are irregular (~2–3 day gaps)')
notes.append('dates extend to 2026-09; check whether recent rows are provisional')
print('\\n'.join('• ' + n for n in notes))
""")

nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})
out = Path(__file__).resolve().parents[1] / "notebooks" / "eda.ipynb"
out.parent.mkdir(exist_ok=True)
nbf.write(nb, out)
print("wrote", out)
