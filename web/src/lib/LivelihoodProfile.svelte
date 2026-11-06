<script>
  /**
   * The selected zone's FEWS NET livelihood profile: what people live on, when the hungry months are,
   * and how food and cash income split by wealth group. Values come from scripts/export_livelihood.py;
   * a "≈" marks a share estimated from the report's chart rather than written in its text.
   */
  let { profile } = $props();

  const MONTHS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];
  const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const SEASONS = [['rainy', 'Rains'], ['harvest', 'Main harvest'], ['lean', 'Lean season'], ['labor', 'Labour demand']];

  const FOOD = {
    own_crops: 'Own crops', own_livestock: 'Own livestock', purchase: 'Purchase', payment_in_kind: 'Payment in kind',
    wild_food_fishing_hunting: 'Wild food, fishing', food_aid: 'Food aid', gifts_other: 'Gifts, other',
  };
  const INCOME = {
    crop_sales: 'Crop sales', livestock_sales: 'Livestock sales', agricultural_labor: 'Farm labour',
    other_casual_labor: 'Other casual labour', formal_employment: 'Wage employment', remittances: 'Remittances',
    self_employment_trade: 'Trade, small business', natural_resources: 'Natural resources', transfers: 'Transfers',
  };
  const GROUP = { 'very poor': 'Very poor', poor: 'Poor', middle: 'Middle', 'better off': 'Better off', all: 'All' };
  const words = (s) => s.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase());
  // a comma list in sentence case; the catch-all 'other' carries no information on its own
  const list = (all) => {
    const xs = (all ?? []).filter((x) => x !== 'other');
    return xs.length ? words(xs.join(', ').replaceAll('_', ' ').toLowerCase()) : '—';
  };
  const range = ([lo, hi], unit = '') => (lo == null && hi == null ? '—' : lo === hi || hi == null ? `${lo}${unit}` : `${lo}–${hi}${unit}`);

  const groups = $derived(profile.groups);
  // a source row appears if any group reports it; rows sorted by the poorest group's share
  function rows(kind, labels) {
    const keys = Object.keys(labels).filter((k) => groups.some((g) => g[kind][k]));
    const first = groups[0]?.[kind] ?? {};
    return keys.sort((a, b) => (first[b]?.[0] ?? -1) - (first[a]?.[0] ?? -1)).map((k) => ({ key: k, label: labels[k] }));
  }
  const foodRows = $derived(rows('food', FOOD));
  const incomeRows = $derived(rows('income', INCOME));

  const cell = (v) => (v ? `background: color-mix(in srgb, var(--ramp-4) ${Math.round(Math.min(100, v[0]) * 0.55)}%, transparent)` : '');
  const cellText = (v) => (!v ? '—' : v[0] === 0 ? '0%' : `${v[1] === 'chart_visual' ? '≈' : ''}${Math.round(v[0])}%`);
  const pages = $derived(profile.source.pages[0] === profile.source.pages[1] ? `p. ${profile.source.pages[0]}` : `pp. ${profile.source.pages.join('–')}`);
  const docDate = $derived(profile.source.date.replace(/-\d$/, '').replace(/^./, (c) => c.toUpperCase()).replace('-', ' '));
</script>

