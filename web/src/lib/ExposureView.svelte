<script>
  /**
   * Who depends on what: every food and income source in the FEWS NET livelihood profiles, ranked by how many
   * people would lose a meaningful part of their food or cash if that source fell by x%.
   * Arithmetic only (share × shock ≥ threshold), no model: it sizes the scope of each variable.
   * Data: scripts/export_exposure.py (Explore Livelihood dataset × WorldPop 2020).
   */
  let { exposure } = $props();

  const COUNTRIES = ['Kenya', 'Malawi', 'Nigeria', 'Uganda', 'Somalia', 'Guatemala'];
  const VARIABLES = [
    { d: 'food', k: 'purchase', label: 'Food bought at market', note: 'a fall in what cash buys: higher prices or lower income' },
    { d: 'food', k: 'own_crops', label: 'Own crop harvest' },
    { d: 'food', k: 'own_livestock', label: 'Own milk and meat' },
    { d: 'food', k: 'payment_in_kind', label: 'Food paid for work' },
    { d: 'food', k: 'food_aid', label: 'Food aid' },
    { d: 'food', k: 'gifts_other', label: 'Gifts and other food' },
    { d: 'food', k: 'wild_food_fishing_hunting', label: 'Wild food, fishing, hunting' },
    { d: 'income', k: 'agricultural_labor', label: 'Farm labour' },
    { d: 'income', k: 'other_casual_labor', label: 'Other casual labour' },
    { d: 'income', k: 'crop_sales', label: 'Crop sales' },
    { d: 'income', k: 'livestock_sales', label: 'Livestock sales' },
    { d: 'income', k: 'self_employment_trade', label: 'Self-employment and petty trade' },
    { d: 'income', k: 'natural_resources', label: 'Firewood, charcoal, grass' },
    { d: 'income', k: 'remittances', label: 'Remittances' },
    { d: 'income', k: 'formal_employment', label: 'Formal employment' },
    { d: 'income', k: 'transfers', label: 'Cash transfers' },
  ];
  const GROUPS = [
    { g: 'very poor', label: 'Very poor', color: 'var(--ramp-6)' },
    { g: 'poor', label: 'Poor', color: 'var(--ramp-5)' },
    { g: 'middle', label: 'Middle', color: 'var(--ramp-3)' },
    { g: 'better off', label: 'Better off', color: 'var(--ramp-2)' },
    { g: 'all', label: 'Zone average (no wealth split)', color: 'var(--faint)' },
  ];

  let scope = $state('all');
  let shock = $state(25);
  let threshold = $state(10);
  let selected = $state('food:purchase');
  let domainFilter = $state('both');

  const rows = $derived(exposure.rows.filter((r) => scope === 'all' || r.c === scope));
  const zones = $derived(exposure.zones.filter((z) => scope === 'all' || z.c === scope));
  const totals = $derived.by(() => {
    const cs = scope === 'all' ? COUNTRIES : [scope];
    const t = { population: 0, food: 0, income: 0 };
    for (const c of cs) for (const k in t) t[k] += exposure.countries[c][k];
    return t;
  });

  // share of a group's food needs (or cash income) from one source: [low, mid, high]; 0 where the breakdown
  // exists but omits the source; null where the group has no breakdown in that domain
  const share = (r, v) => (r[v.d] ? (r[v.d][v.k] ?? [0, 0, 0]) : null);

  const ranked = $derived.by(() => {
    const cut = threshold / (shock / 100); // share at which an x% fall costs at least the threshold
    return VARIABLES.filter((v) => domainFilter === 'both' || v.d === domainFilter)
      .map((v) => {
        const byGroup = Object.fromEntries(GROUPS.map((g) => [g.g, 0]));
        let low = 0, mid = 0, high = 0, lost = 0;
        const contrib = [];
        for (const r of rows) {
          const s = share(r, v);
          if (!s) continue;
          if (s[1] >= cut) { mid += r.p; byGroup[r.g] = (byGroup[r.g] ?? 0) + r.p; contrib.push({ ...r, s: s[1] }); }
          if ((s[0] ?? s[1]) >= cut) low += r.p;
          if ((s[2] ?? s[1]) >= cut) high += r.p;
          lost += r.p * (s[1] / 100) * (shock / 100);
        }
        return { ...v, key: `${v.d}:${v.k}`, mid, low, high, lost, byGroup, contrib, base: totals[v.d] };
      })
      .sort((a, b) => b.mid - a.mid || b.lost - a.lost);
  });
  const maxPeople = $derived(Math.max(1, ...ranked.map((r) => r.high)));
  const sel = $derived(ranked.find((r) => r.key === selected) ?? ranked[0]);
  const topZones = $derived.by(() => {
    if (!sel) return [];
    const byZone = new Map();
    for (const r of sel.contrib) {
      const z = byZone.get(r.fnid) ?? { zone: r.zone, c: r.c, p: 0, groups: [] };
      z.p += r.p; z.groups.push(`${r.g === 'all' ? 'zone average' : r.g} ${Math.round(r.s)}%`);
      byZone.set(r.fnid, z);
    }
    return [...byZone.values()].sort((a, b) => b.p - a.p).slice(0, 8);
  });

  // specific crops: the profiles give one pooled own-crop share per wealth group, not a share per crop. Each crop
  // gets the people in groups whose pooled own-crop share passes the threshold, in zones that list the crop as a
  // main crop: an upper bound per crop (the same people appear under every main crop of their zone)
  const OWN_CROPS = VARIABLES.find((v) => v.k === 'own_crops');
  const crops = $derived.by(() => {
    const cut = threshold / (shock / 100);
    const cropsByZone = new Map(zones.map((z) => [z.fnid, z.crops]));
    const m = new Map();
    for (const r of rows) {
      const s = share(r, OWN_CROPS);
      if (!s) continue;
      for (const crop of cropsByZone.get(r.fnid) ?? []) {
        const c = m.get(crop) ?? { crop, mid: 0, low: 0, high: 0, zones: new Set(), byGroup: {} };
        if (s[1] >= cut) { c.mid += r.p; c.byGroup[r.g] = (c.byGroup[r.g] ?? 0) + r.p; c.zones.add(r.fnid); }
        if ((s[0] ?? s[1]) >= cut) c.low += r.p;
        if ((s[2] ?? s[1]) >= cut) c.high += r.p;
        m.set(crop, c);
      }
    }
    return [...m.values()].filter((c) => c.high > 0).sort((a, b) => b.mid - a.mid || b.high - a.high).slice(0, 12);
  });
  const maxCrop = $derived(Math.max(1, ...crops.map((c) => c.high)));
  const cropCut = $derived(Math.min(100, Math.round(threshold / (shock / 100))));

  const M = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : `${n}`);
  const pct = (a, b) => (b ? `${Math.round((100 * a) / b)}%` : '–');
  const scopeName = $derived(scope === 'all' ? 'Six countries' : scope);
  const finding = $derived.by(() => {
    const top = ranked[0];
    if (!top || !top.mid) return `No source reaches the threshold at a ${shock}% fall.`;
    return `A ${shock}% fall in ${top.label.toLowerCase()} would cost ${M(top.mid)} people at least ${threshold}% of their ${top.d === 'food' ? 'food needs' : 'cash income'}.`;
  });
  const uncovered = $derived(totals.population - Math.max(totals.food, totals.income));
