<script>
  /**
   * Population affected when drought, conflict or flood moves six first-order variables (crop yield, livestock,
   * labour demand, wild food, market access, staple price), traced through each wealth group's food and income
   * shares from the FEWS NET livelihood profiles. Arithmetic only, no model; every step is shown in the zone panel.
   *
   * Per wealth group, everything in percent of annual food needs:
   *   direct     own harvest × crop fall + own milk/meat × livestock fall + food paid for work × labour fall
   *              + wild food × wild-food fall
   *   cash lost  Y = Σ income share × its fall   (crop sales: crop + market access; livestock sales: livestock +
   *              market access; farm and casual labour: labour demand; petty trade: market access)
   *   purchases  food bought × Y  (less cash)  +  food bought × (1 − Y) × p / (1 + p)  (higher staple price)
   *   loss L     direct + purchases
   * Households within a group vary: their losses are taken as spread evenly from 0.5L to 1.5L, so the share of
   * a group counted as affected (loss ≥ threshold) changes smoothly instead of all at once.
   */
  import ExposureMap, { BINS } from './ExposureMap.svelte';

  let { exposure, zonesGeo, country, dark, oncountry } = $props();

  const COUNTRIES = ['Kenya', 'Malawi', 'Nigeria', 'Uganda', 'Somalia', 'Guatemala'];
  const VARS = [
    { k: 'crop', label: 'Crop yield', verb: 'falls', color: 'var(--v1)' },
    { k: 'livestock', label: 'Livestock (milk, meat, sale value)', short: 'Livestock', verb: 'falls', color: 'var(--v2)' },
    { k: 'labour', label: 'Labour demand', verb: 'falls', color: 'var(--v3)' },
    { k: 'wild', label: 'Wild food', verb: 'falls', color: 'var(--v4)' },
    { k: 'market', label: 'Market access', verb: 'falls', color: 'var(--v5)' },
    { k: 'price', label: 'Staple price', verb: 'rises', color: 'var(--v6)' },
  ];
  const VAR = Object.fromEntries(VARS.map((v) => [v.k, v]));
  const SCENARIOS = {
    drought: { label: 'Drought', hazards: ['drought', 'erratic_rainfall'], x: { crop: 20, livestock: 10, labour: 20, wild: 10, market: 0, price: 20 } },
    conflict: { label: 'Conflict', hazards: ['conflict_insecurity', 'displacement', 'market_disruption'], x: { crop: 10, livestock: 10, labour: 10, wild: 0, market: 20, price: 20 } },
    flood: { label: 'Flood', hazards: ['flood', 'cyclone_hurricane'], x: { crop: 20, livestock: 0, labour: 10, wild: 0, market: 10, price: 10 } },
    all: { label: 'All zones', hazards: null, x: null },
  };
  const GROUP_ORDER = ['very poor', 'poor', 'middle', 'better off', 'all'];

  let scenario = $state('drought');
  let x = $state({ ...SCENARIOS.drought.x });
  let threshold = $state(10);
  let pickedZone = $state(null);
  let pickedGroup = $state(null);
  $effect(() => { country; pickedZone = null; pickedGroup = null; });
  function choose(key) {
    scenario = key;
    if (SCENARIOS[key].x) x = { ...SCENARIOS[key].x };
  }

  const rows = $derived(exposure.rows.filter((r) => r.c === country));
  const zones = $derived(exposure.zones.filter((z) => z.c === country));
  const population = $derived(exposure.countries[country].population);
  const hazardWords = { drought: 'drought', conflict: 'conflict', flood: 'floods' };

  // ---- the calculation, for one wealth group -------------------------------------------------
  function calc(r, xs = x) {
    const F = (k) => r.food?.[k]?.[1] ?? 0; // % of annual food needs
    const I = (k) => r.income?.[k]?.[1] ?? 0; // % of annual cash income
    const f = (k) => xs[k] / 100;
    const lines = [];
    const direct = (v, label, share) => share && xs[v] && lines.push({ v, kind: 'direct', label, share, change: xs[v], loss: share * f(v) });
    direct('crop', 'Own harvest', F('own_crops'));
    direct('livestock', 'Own milk and meat', F('own_livestock'));
    direct('labour', 'Food paid for work', F('payment_in_kind'));
    direct('wild', 'Wild food', F('wild_food_fishing_hunting'));

    const cash = [];
    const income = (v, label, share) => share && cash.push({ v, label, share, change: xs[v], lost: (share * f(v)) / 100 });
    if (r.income) {
      income('crop', 'Crop sales', I('crop_sales'));
      income('market', 'Crop sales (market access)', I('crop_sales'));
      income('livestock', 'Livestock sales', I('livestock_sales'));
      income('market', 'Livestock sales (market access)', I('livestock_sales'));
      income('labour', 'Farm and casual labour', I('agricultural_labor') + I('other_casual_labor'));
      income('market', 'Petty trade', I('self_employment_trade'));
    }
    const Y = Math.min(1, cash.reduce((a, c) => a + c.lost, 0));
    const bought = F('purchase');
    for (const c of cash) if (bought && c.change) lines.push({ v: c.v, kind: 'cash', label: `Less cash: ${c.label.toLowerCase()}`, share: c.share, change: c.change, bought, loss: bought * c.lost });
    const p = f('price');
    if (bought && p) lines.push({ v: 'price', kind: 'price', label: 'Food bought costs more', bought, Y, change: xs.price, loss: (bought * (1 - Y) * p) / (1 + p) });
    const L = lines.reduce((a, l) => a + l.loss, 0);
    const byVar = Object.fromEntries(VARS.map((v) => [v.k, 0]));
    for (const l of lines) byVar[l.v] += l.loss;
    return { lines, L, byVar, Y, bought, hasIncome: Boolean(r.income) };
  }
  // share of a group whose loss reaches the threshold, households spread evenly over 0.5L–1.5L
  const counted = (L) => (L <= 0 ? 0 : Math.min(1, Math.max(0, (1.5 * L - threshold) / L)));

  // ---- per zone and country --------------------------------------------------------------------
  const exposedZone = (z) => !SCENARIOS[scenario].hazards || z.hazards.some((h) => SCENARIOS[scenario].hazards.includes(h));
  const results = $derived.by(() => {
    const out = {};
    for (const z of zones) out[z.fnid] = { pop: z.p, hit: 0, known: false, exposed: exposedZone(z), pct: 0, groups: [] };
    for (const r of rows) {
      const z = out[r.fnid];
      if (!z || !r.food) continue;
      z.known = true;
      const c = calc(r);
      const share = z.exposed ? counted(c.L) : 0;
      z.groups.push({ ...r, ...c, share, people: r.p * share });
      z.hit += r.p * share;
    }
    for (const z of Object.values(out)) {
      z.pct = z.pop ? (100 * z.hit) / z.pop : 0;
      z.groups.sort((a, b) => GROUP_ORDER.indexOf(a.g) - GROUP_ORDER.indexOf(b.g));
    }
    return out;
  });
  const totalHit = $derived(Object.values(results).reduce((a, z) => a + z.hit, 0));
  const exposedZones = $derived(zones.filter((z) => results[z.fnid]?.exposed));
  const hasData = $derived(rows.some((r) => r.food));

  const zone = $derived.by(() => {
    const id = pickedZone ?? [...zones].sort((a, b) => (results[b.fnid]?.hit ?? 0) - (results[a.fnid]?.hit ?? 0))[0]?.fnid;
    return id ? { ...zones.find((z) => z.fnid === id), ...results[id] } : null;
  });
  const group = $derived(zone?.groups?.length ? (zone.groups.find((g) => g.group_index === pickedGroup?.i && g.g === pickedGroup?.g) ?? zone.groups[0]) : null);
  // x axis: a round maximum that fits the household range of every group and the threshold
  const tickStep = $derived.by(() => { const m = Math.max(threshold * 1.3, ...(zone?.groups ?? []).map((g) => g.L * 1.5), 5); return m <= 20 ? 5 : m <= 50 ? 10 : 20; });
  const scaleMax = $derived(Math.ceil(Math.max(threshold * 1.3, ...(zone?.groups ?? []).map((g) => g.L * 1.5), 5) / tickStep) * tickStep);
  const ticks = $derived(Array.from({ length: scaleMax / tickStep + 1 }, (_, i) => i * tickStep));
  const segments = (g) => VARS.reduce((acc, v) => {
    const w = (100 * g.byVar[v.k]) / scaleMax;
    if (w > 0) acc.push({ v, x: acc.length ? acc.at(-1).x + acc.at(-1).w : 0, w });
    return acc;
  }, []);

  // ---- across countries -----------------------------------------------------------------------
  const CROSS = ['Malawi', 'Guatemala', 'Somalia', 'Kenya', 'Nigeria'];
  const zoneById = Object.fromEntries(exposure.zones.map((z) => [z.fnid, z]));
  // share of all food lost, by cause, for the current scenario and dials
  const causeShares = $derived(CROSS.map((c) => {
    const by = Object.fromEntries(VARS.map((v) => [v.k, 0]));
    let hit = 0;
    for (const r of exposure.rows) {
      if (r.c !== c || !r.food || !exposedZone(zoneById[r.fnid])) continue;
      const res = calc(r);
      for (const v of VARS) by[v.k] += r.p * res.byVar[v.k];
      hit += r.p * counted(res.L);
    }
    const total = Object.values(by).reduce((a, b) => a + b, 0);
    return { c, hit, total, shares: VARS.map((v) => ({ v, pct: total ? (100 * by[v.k]) / total : 0 })) };
  }));
  // one dial at a time: a 10% move, people losing at least 5% of food needs, every zone
  const ONE_AT_A_TIME = { move: 10, cut: 5 };
  const single = $derived.by(() => {
    const out = {};
    for (const v of VARS) {
      const xs = Object.fromEntries(VARS.map((w) => [w.k, w.k === v.k ? ONE_AT_A_TIME.move : 0]));
      out[v.k] = Object.fromEntries(CROSS.map((c) => [c, 0]));
      for (const r of exposure.rows) {
        if (!r.food || !(r.c in out[v.k])) continue;
        const L = calc(r, xs).L;
        const share = L <= 0 ? 0 : Math.min(1, Math.max(0, (1.5 * L - ONE_AT_A_TIME.cut) / L));
        out[v.k][r.c] += r.p * share;
      }
    }
    return out;
  });
  const singleMax = $derived(Object.fromEntries(CROSS.map((c) => [c, Math.max(...VARS.map((v) => single[v.k][c]))])));

  const M = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)} million` : n >= 1e3 ? `${Math.round(n / 1e3).toLocaleString()},000` : `${Math.round(n)}`);
  const short = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : `${Math.round(n)}`);
  const n1 = (v) => (Math.abs(v) < 10 ? v.toFixed(1) : Math.round(v).toString());
  const groupName = (g) => (g.g === 'all' ? 'Whole zone' : g.label.replace(/^./, (c) => c.toUpperCase()));
</script>

<section class="exposure" aria-labelledby="exposure-title">
  <header class="title-row">
    <h1 id="exposure-title">Measuring impact of disaster on {country} population</h1>
    <select value={country} onchange={(e) => oncountry(e.currentTarget.value)} aria-label="Country">
      {#each COUNTRIES as c}<option value={c}>{c}</option>{/each}
    </select>
  </header>

  {#if !hasData}
    <div class="panel empty">
      <p>No quantified livelihood profiles for {country}. The FEWS NET profiles available for {country} describe zones
        without food or income shares.</p>
    </div>
  {:else}
    <div class="panel controls">
      <div class="seg" role="radiogroup" aria-label="Scenario">
        {#each Object.entries(SCENARIOS) as [k, s]}
          <button role="radio" aria-checked={scenario === k} class:active={scenario === k} onclick={() => choose(k)}>{s.label}</button>
        {/each}
      </div>
      <div class="vars">
        {#each VARS as v}
          <label class="var">
            <span class="vname"><i style="background:{v.color}"></i>{v.short ?? v.label} {v.verb} <strong>{x[v.k]}%</strong></span>
            <input type="range" min="0" max="25" step="1" bind:value={x[v.k]} style="accent-color:{v.color}" />
          </label>
        {/each}
        <label class="var threshold">
          <span class="vname">Affected: loses at least <strong>{threshold}%</strong> of annual food needs</span>
          <input type="range" min="1" max="25" step="1" bind:value={threshold} />
        </label>
      </div>
    </div>

    <div class="panel answer-panel">
      <p class="answer"><strong>{M(totalHit)}</strong> people affected in {country}</p>
      <p class="muted small">
        {Math.round((100 * totalHit) / population)}% of {M(population)}.
        {#if SCENARIOS[scenario].hazards}{SCENARIOS[scenario].label} applied to {exposedZones.length} of {zones.length} zones, those whose FEWS NET
          profile lists {hazardWords[scenario]}. Other zones are unshaded.{:else}Applied to all {zones.length} zones.{/if}
      </p>
    </div>

    <div class="body">
      <div class="map-card">
        <ExposureMap zones={zonesGeo} stats={results} {country} {dark} selected={zone?.fnid} onselect={(f) => { pickedZone = f; pickedGroup = null; }} />
        <div class="legend" aria-label="Population affected, percent of zone">
          <span class="legend-title">Population affected (% of zone)</span>
          {#each BINS as b}<span><i style="background:var({b.ramp})"></i>{b.label}</span>{/each}
          <span><i class="nodata"></i>No shares in profile</span>
          {#if SCENARIOS[scenario].hazards}<span><i class="unexposed"></i>Hazard not listed</span>{/if}
        </div>
      </div>

      <aside class="panel zone-panel">
        {#if zone}
          <header>
            <h2>{zone.zone}</h2>
            <p class="muted small">
              {M(zone.pop)} people{#if zone.exposed}, {M(zone.hit)} affected{:else}. Profile does not list {hazardWords[scenario]}{/if}.
              {#if !pickedZone}Largest affected zone. Select a zone on the map to change.{/if}
            </p>
          </header>

          {#if zone.groups.length}
            <div class="chart">
              <div class="chart-head">
                <h3>Food lost by wealth group</h3>
                <p class="muted small">Percent of annual food needs. A group whose bar passes the dashed line at {threshold}% is affected.</p>
              </div>
              <div class="chart-legend">
                {#each VARS as v}<span><i style="background:{v.color}"></i>{v.short ?? v.label}</span>{/each}
              </div>
              <div class="grid-head" aria-hidden="true">
                <span></span>
                <span class="ticks">
                  {#each ticks.filter((t) => Math.abs(t - threshold) > tickStep * 0.35) as t}<span style="left:{(100 * t) / scaleMax}%">{t}%</span>{/each}
                  <span class="thr-label" style="left:{(100 * threshold) / scaleMax}%">{threshold}%</span>
                </span>
                <span class="num">Affected</span>
              </div>
              {#each zone.groups as g}
                <button class="grow" class:active={group === g} onclick={() => (pickedGroup = { i: g.group_index, g: g.g })}
                  aria-label="{groupName(g)}: loses {n1(g.L)}% of food needs, {short(g.people)} of {short(g.p)} people affected">
                  <span class="gname">{groupName(g)}<small>{short(g.p)} people</small></span>
                  <span class="gplot">
                    <svg class="gbar" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true">
                      {#each ticks as t}<line class="tick" x1={(100 * t) / scaleMax} x2={(100 * t) / scaleMax} y1="0" y2="24" vector-effect="non-scaling-stroke" />{/each}
                      <line class="spread" x1={(50 * g.L) / scaleMax} x2={(150 * g.L) / scaleMax} y1="21" y2="21" vector-effect="non-scaling-stroke" />
                      {#each segments(g) as s}
                        <rect x={s.x} y="4" width={Math.max(0, s.w - 0.4)} height="13" fill={s.v.color}><title>{s.v.label}: {n1(g.byVar[s.v.k])}% of food needs</title></rect>
                      {/each}
                      <line class="thr" x1={(100 * threshold) / scaleMax} x2={(100 * threshold) / scaleMax} y1="0" y2="24" vector-effect="non-scaling-stroke" />
                    </svg>
                    <span class="bar-val" style="left:{Math.min(88, (100 * g.L) / scaleMax)}%">{n1(g.L)}%</span>
                  </span>
                  <span class="gval">{zone.exposed ? short(g.people) : '–'}<small>{zone.exposed ? `${Math.round(100 * g.share)}%` : ''}</small></span>
                </button>
              {/each}
              <p class="muted small">Grey line under each bar: assumed range across households in the group (0.5 to 1.5 times the group figure). Select a group for its calculation.</p>
            </div>

            {#if group}
              <div class="worked">
                <h3>Calculation for {groupName(group).toLowerCase()} {group.g === 'all' ? '' : 'households'}</h3>
                <table>
                  <thead><tr><th>Pathway</th><th class="num">Calculation</th><th class="num">Food lost</th></tr></thead>
                  <tbody>
                    {#each group.lines as l}
                      <tr>
                        <td><i class="dot" style="background:{VAR[l.v].color}"></i>{l.label}</td>
                        <td class="num calc">
                          {#if l.kind === 'direct'}{n1(l.share)}% of food × {l.change}%
                          {:else if l.kind === 'cash'}{n1(l.bought)}% bought × {n1(l.share)}% of cash × {l.change}%
                          {:else}{n1(l.bought)}% bought × {Math.round(100 * (1 - l.Y))}% cash left × {l.change}/{100 + l.change}{/if}
                        </td>
                        <td class="num">{n1(l.loss)}%</td>
                      </tr>
                    {:else}
                      <tr><td colspan="3" class="muted">No change at these settings.</td></tr>
                    {/each}
                  </tbody>
                  <tfoot>
                    <tr><td>Total</td><td></td><td class="num">{n1(group.L)}%</td></tr>
                  </tfoot>
                </table>
                <p class="muted small">
                  {#if !group.hasIncome}No income shares in this profile; cash losses are not included.{/if}
                  Household losses assumed to range from {n1(group.L * 0.5)}% to {n1(group.L * 1.5)}%.
                  {#if zone.exposed}{Math.round(100 * group.share)}% of households exceed {threshold}%: {short(group.people)} of {short(group.p)} people affected.{/if}
                </p>
              </div>
            {/if}
          {:else}
            <p class="muted small">No food or income shares in this zone's profile.</p>
          {/if}
        {/if}
      </aside>
    </div>
  {/if}

  <section class="panel across" aria-labelledby="across-title">
    <h2 id="across-title">Across countries</h2>
    <div class="across-grid">
      <div>
        <h3>Food lost by cause, {SCENARIOS[scenario].label.toLowerCase()} scenario</h3>
        <p class="muted small">Share of all food lost in each country under the current settings. The same disaster reaches people through different channels.</p>
        <div class="cause-legend">{#each VARS as v}<span><i style="background:{v.color}"></i>{v.short ?? v.label}</span>{/each}</div>
        {#each causeShares as r}
          <div class="crow">
            <span class="cname">{r.c}<small>{short(r.hit)} affected</small></span>
            <span class="stack" role="img" aria-label="{r.c}: {r.shares.filter((s) => s.pct >= 1).map((s) => `${s.v.short ?? s.v.label} ${Math.round(s.pct)}%`).join(', ')}">
              {#each r.shares as s}{#if s.pct > 0}<i style="width:{s.pct}%; background:{s.v.color}" title="{s.v.label}: {Math.round(s.pct)}%">{#if s.pct >= 12}<b>{Math.round(s.pct)}%</b>{/if}</i>{/if}{/each}
              {#if !r.total}<em class="muted">no zones list this hazard</em>{/if}
            </span>
          </div>
        {/each}
      </div>
      <div>
        <h3>Variable contributions</h3>
        <p class="muted small">People losing at least {ONE_AT_A_TIME.cut}% of food needs when one variable moves {ONE_AT_A_TIME.move}% in every zone. The largest in each country is in bold.</p>
        <table class="single">
          <thead><tr><th></th>{#each CROSS as c}<th class="num">{c}</th>{/each}</tr></thead>
          <tbody>
            {#each VARS as v}
              <tr>
                <td><i class="dot" style="background:{v.color}"></i>{v.short ?? v.label}</td>
                {#each CROSS as c}
                  <td class="num" class:top={single[v.k][c] > 0 && single[v.k][c] === singleMax[c]}>{single[v.k][c] >= 5e4 ? short(single[v.k][c]) : '–'}</td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <p class="note">
    Sources: FEWS NET livelihood zone profiles (reference years 2005–2024) via the Explore Livelihood dataset; WorldPop
    2020 population. Excludes switching between food sources, coping strategies, aid response and price gains to crop
    sellers. Purchases scale with cash income.
  </p>
</section>

<style>
  .exposure {
    --v1: #2a78d6; --v2: #eb6834; --v3: #1baf7a; --v4: #eda100; --v5: #e87ba4; --v6: #008300;
    padding: var(--pad); display: grid; gap: var(--gap); align-content: start; max-width: 1400px;
  }
  @media (prefers-color-scheme: dark) {
    :global(:root:where(:not([data-theme='light']))) .exposure { --v1: #3987e5; --v2: #d95926; --v3: #199e70; --v4: #c98500; --v5: #d55181; --v6: #0ca30c; }
  }
  :global(:root[data-theme='dark']) .exposure { --v1: #3987e5; --v2: #d95926; --v3: #199e70; --v4: #c98500; --v5: #d55181; --v6: #0ca30c; }

  .title-row { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
  h1 { font-size: var(--fs-title); line-height: 1.2; letter-spacing: -0.01em; }
  h2 { font-size: var(--fs-section); }
  h3 { font-size: var(--fs-body); }
  select {
    height: var(--control-height); padding: 0 12px; border-radius: 999px; border: 1px solid var(--control);
    background: var(--surface); color: var(--text); font: inherit;
  }
  .panel { background: var(--surface); border-radius: var(--radius-card); padding: 16px 20px; }
  .empty p { max-width: 70ch; }
  .muted { color: var(--muted); }
  .small { font-size: var(--fs-small); }
  .num { font-variant-numeric: tabular-nums; text-align: right; }

  .controls { display: grid; gap: 14px; }
  .seg { display: inline-flex; justify-self: start; border: 1px solid var(--control); border-radius: 999px; overflow: hidden; height: var(--control-height); }
  .seg button { padding: 0 16px; background: none; border: 0; color: var(--muted); font: inherit; font-size: var(--fs-body); cursor: pointer; }
  .seg button.active { background: var(--raised); color: var(--text); }
  .vars { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px 24px; }
  .var { display: grid; gap: 4px; font-size: var(--fs-body); }
  .vname { display: flex; align-items: center; gap: 8px; color: var(--muted); }
  .vname strong { color: var(--text); font-variant-numeric: tabular-nums; }
  .vname i { width: 10px; height: 10px; border-radius: 2px; flex: none; }
  .var input { width: 100%; }
  .threshold { grid-column: 1 / -1; max-width: 520px; }
  .threshold input { accent-color: var(--text); }

  .answer { font-size: 20px; line-height: 1.35; }
  .answer strong { font-variant-numeric: tabular-nums; }
  .answer-panel { display: grid; gap: 4px; }

  .body { display: grid; grid-template-columns: minmax(0, 1fr) 440px; gap: var(--gap); align-items: start; }
  .map-card { position: relative; height: min(78vh, 760px); background: var(--surface); border-radius: var(--radius-card); }
  .legend {
    position: absolute; left: 12px; top: 12px; display: grid; gap: 3px; padding: 8px 10px; border-radius: 4px;
    background: color-mix(in srgb, var(--surface) 92%, transparent); font-size: var(--fs-small);
  }
  .legend-title { color: var(--muted); }
  .legend span { display: inline-flex; align-items: center; gap: 8px; }
  .legend i { width: 14px; height: 10px; border-radius: 2px; display: inline-block; }
  .legend i.nodata { background: var(--raised); outline: 1px dashed var(--muted); outline-offset: -1px; }
  .legend i.unexposed { background: none; outline: 1px solid var(--zone-line); outline-offset: -1px; }

  .zone-panel { display: grid; gap: 14px; }
  .zone-panel header { display: grid; gap: 4px; }
  .chart { display: grid; gap: 2px; position: relative; }
  .chart-head { display: grid; gap: 2px; padding-bottom: 6px; }
  .chart-legend { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: var(--fs-small); color: var(--muted); padding-bottom: 8px; }
  .grid-head { display: grid; grid-template-columns: 96px minmax(0, 1fr) 64px; gap: 10px; font-size: 11px; color: var(--muted); padding: 0 4px; height: 16px; }
  .ticks { position: relative; }
  .ticks span { position: absolute; transform: translateX(-50%); }
  .ticks .thr-label { color: var(--text); font-weight: 650; }
  .gplot { position: relative; display: block; }
  .bar-val { position: absolute; top: 2px; margin-left: 6px; font-size: 11px; font-variant-numeric: tabular-nums; color: var(--text); pointer-events: none; }
  .chart-legend span { display: inline-flex; align-items: center; gap: 6px; }
  .chart-legend i { width: 10px; height: 10px; border-radius: 2px; }
  .grow {
    display: grid; grid-template-columns: 96px minmax(0, 1fr) 64px; gap: 10px; align-items: center; width: 100%;
    padding: 6px 4px; border: 0; border-top: 1px solid var(--rule); background: none; color: var(--text); font: inherit;
    font-size: var(--fs-body); text-align: left; cursor: pointer;
  }
  .grow.active { background: var(--raised); }
  .gname, .gval { display: grid; line-height: 1.25; }
  .gname small, .gval small { color: var(--faint); font-size: 11px; }
  .gval { text-align: right; font-variant-numeric: tabular-nums; }
  .gbar { width: 100%; height: 28px; display: block; overflow: visible; }
  .gbar .tick { stroke: var(--rule); stroke-width: 1; }
  .gbar rect { shape-rendering: crispEdges; }
  .gbar .thr { stroke: var(--text); stroke-width: 1.5; stroke-dasharray: 3 2; }
  .gbar .spread { stroke: var(--faint); stroke-width: 1.5; opacity: 0.7; }

  .worked { display: grid; gap: 8px; }
  table { width: 100%; border-collapse: collapse; font-size: var(--fs-body); }
  th { color: var(--muted); font-weight: 400; font-size: var(--fs-small); text-align: left; padding: 4px 0; }
  th.num { text-align: right; }
  td { padding: 6px 0; border-top: 1px solid var(--rule); vertical-align: top; }
  td.calc { color: var(--muted); font-size: var(--fs-small); padding-left: 8px; }
  tfoot td { font-weight: 650; border-top: 1px solid var(--border); }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 8px; }
  .note { font-size: var(--fs-small); color: var(--muted); max-width: 90ch; }

  @media (max-width: 1100px) {
    .body { grid-template-columns: 1fr; }
    .map-card { height: 60vh; }
  }
  @media (max-width: 700px) {
    .exposure { padding: 16px; }
    .title-row { flex-direction: column; align-items: flex-start; }
    .answer { font-size: 17px; }
  }
  .across { display: grid; gap: 12px; }
  .across-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 32px; }
  .across-grid > div { display: grid; gap: 8px; align-content: start; }
  .cause-legend { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: var(--fs-small); color: var(--muted); }
  .cause-legend span { display: inline-flex; align-items: center; gap: 6px; }
  .cause-legend i { width: 10px; height: 10px; border-radius: 2px; }
  .crow { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 12px; align-items: center; padding: 6px 0; border-top: 1px solid var(--rule); }
  .cname { display: grid; line-height: 1.25; font-size: var(--fs-body); }
  .cname small { color: var(--faint); font-size: 11px; }
  .stack { display: flex; gap: 2px; height: 22px; }
  .stack i { display: flex; align-items: center; justify-content: center; height: 100%; min-width: 0; }
  .stack b { font-size: 11px; font-weight: 600; font-style: normal; color: #111214; }
  .stack em { font-size: var(--fs-small); align-self: center; }
  .single td.top { font-weight: 650; }
  @media (max-width: 1100px) { .across-grid { grid-template-columns: 1fr; } }
</style>