<section class="lh" aria-labelledby="lh-title">
  <div class="lh-head">
    <h3 id="lh-title">Livelihood profile</h3>
    <a class="muted small" href={profile.source.url} target="_blank" rel="noopener">FEWS NET {profile.source.type}, {docDate}, {pages}</a>
  </div>

  <dl class="kv">
    <dt>System</dt><dd>{words(profile.system)}</dd>
    <dt>Main crops</dt><dd class="wrap">{list(profile.crops)}</dd>
    {#if profile.livestock?.length}<dt>Livestock</dt><dd class="wrap">{list(profile.livestock)}</dd>{/if}
    <dt>Rainfall</dt><dd>{range(profile.rainfall_mm, ' mm')}</dd>
    <dt>Labour migration</dt><dd>{words(profile.migration)}</dd>
    <dt>Market access</dt><dd>{words(profile.market_access)}</dd>
  </dl>

  <div class="cal" role="table" aria-label="Seasonal calendar">
    <div class="cal-row" role="row">
      <span role="columnheader"></span>
      {#each MONTHS as m, i}<span class="cal-m muted" role="columnheader" title={MONTH_NAMES[i]}>{m}</span>{/each}
    </div>
    {#each SEASONS as [key, label]}
      {@const on = new Set(profile.months[key])}
      <div class="cal-row" role="row">
        <span class="cal-label" role="rowheader">{label}</span>
        {#each MONTHS as _, i}
          <i role="cell" class:on={on.has(i + 1)} title="{label}, {MONTH_NAMES[i]}: {on.has(i + 1) ? 'yes' : 'no'}"></i>
        {/each}
      </div>
    {/each}
  </div>

  {#if groups.length}
    {#each [['food', 'Food sources', '% of annual food needs', foodRows], ['income', 'Cash income', '% of annual cash income', incomeRows]] as [kind, title, unit, rs]}
      {#if rs.length}
        <table class="shares">
          <caption><span>{title}</span> <span class="muted">{unit}</span></caption>
          <thead>
            <tr><th></th>{#each groups as g, i}<th class="num">{profile.group_labels?.[i] ?? GROUP[g.group]}</th>{/each}</tr>
          </thead>
          <tbody>
            {#each rs as r}
              <tr>
                <td>{r.label}</td>
                {#each groups as g}<td class="num" style={cell(g[kind][r.key])}>{cellText(g[kind][r.key])}</td>{/each}
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    {/each}
    <table class="shares">
      <caption><span>Wealth groups</span></caption>
      <thead><tr><th></th>{#each groups as g, i}<th class="num">{profile.group_labels?.[i] ?? GROUP[g.group]}</th>{/each}</tr></thead>
      <tbody>
        <tr><td>Households</td>{#each groups as g}<td class="num">{range(g.households_pct, '%')}</td>{/each}</tr>
        <tr><td>Household size</td>{#each groups as g}<td class="num">{g.size ?? '—'}</td>{/each}</tr>
        <tr><td>Land farmed</td>{#each groups as g}<td class="num">{g.land_ha == null ? '—' : `${g.land_ha} ha`}</td>{/each}</tr>
        <tr><td>Months of own staple</td>{#each groups as g}<td class="num">{g.staple_months ?? '—'}</td>{/each}</tr>
      </tbody>
    </table>
  {/if}

  <dl class="kv">
    <dt>Hazards</dt><dd class="wrap">{list(profile.hazards)}</dd>
    {#if profile.chronic?.length}<dt>Frequent</dt><dd class="wrap">{list(profile.chronic)}</dd>{/if}
    <dt>Coping</dt><dd class="wrap">{list(profile.coping)}</dd>
  </dl>
</section>

<style>
  .lh { display: grid; gap: 12px; padding-top: 14px; border-top: 1px solid var(--rule); }
  .lh-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  .lh-head h3 { font-size: var(--fs-body); font-weight: 600; }
  .lh-head a { text-decoration: none; }
  .lh-head a:hover { color: var(--text); text-decoration: underline; }
  .small { font-size: var(--fs-small); }
  .kv { display: grid; grid-template-columns: auto 1fr; gap: 6px 12px; margin: 0; }
  .kv dt { color: var(--muted); }
  .kv dd { margin: 0; text-align: right; }
  .wrap { white-space: normal; }

  .cal { display: grid; gap: 2px; }
  .cal-row { display: grid; grid-template-columns: 92px repeat(12, minmax(0, 1fr)); gap: 2px; align-items: center; }
  .cal-m { font-size: 11px; text-align: center; }
  .cal-label { font-size: var(--fs-small); color: var(--muted); }
  .cal i { height: 10px; border-radius: 1px; background: var(--ramp-0); }
  .cal i.on { background: var(--ramp-4); }

  .shares { width: 100%; border-collapse: collapse; font-size: var(--fs-small); }
  .shares caption { text-align: left; padding-bottom: 6px; font-size: var(--fs-small); }
  .shares caption span:first-child { font-weight: 600; color: var(--text); }
  .shares th { font-weight: 400; color: var(--muted); padding: 0 0 4px 6px; }
  .shares td { padding: 4px 0; border-top: 1px solid var(--rule); }
  .shares td.num, .shares th.num { text-align: right; padding-left: 6px; padding-right: 4px; }
</style>
