<script>
  /**
   * One country, one question: if a source of food or income falls by x%, who is hit, and where?
   * A person is hit when their wealth group loses at least hit% of its food needs (food sources) or of its cash
   * income (income sources): group share from the source × the fall ≥ hit. Arithmetic only, no model.
   * Data: scripts/export_exposure.py (Explore Livelihood dataset × WorldPop 2020).
   */
  import ExposureMap, { BINS } from './ExposureMap.svelte';

  let { exposure, zonesGeo, country, dark, oncountry } = $props();

  const COUNTRIES = ['Kenya', 'Malawi', 'Nigeria', 'Uganda', 'Somalia', 'Guatemala'];
  const SOURCES = [
    { d: 'food', k: 'purchase', label: 'Food bought at market', fall: 'what their cash buys (prices up or income down)' },
    { d: 'food', k: 'own_crops', label: 'Own harvest' },
    { d: 'food', k: 'own_livestock', label: 'Own milk and meat' },
    { d: 'food', k: 'payment_in_kind', label: 'Food paid for work' },
    { d: 'food', k: 'food_aid', label: 'Food aid' },
    { d: 'food', k: 'gifts_other', label: 'Gifts of food' },
    { d: 'food', k: 'wild_food_fishing_hunting', label: 'Wild food and fishing' },
    { d: 'income', k: 'agricultural_labor', label: 'Farm labour' },
    { d: 'income', k: 'other_casual_labor', label: 'Other casual labour' },
    { d: 'income', k: 'crop_sales', label: 'Crop sales' },
    { d: 'income', k: 'livestock_sales', label: 'Livestock sales' },
    { d: 'income', k: 'self_employment_trade', label: 'Petty trade and small business' },
    { d: 'income', k: 'natural_resources', label: 'Firewood, charcoal, grass' },
    { d: 'income', k: 'remittances', label: 'Remittances' },
    { d: 'income', k: 'formal_employment', label: 'Salaried jobs' },
    { d: 'income', k: 'transfers', label: 'Cash transfers' },
  ];
  const GROUP_ORDER = ['very poor', 'poor', 'middle', 'better off', 'all'];

  let sourceKey = $state(null); // null = the source that hits the most people
  let shock = $state(25); // size of the fall, percent (1–25: notional)
  let hit = $state(10); // loss that counts as hit, percent of food needs or cash income (1–25)
  let selectedZone = $state(null);
  $effect(() => { country; selectedZone = null; sourceKey = null; });

  const source = $derived(SOURCES.find((s) => `${s.d}:${s.k}` === sourceKey));
  const rows = $derived(exposure.rows.filter((r) => r.c === country));
  const zones = $derived(exposure.zones.filter((z) => z.c === country));
  const population = $derived(exposure.countries[country].population);

  // a group's share (mid, percent) from a source; 0 where its breakdown omits the source; null without a breakdown
  const shareOf = (r, s) => (r[s.d] ? (r[s.d][s.k]?.[1] ?? 0) : null);
  const isHit = (share) => share !== null && (share * shock) / 100 >= hit;

  function peopleHit(s) {
    let n = 0;
    for (const r of rows) if (isHit(shareOf(r, s))) n += r.p;
    return n;
  }
  const ranked = $derived(
    SOURCES.map((s) => ({ ...s, key: `${s.d}:${s.k}`, hit: peopleHit(s) }))
      .filter((s) => rows.some((r) => r[s.d]))
      .sort((a, b) => b.hit - a.hit),
  );
  const maxHit = $derived(Math.max(1, ...ranked.map((s) => s.hit)));
  const current = $derived(ranked.find((s) => s.key === sourceKey) ?? ranked[0]);

  // per zone: people hit and the share of the zone's people that is
  const zoneStats = $derived.by(() => {
    const out = {};
    for (const z of zones) out[z.fnid] = { pop: z.p, hit: 0, known: false, pct: 0 };
    if (!current) return out;
    for (const r of rows) {
      const s = shareOf(r, current);
      const z = out[r.fnid];
      if (!z || s === null) continue;
      z.known = true;
      if (isHit(s)) z.hit += r.p;
    }
    for (const z of Object.values(out)) z.pct = z.pop ? (100 * z.hit) / z.pop : 0;
    return out;
  });
  const totalHit = $derived(Object.values(zoneStats).reduce((a, z) => a + z.hit, 0));
  const knownPop = $derived(Object.values(zoneStats).reduce((a, z) => a + (z.known ? z.pop : 0), 0));
  const unknownPop = $derived(population - knownPop);

  const zone = $derived(selectedZone ? zones.find((z) => z.fnid === selectedZone) : null);
  const zoneGroups = $derived(
    zone && current
      ? rows.filter((r) => r.fnid === zone.fnid)
          .sort((a, b) => GROUP_ORDER.indexOf(a.g) - GROUP_ORDER.indexOf(b.g))
          .map((r) => { const s = shareOf(r, current); return { ...r, share: s, loss: s === null ? null : (s * shock) / 100 }; })
      : [],
  );

  const M = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)} million` : n >= 1e3 ? `${Math.round(n / 1e3)},000` : `${n}`);
  const short = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : `${n}`);
  const unit = (s) => (s.d === 'food' ? 'food' : 'cash income');
</script>

<section class="exposure" aria-labelledby="exposure-title">
  <header class="title-row">
    <h1 id="exposure-title">{country}: who is hit when a source of food or income falls</h1>
    <select value={country} onchange={(e) => oncountry(e.currentTarget.value)} aria-label="Country">
      {#each COUNTRIES as c}<option value={c}>{c}</option>{/each}
    </select>
  </header>

  {#if !current}
    <div class="panel empty">
      <p>None of {country}'s livelihood zone profiles quantify where households get their food or income, so there is
        nothing to score for {country}. Its profiles describe the zones in words only.</p>
    </div>
  {:else}
    <div class="question panel">
      <p class="sentence">
        If <strong>{current.label.toLowerCase()}</strong> falls by
        <input type="range" min="1" max="25" step="1" bind:value={shock} aria-label="Size of the fall" />
        <strong class="num pct">{shock}%,</strong>
        counting people who lose at least
        <input type="range" min="1" max="25" step="1" bind:value={hit} aria-label="Loss that counts as hit" />
        <strong class="num pct">{hit}%</strong>
        of their {unit(current)}
      </p>
      <p class="answer">
        <strong>{M(totalHit)}</strong> people in {country} lose at least {hit}% of their {unit(current)}.
      </p>
      {#if shock < hit}
        <p class="muted small">
          No one can be hit: a {shock}% fall costs at most {shock}% even for a group that relies on the source entirely.
        </p>
      {:else}
        <p class="muted small">At these settings a group is hit if it gets at least {Math.ceil((100 * hit) / shock)}% of its {unit(current)} from the source.</p>
      {/if}
      <p class="muted small">
        {Math.round((100 * totalHit) / population)}% of {country}'s {short(population)} people.
        {#if current.fall}For this source the fall is in {current.fall}.{/if}
        {#if unknownPop > population * 0.02}{short(unknownPop)} people live in zones whose profile has no breakdown (grey with a dashed edge on the map).{/if}
      </p>
    </div>

    <div class="body">
      <div class="map-card">
        <ExposureMap zones={zonesGeo} stats={zoneStats} {country} {dark} selected={selectedZone} onselect={(f) => (selectedZone = f)} />
        <div class="legend" aria-label="Share of each zone's people hit">
          <span class="legend-title">Share of the zone's people hit</span>
          {#each BINS as b}<span><i style="background:var({b.ramp})"></i>{b.label}</span>{/each}
          <span><i class="nodata"></i>No breakdown</span>
        </div>
      </div>

      <aside class="side">
        {#if zone}
          <div class="panel">
            <header class="zone-head">
              <h2>{zone.zone}</h2>
              <button class="close" aria-label="Back to the source list" onclick={() => (selectedZone = null)}>×</button>
            </header>
            <p class="muted small">{short(zone.p)} people · {current.label.toLowerCase()} falls {shock}%</p>
            {#if zoneGroups.some((g) => g.share !== null)}
              <table>
                <thead><tr><th>Group</th><th class="num">People</th><th class="num">From source</th><th class="num">Loses</th></tr></thead>
                <tbody>
                  {#each zoneGroups as g}
                    <tr class:hit={g.loss !== null && g.loss >= hit}>
                      <td>{g.g === 'all' ? 'Whole zone' : g.label}</td>
                      <td class="num">{short(g.p)}</td>
                      <td class="num">{g.share === null ? '–' : `${Math.round(g.share)}%`}</td>
                      <td class="num">{g.loss === null ? '–' : `${Math.round(g.loss)}%`}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
              <p class="muted small">
                Bold rows lose at least {hit}% of their {unit(current)}. Shares are of {current.d === 'food' ? 'annual food needs' : 'annual cash income'}.
                {#if zoneGroups.some((g) => g.g === 'all')}This profile gives one figure for the whole zone, not by wealth group.{/if}
              </p>
            {:else}
              <p class="muted small">This zone's profile has no breakdown of {unit(current)}, so it can't be scored.</p>
            {/if}
          </div>
        {:else}
          <div class="panel">
            <h2>Pick a source</h2>
            <p class="muted small">
              Each bar asks the same question of a different source: if <em>that source alone</em> fell {shock}%, how many
              people in {country} would lose {hit}%? Moving a slider redraws every bar; the sources don't affect each other.
            </p>
            <div class="sources">
              {#each ranked.filter((s) => s.hit || s.key === current.key) as s (s.key)}
                <button class="src" class:active={s.key === current.key} aria-pressed={s.key === current.key} onclick={() => (sourceKey = s.key)}>
                  <span class="name">{s.label}<small>{s.d === 'food' ? 'food' : 'income'}</small></span>
                  <span class="bar" aria-hidden="true"><i style="width:{(100 * s.hit) / maxHit}%"></i></span>
                  <span class="num">{s.hit ? short(s.hit) : '0'}</span>
                </button>
              {/each}
            </div>
            {#if ranked.some((s) => !s.hit && s.key !== current.key)}
              <p class="muted small">
                At a {shock}% fall, no one loses {hit}% of their food or income from:
                {ranked.filter((s) => !s.hit && s.key !== current.key).map((s) => s.label.toLowerCase()).join(', ')}.
              </p>
            {/if}
            <p class="muted small">Click a zone on the map to see its wealth groups.</p>
          </div>
        {/if}
      </aside>
    </div>
  {/if}

  <p class="note">
    A wealth group is hit when its share from the source × the fall is at least {hit}% of its food needs or cash
    income. No switching between sources or price knock-on effects. Shares: FEWS NET livelihood zone profiles
    (reference years 2005–2024) via the Explore Livelihood dataset; people: WorldPop 2020.
  </p>
</section>

<style>
  .exposure { padding: var(--pad); display: grid; gap: var(--gap); align-content: start; max-width: 1400px; }
  .title-row { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
  h1 { font-size: var(--fs-title); line-height: 1.2; letter-spacing: -0.01em; }
  h2 { font-size: var(--fs-section); }
  select {
    height: var(--control-height); padding: 0 12px; border-radius: 999px; border: 1px solid var(--control);
    background: var(--surface); color: var(--text); font: inherit;
  }
  .panel { background: var(--surface); border-radius: var(--radius-card); padding: 16px 20px; }
  .empty p { max-width: 70ch; }
  .question { display: grid; gap: 6px; }
  .sentence { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; font-size: 16px; }
  .sentence input { width: min(180px, 40vw); accent-color: var(--accent); }
  .pct { min-width: 3ch; display: inline-block; }
  .answer { font-size: 20px; line-height: 1.35; }
  .answer strong { font-variant-numeric: tabular-nums; }
  .muted { color: var(--muted); }
  .small { font-size: var(--fs-small); }
  .num { font-variant-numeric: tabular-nums; text-align: right; }

  .body { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: var(--gap); align-items: start; }
  .map-card { position: relative; height: min(72vh, 680px); background: var(--surface); border-radius: var(--radius-card); }
  .legend {
    position: absolute; left: 12px; top: 12px; display: grid; gap: 3px; padding: 8px 10px; border-radius: 4px;
    background: color-mix(in srgb, var(--surface) 92%, transparent); font-size: var(--fs-small);
  }
  .legend-title { color: var(--muted); }
  .legend span { display: inline-flex; align-items: center; gap: 8px; }
  .legend i { width: 14px; height: 10px; border-radius: 2px; display: inline-block; }
  .legend i.nodata { background: var(--raised); outline: 1px dashed var(--muted); outline-offset: -1px; }

  .side { display: grid; gap: var(--gap); }
  .side .panel { display: grid; gap: 10px; }
  .sources { display: grid; }
  .src {
    display: grid; grid-template-columns: minmax(0, 150px) minmax(0, 1fr) 48px; gap: 10px; align-items: center;
    width: 100%; min-height: 38px; padding: 4px 6px; border: 0; border-top: 1px solid var(--rule); background: none;
    color: var(--text); font: inherit; font-size: var(--fs-body); text-align: left; cursor: pointer; border-radius: 0;
  }
  .src:hover .name { color: var(--accent); }
  .src.active { background: var(--raised); }
  .name { display: grid; line-height: 1.25; }
  .name small { color: var(--faint); font-size: 11px; }
  .bar { display: block; height: 10px; background: var(--rule); border-radius: 2px; }
  .bar i { display: block; height: 100%; background: var(--ramp-5); border-radius: 2px; }
  .src.active .bar i { background: var(--accent); }

  .zone-head { display: flex; justify-content: space-between; gap: 12px; align-items: start; }
  .close { border: 0; background: none; color: var(--muted); font-size: 20px; line-height: 1; cursor: pointer; }
  table { width: 100%; border-collapse: collapse; font-size: var(--fs-body); }
  th { color: var(--muted); font-weight: 400; font-size: var(--fs-small); text-align: left; padding: 4px 0; }
  td { padding: 6px 0; border-top: 1px solid var(--rule); }
  tr.hit td { font-weight: 650; }
  .note { font-size: var(--fs-small); color: var(--muted); max-width: 90ch; }

  @media (max-width: 900px) {
    .exposure { padding: 16px; }
    .title-row { flex-direction: column; align-items: flex-start; }
    .body { grid-template-columns: 1fr; }
    .map-card { height: 60vh; }
    .answer { font-size: 17px; }
  }
</style>