</script>

<section class="exposure" aria-labelledby="exposure-title">
  <header class="title-row">
    <div class="title">
      <h1 id="exposure-title">{scopeName}: who depends on what</h1>
      <p class="finding">{finding}</p>
    </div>
    <label class="scope">
      <span class="visually-hidden">Countries</span>
      <select bind:value={scope}>
        <option value="all">All six countries</option>
        {#each COUNTRIES as c}<option value={c}>{c}</option>{/each}
      </select>
    </label>
  </header>

  <div class="controls panel">
    <label class="slider">
      <span>Supply falls by <strong>{shock}%</strong></span>
      <input type="range" min="5" max="100" step="5" bind:value={shock} />
    </label>
    <label class="slider">
      <span>Counted when the loss is at least <strong>{threshold}%</strong> of food needs or cash income</span>
      <input type="range" min="5" max="50" step="5" bind:value={threshold} />
    </label>
    <div class="seg" role="radiogroup" aria-label="Sources">
      {#each [['both', 'All sources'], ['food', 'Food'], ['income', 'Income']] as [k, l]}
        <button role="radio" aria-checked={domainFilter === k} class:active={domainFilter === k} onclick={() => (domainFilter = k)}>{l}</button>
      {/each}
    </div>
  </div>

  <div class="body">
    <div class="panel list">
      <div class="legend" aria-label="Wealth groups">
        {#each GROUPS as g}<span><i style="background:{g.color}"></i>{g.label}</span>{/each}
        <span><i class="band"></i>Range from the reports' low–high readings</span>
      </div>
      {#each ranked as r (r.key)}
        <button class="row" class:active={sel?.key === r.key} onclick={() => (selected = r.key)}>
          <span class="name">{r.label}<small>{r.d === 'food' ? 'Food source' : 'Income source'}</small></span>
          <span class="bar" aria-hidden="true">
            {#each GROUPS as g}
              {#if r.byGroup[g.g]}<i style="width:{(100 * r.byGroup[g.g]) / maxPeople}%; background:{g.color}"></i>{/if}
            {/each}
            {#if r.high > r.low}<b class="whisker" style="left:{(100 * r.low) / maxPeople}%; width:{(100 * (r.high - r.low)) / maxPeople}%"></b>{/if}
          </span>
          <span class="num">{r.mid ? M(r.mid) : '–'}<small>{r.mid ? pct(r.mid, r.base) : ''}</small></span>
        </button>
      {/each}
      <p class="note">
        Percent is of the {M(totals.food)} people whose food sources are quantified (income: {M(totals.income)}).
        {#if uncovered > 0}{M(uncovered)} of {scopeName === 'Six countries' ? 'the six countries\'' : `${scope}'s`} {M(totals.population)} people
          live in zones without a quantified profile{scope === 'all' || scope === 'Uganda' ? ', including all of Uganda' : ''}.{/if}
      </p>
    </div>

    <aside class="panel detail">
      {#if sel}
        <h2>{sel.label}</h2>
        {#if sel.note}<p class="muted small">{sel.note}</p>{/if}
        <dl>
          <dt>People losing ≥ {threshold}%</dt><dd>{M(sel.mid)} <span class="muted">({M(sel.low)}–{M(sel.high)})</span></dd>
          <dt>Total {sel.d === 'food' ? 'food lost' : 'income lost'}</dt>
          <dd>{M(Math.round(sel.lost))} <span class="muted">{sel.d === 'food' ? 'people\'s full year of food' : 'people\'s full year of cash income'}</span></dd>
        </dl>
        <p class="muted small">
          A {shock}% fall in this source crosses the threshold for groups that get at least
          {Math.min(100, Math.round(threshold / (shock / 100)))}% of their {sel.d === 'food' ? 'food' : 'cash income'} from it.
        </p>
        {#if topZones.length}
          <h3>Largest zones</h3>
          <ol class="zones">
            {#each topZones as z}
              <li><span>{z.zone}<small>{scope === 'all' ? `${z.c} · ` : ''}{z.groups.join(', ')}</small></span><span class="num">{M(z.p)}</span></li>
            {/each}
          </ol>
        {/if}
      {/if}
    </aside>
  </div>

  <div class="panel crops">
    <header>
      <h2>Named crops: upper bound per crop</h2>
      <p class="muted small">
        People in wealth groups that get at least {cropCut}% of their food from their own harvest, in zones where the
        crop is a main crop. The profiles give one own-crop share for all crops together, so each bar assumes the
        whole harvest is that crop: a ceiling, and the same people appear under every main crop of their zone. Bars
        are not additive.
      </p>
    </header>
    {#each crops as c (c.crop)}
      <div class="crow">
        <span class="name"><span class="crop">{c.crop}</span><small>{c.zones.size} zone{c.zones.size === 1 ? '' : 's'}</small></span>
        <span class="bar" aria-hidden="true">
          {#each GROUPS as g}
            {#if c.byGroup[g.g]}<i style="width:{(100 * c.byGroup[g.g]) / maxCrop}%; background:{g.color}"></i>{/if}
          {/each}
          {#if c.high > c.low}<b class="whisker" style="left:{(100 * c.low) / maxCrop}%; width:{(100 * (c.high - c.low)) / maxCrop}%"></b>{/if}
        </span>
        <span class="num">{c.mid ? M(c.mid) : '–'}</span>
      </div>
    {:else}
      <p class="note">No group gets {cropCut}% of its food from its own harvest at these settings.</p>
    {/each}
  </div>

  <p class="note">
    Shares from FEWS NET livelihood zone profiles (reference years 2005–2024) via the Explore Livelihood dataset;
    people from WorldPop 2020. Arithmetic only: no substitution, coping or price feedback between sources.
  </p>
</section>

<style>
  .exposure { padding: var(--pad); display: grid; gap: var(--gap); align-content: start; max-width: 1400px; }
  .title-row { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
  .title { display: grid; gap: 6px; }
  h1 { font-size: var(--fs-title); line-height: 1.2; letter-spacing: -0.01em; }
  h2 { font-size: var(--fs-section); }
  h3 { font-size: var(--fs-body); margin-top: 8px; }
  .finding { color: var(--muted); font-size: 14px; max-width: 80ch; }
  .panel { background: var(--surface); border-radius: var(--radius-card); padding: 16px 20px; }
  select {
    height: var(--control-height); padding: 0 12px; border-radius: 999px; border: 1px solid var(--control);
    background: var(--surface); color: var(--text); font: inherit;
  }
  .controls { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr) auto; gap: 24px; align-items: end; }
  .slider { display: grid; gap: 8px; font-size: var(--fs-body); color: var(--muted); }
  .slider strong { color: var(--text); font-variant-numeric: tabular-nums; }
  input[type='range'] { width: 100%; accent-color: var(--accent); }
  .seg { display: inline-flex; border: 1px solid var(--control); border-radius: 999px; overflow: hidden; height: var(--control-height); }
  .seg button { padding: 0 14px; background: none; border: 0; color: var(--muted); font: inherit; font-size: var(--fs-body); cursor: pointer; }
  .seg button.active { background: var(--raised); color: var(--text); }

  .body { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: var(--gap); align-items: start; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: var(--fs-small); color: var(--muted); padding-bottom: 10px; }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .legend i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
  .legend i.band { height: 2px; background: var(--text); border-radius: 0; width: 14px; }
  .row, .crow {
    display: grid; grid-template-columns: minmax(150px, 220px) minmax(0, 1fr) 64px; gap: 16px; align-items: center;
    width: 100%; min-height: 40px; border: 0; border-top: 1px solid var(--rule); background: none; color: var(--text);
    font: inherit; font-size: var(--fs-body); text-align: left; padding: 4px 0;
  }
  .row { cursor: pointer; }
  .row:hover .name { color: var(--accent); }
  .row { position: relative; }
  .row.active { padding-left: 8px; }
  .row.active::before { content: ''; position: absolute; left: 0; top: 6px; bottom: 6px; width: 2px; background: var(--accent); }
  .name { display: grid; line-height: 1.3; }
  .name small { color: var(--faint); font-size: 11px; }
  .crow .crop { text-transform: capitalize; }
  .bar { position: relative; display: flex; height: 14px; background: var(--rule); border-radius: 2px; }
  .bar i { display: block; height: 100%; }
  .whisker { position: absolute; top: 50%; height: 2px; margin-top: -1px; background: var(--text); opacity: 0.55; }
  .num { text-align: right; font-variant-numeric: tabular-nums; display: grid; line-height: 1.3; }
  .num small { color: var(--faint); font-size: 11px; }
  .note { font-size: var(--fs-small); color: var(--muted); max-width: 90ch; padding-top: 10px; }

  .detail { display: grid; gap: 10px; position: sticky; top: var(--pad); }
  dl { display: grid; grid-template-columns: auto 1fr; gap: 6px 12px; font-size: var(--fs-body); }
  dt { color: var(--muted); }
  dd { margin: 0; font-variant-numeric: tabular-nums; }
  .muted { color: var(--muted); }
  .small { font-size: var(--fs-small); }
  .zones { list-style: none; padding: 0; margin: 0; display: grid; font-size: var(--fs-body); }
  .zones li { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-top: 1px solid var(--rule); }
  .zones li span:first-child { display: grid; }
  .zones small { color: var(--faint); font-size: 11px; }
  .crops header { display: grid; gap: 4px; padding-bottom: 8px; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

  @media (max-width: 900px) {
    .exposure { padding: 16px; }
    .title-row { flex-direction: column; }
    .controls { grid-template-columns: 1fr; gap: 16px; }
    .body { grid-template-columns: 1fr; }
    .detail { position: static; }
    .row, .crow { grid-template-columns: minmax(0, 1fr) 56px; row-gap: 4px; }
    .row .bar, .crow .bar { grid-column: 1 / -1; order: 3; }
  }
</style>
