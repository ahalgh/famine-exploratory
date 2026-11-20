<script>
  /**
   * Who is impacted when drought, conflict or flood moves six first-order variables (crop yield, livestock,
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
   * a group counted as impacted (loss ≥ threshold) changes smoothly instead of all at once.
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
    all: { label: 'Any zone', hazards: null, x: null },
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
  function calc(r) {
    const F = (k) => r.food?.[k]?.[1] ?? 0; // % of annual food needs
    const I = (k) => r.income?.[k]?.[1] ?? 0; // % of annual cash income
    const f = (k) => x[k] / 100;
    const lines = [];
    const direct = (v, label, share) => share && x[v] && lines.push({ v, kind: 'direct', label, share, change: x[v], loss: share * f(v) });
    direct('crop', 'Own harvest', F('own_crops'));
    direct('livestock', 'Own milk and meat', F('own_livestock'));
    direct('labour', 'Food paid for work', F('payment_in_kind'));
    direct('wild', 'Wild food', F('wild_food_fishing_hunting'));

    const cash = [];
    const income = (v, label, share) => share && cash.push({ v, label, share, change: x[v], lost: (share * f(v)) / 100 });
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
    if (bought && p) lines.push({ v: 'price', kind: 'price', label: 'Food bought costs more', bought, Y, change: x.price, loss: (bought * (1 - Y) * p) / (1 + p) });
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
  const scaleMax = $derived(Math.max(threshold * 1.4, ...(zone?.groups ?? []).map((g) => g.L * 1.5), 5));

  const M = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)} million` : n >= 1e3 ? `${Math.round(n / 1e3).toLocaleString()},000` : `${Math.round(n)}`);
  const short = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : `${Math.round(n)}`);
  const n1 = (v) => (Math.abs(v) < 10 ? v.toFixed(1) : Math.round(v).toString());
  const groupName = (g) => (g.g === 'all' ? 'Whole zone' : g.label.replace(/^./, (c) => c.toUpperCase()));
</script>

<section class="exposure" aria-labelledby="exposure-title">
  <header class="title-row">
    <h1 id="exposure-title">{country}: who is impacted by drought, conflict or flood</h1>
    <select value={country} onchange={(e) => oncountry(e.currentTarget.value)} aria-label="Country">
      {#each COUNTRIES as c}<option value={c}>{c}</option>{/each}
    </select>
  </header>

  {#if !hasData}
    <div class="panel empty">
      <p>None of {country}'s livelihood zone profiles quantify where households get their food or income, so there is
        nothing to calculate for {country}. Its profiles describe the zones in words only.</p>
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
          <span class="vname">Count people who lose at least <strong>{threshold}%</strong> of their food needs</span>
          <input type="range" min="1" max="25" step="1" bind:value={threshold} />
        </label>
      </div>
    </div>

    <div class="panel answer-panel">
      <p class="answer"><strong>{M(totalHit)}</strong> people in {country} lose at least {threshold}% of their food needs.</p>
      <p class="muted small">
        {Math.round((100 * totalHit) / population)}% of {country}'s {short(population)} people.
        {#if SCENARIOS[scenario].hazards}Counted only in the {exposedZones.length} of {zones.length} zones whose profile lists
          {hazardWords[scenario]} as a hazard (the others are left blank on the map).{:else}Applied to every zone.{/if}
      </p>
    </div>

    <div class="body">
      <div class="map-card">
        <ExposureMap zones={zonesGeo} stats={results} {country} {dark} selected={zone?.fnid} onselect={(f) => { pickedZone = f; pickedGroup = null; }} />
        <div class="legend" aria-label="Share of each zone's people impacted">
          <span class="legend-title">Share of the zone's people impacted</span>
          {#each BINS as b}<span><i style="background:var({b.ramp})"></i>{b.label}</span>{/each}
          <span><i class="nodata"></i>No breakdown in profile</span>
          {#if SCENARIOS[scenario].hazards}<span><i class="unexposed"></i>Hazard not listed</span>{/if}
        </div>
      </div>

      <aside class="panel zone-panel">
        {#if zone}
          <header>
            <h2>{zone.zone}</h2>
            <p class="muted small">{short(zone.pop)} people · {zone.exposed ? `${short(zone.hit)} impacted` : `profile doesn't list ${hazardWords[scenario]}`}{pickedZone ? '' : ' · zone with the most people impacted; click the map for another'}</p>
          </header>

          {#if zone.groups.length}
            <div class="chart" role="img" aria-label="Food needs lost by each wealth group, split by cause">
              <div class="chart-legend">
                {#each VARS as v}<span><i style="background:{v.color}"></i>{v.short ?? v.label}</span>{/each}
                <span><i class="leg-spread"></i>Range across households</span>
                <span><i class="leg-thr"></i>Threshold</span>
              </div>
              {#each zone.groups as g}
                <button class="grow" class:active={group === g} onclick={() => (pickedGroup = { i: g.group_index, g: g.g })}>
                  <span class="gname">{groupName(g)}<small>{short(g.p)} people</small></span>
                  <svg class="gbar" viewBox="0 0 100 20" preserveAspectRatio="none" aria-hidden="true">
                    <line class="spread" x1={(50 * g.L) / scaleMax} x2={(150 * g.L) / scaleMax} y1="17.5" y2="17.5" vector-effect="non-scaling-stroke" />
                    {#each VARS.reduce((acc, v) => { const w = (100 * g.byVar[v.k]) / scaleMax; if (w > 0) acc.push({ v, x: acc.length ? acc.at(-1).x + acc.at(-1).w : 0, w }); return acc; }, []) as s}
                      <rect x={s.x} y="3" width={Math.max(0, s.w - 0.4)} height="11" fill={s.v.color}><title>{s.v.label}: {n1(g.byVar[s.v.k])}% of food needs</title></rect>
                    {/each}
                    <line class="thr" x1={(100 * threshold) / scaleMax} x2={(100 * threshold) / scaleMax} y1="0" y2="20" vector-effect="non-scaling-stroke" />
                  </svg>
                  <span class="gval">{n1(g.L)}%<small>{zone.exposed ? `${Math.round(100 * g.share)}% counted` : '–'}</small></span>
                </button>
              {/each}
              <p class="axis muted"><span>0</span><span class="thr-label" style="left:calc({(100 * threshold) / scaleMax}% )">threshold {threshold}%</span><span>{Math.round(scaleMax)}% of food needs</span></p>
            </div>

            {#if group}
              <div class="worked">
                <h3>{groupName(group)}: the calculation</h3>
                <table>
                  <thead><tr><th>Pathway</th><th class="num">Calculation</th><th class="num">Food needs lost</th></tr></thead>
                  <tbody>
                    {#each group.lines as l}
                      <tr>
                        <td><i class="dot" style="background:{VAR[l.v].color}"></i>{l.label}</td>
                        <td class="num calc">
                          {#if l.kind === 'direct'}{n1(l.share)}% of food × {l.change}%
                          {:else if l.kind === 'cash'}{n1(l.bought)}% bought × ({n1(l.share)}% of cash × {l.change}%)
                          {:else}{n1(l.bought)}% bought × {Math.round(100 * (1 - l.Y))}% cash left × {l.change}/{100 + l.change}{/if}
                        </td>
                        <td class="num">{n1(l.loss)}%</td>
                      </tr>
                    {:else}
                      <tr><td colspan="3" class="muted">None of this group's sources move with these settings.</td></tr>
                    {/each}
                  </tbody>
                  <tfoot>
                    <tr><td>Total</td><td></td><td class="num">{n1(group.L)}%</td></tr>
                  </tfoot>
                </table>
                <p class="muted small">
                  {#if !group.hasIncome}This profile gives no income breakdown for the group, so lost cash isn't counted.{/if}
                  Households in a group differ, so losses are taken as spread from {n1(group.L * 0.5)}% to {n1(group.L * 1.5)}%
                  (half to one and a half times {n1(group.L)}%).
                  {#if zone.exposed}{Math.round(100 * group.share)}% of them reach {threshold}%: {short(group.people)} of {short(group.p)} people counted.{/if}
                </p>
              </div>
            {/if}
          {:else}
            <p class="muted small">This zone's profile has no breakdown of food or income, so it can't be calculated.</p>
          {/if}
        {/if}
      </aside>
    </div>
  {/if}

  <p class="note">
    Shares from FEWS NET livelihood zone profiles (reference years 2005–2024) via the Explore Livelihood dataset;
    people from WorldPop 2020. Notional: no switching between sources, coping, aid response or gains to sellers from
    higher prices. Purchases are assumed to shrink in step with cash income.
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
  .chart-legend { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: var(--fs-small); color: var(--muted); padding-bottom: 6px; }
  .chart-legend span { display: inline-flex; align-items: center; gap: 6px; }
  .chart-legend i { width: 10px; height: 10px; border-radius: 2px; }
  .chart-legend i.leg-spread { height: 0; border-top: 1.5px solid var(--muted); border-radius: 0; width: 14px; }
  .chart-legend i.leg-thr { width: 0; height: 12px; border-left: 1.5px dashed var(--text); border-radius: 0; }
  .grow {
    display: grid; grid-template-columns: 96px minmax(0, 1fr) 64px; gap: 10px; align-items: center; width: 100%;
    padding: 6px 4px; border: 0; border-top: 1px solid var(--rule); background: none; color: var(--text); font: inherit;
    font-size: var(--fs-body); text-align: left; cursor: pointer;
  }
  .grow.active { background: var(--raised); }
  .gname, .gval { display: grid; line-height: 1.25; }
  .gname small, .gval small { color: var(--faint); font-size: 11px; }
  .gval { text-align: right; font-variant-numeric: tabular-nums; }
  .gbar { width: 100%; height: 24px; display: block; overflow: visible; background: linear-gradient(var(--rule), var(--rule)) 0 3px / 100% 11px no-repeat; }
  .gbar rect { shape-rendering: crispEdges; }
  .gbar .thr { stroke: var(--text); stroke-width: 1.5; stroke-dasharray: 3 2; }
  .gbar .spread { stroke: var(--muted); stroke-width: 1.5; }
  .axis { position: relative; display: flex; justify-content: space-between; font-size: 11px; margin: 0 74px 0 106px; height: 16px; }
  .thr-label { position: absolute; transform: translateX(-50%); white-space: nowrap; color: var(--text); }

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
    .axis { margin: 0; }
  }
</style>
