<script>
  import { onMount } from 'svelte';
  import Map from './Map.svelte';
  import { FILLS } from './fills.js';
  import { asset } from './paths.js';

  const COUNTRIES = ['Kenya', 'Malawi', 'Nigeria', 'Uganda', 'Somalia', 'Guatemala'];
  const SYSTEMS = [
    { key: 'hfid', label: 'HFID admin-2 units', cls: 'k-hfid' },
    { key: 'zones', label: 'FEWS livelihood zones', cls: 'k-zone' },
    { key: 'admin1', label: 'Provinces and states', cls: 'k-a1' },
    { key: 'admin2', label: 'Districts (geoBoundaries)', cls: 'k-a2' },
    { key: 'smap', label: 'SMAP 36 km grid (reference)', cls: 'k-smap' },
    { key: 'fao', label: 'FAO price series (towns and areas)', cls: 'k-fao' },
    { key: 'faoCatch', label: 'FAO town price catchments', cls: 'k-catch-fao' },
    { key: 'wfp', label: 'WFP markets', cls: 'k-wfp' },
    { key: 'wfpCatch', label: 'WFP price catchments', cls: 'k-catch-wfp' },
  ];

  let country = $state('Kenya');
  let fill = $state('dominant_share');
  let layers = $state({ hfid: true, zones: false, admin1: false, admin2: false, smap: false, fao: true, wfp: true, faoCatch: true, wfpCatch: false });
  let catchments = $state({ wfp: [], fao: [] });
  let selected = $state(null);
  let summary = $state(null);
  let theme = $state('auto');
  let systemDark = $state(false);
  const dark = $derived(theme === 'dark' || (theme === 'auto' && systemDark));

  function readHash() {
    const h = new URLSearchParams(location.hash.slice(1));
    if (COUNTRIES.includes(h.get('country'))) country = h.get('country');
    if (h.get('fill') in FILLS) fill = h.get('fill');
    if (['auto', 'light', 'dark'].includes(h.get('theme'))) theme = h.get('theme');
  }
  onMount(() => {
    const mq = matchMedia('(prefers-color-scheme: dark)');
    systemDark = mq.matches;
    mq.addEventListener('change', (e) => (systemDark = e.matches));
    readHash();
    addEventListener('hashchange', readHash);
    fetch(asset('/data/summary.json')).then((r) => r.json()).then((s) => (summary = s));
    for (const source of ['wfp', 'fao']) {
      fetch(asset(`/data/catchments_${source}.geojson`)).then((r) => r.json())
        .then((g) => (catchments[source] = g.features.map((f) => ({ ...f.properties, geometry: undefined }))));
    }
  });
  $effect(() => {
    if (theme === 'auto') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
  });
  $effect(() => {
    const h = new URLSearchParams({ country, fill });
    if (theme !== 'auto') h.set('theme', theme);
    if (location.hash !== `#${h}`) history.replaceState(null, '', `#${h}`);
  });

  const s = $derived(summary?.[country]);
  const pct = (x) => `${Math.round(x * 100)}%`;
  const n = (x) => (x === null || x === undefined ? '—' : Math.round(x).toLocaleString());
  const cells = (x) => (x === null || x === undefined ? '—' : x < 10 ? x.toFixed(2) : Math.round(x).toLocaleString());


  const table = $derived(s ? [
    { label: 'HFID admin-2 units', cls: 'k-hfid', count: s.units.hfid.n, km2: s.units.hfid.median_km2, cells: s.units.hfid.median_smap_cells },
    { label: 'Livelihood zones', cls: 'k-zone', count: s.units.zones.n, km2: s.units.zones.median_km2, cells: s.units.zones.median_smap_cells },
    { label: 'Provinces and states', cls: 'k-a1', count: s.units.admin1.n, km2: s.units.admin1.median_km2, cells: s.units.admin1.median_km2 / s.units.smap.cell_km2 },
    { label: 'Districts (geoBoundaries)', cls: 'k-a2', count: s.units.admin2.n, km2: s.units.admin2.median_km2, cells: s.units.admin2.median_km2 / s.units.smap.cell_km2 },
    { label: 'SMAP 36 km cells', cls: 'k-smap', count: s.units.smap.n, km2: s.units.smap.cell_km2, cells: 1 },
  ] : []);
  const f = $derived(FILLS[fill]);
</script>

<div class="app">
  <header class="top">
    <div class="title">
      <h1>{country} boundaries</h1>
      <p class="muted">Geographical inconsistencies between different measurement units.</p>
    </div>
    <div class="controls">
      <select bind:value={country} aria-label="Country" onchange={() => (selected = null)}>
        {#each COUNTRIES as c}<option>{c}</option>{/each}
      </select>
      <button class="ghost" onclick={() => (theme = { auto: 'light', light: 'dark', dark: 'auto' }[theme])}>Theme: {theme}</button>
    </div>
  </header>

  <div class="body">
    <div class="map-card">
      <Map {country} {layers} {fill} {dark} {selected} onselect={(x) => (selected = x)} />
      <div class="key" aria-label="Layers">
        {#each SYSTEMS as sys}
          <label><input type="checkbox" bind:checked={layers[sys.key]} /><i class={sys.cls}></i>{sys.label}</label>
        {/each}
      </div>
    </div>

    <aside class="side">
      {#if selected}
        <article class="panel detail">
          <header>
            <h2>{selected.kind === 'zone' ? selected.zone : selected.admin2 || selected.admin1}</h2>
            <button class="close" aria-label="Clear selection" onclick={() => (selected = null)}>×</button>
          </header>
          {#if selected.kind === 'market'}
            {@const c = catchments[selected.source].find((x) => x.market === selected.market && x.country === selected.country)}
            <p class="muted small">{selected.source === 'wfp' ? 'WFP market' : 'FAO town price series'} · its catchment is shaded on the map</p>
            {#if c}
              <dl>
                <dt>Catchment area</dt><dd>{n(c.area_km2)} km²</dd>
                <dt>Distance inside it</dt><dd>median {c.median_km} km · 90th pct {c.p90_km} km</dd>
              </dl>
              <p class="muted small">Every 1 km cell in the catchment is closer in a straight line to this market than to any other {selected.source === 'wfp' ? 'WFP market' : 'FAO town series'}, so this is the area its price stands in for.</p>
            {:else}
              <p class="muted small">No catchment: the market sits outside the country's land or shares a cell with another market.</p>
            {/if}
          {:else if selected.kind === 'hfid'}
            <p class="muted small">HFID unit · {selected.admin1} · {n(selected.area_km2)} km²</p>
            <dl>
              <dt>Main livelihood zone</dt><dd>{selected.dominant_zone ?? '—'} <span class="muted">({selected.dominant_share ? pct(selected.dominant_share) : '—'} of the unit)</span></dd>
              <dt>Zones it touches</dt><dd>{selected.n_zones}</dd>
              <dt>Size in SMAP cells</dt><dd>{cells(Number(selected.smap_cells))}</dd>
              <dt>geoBoundaries district</dt><dd>{selected.gb_district ?? '—'} <span class="muted">(overlap {selected.gb_iou ? Number(selected.gb_iou).toFixed(2) : '—'})</span></dd>
              <dt>Markets inside</dt><dd>{selected.n_wfp} WFP · {selected.n_fao} FAO</dd>
              <dt>WFP price source</dt><dd>{selected.wfp_market ?? '—'} <span class="muted">({selected.wfp_km ?? '—'} km{selected.wfp_n_catchments > 1 ? `; spans ${selected.wfp_n_catchments} catchments` : ''})</span></dd>
              <dt>FAO price source</dt><dd>{selected.fao_market ?? '—'} <span class="muted">({selected.fao_km ?? '—'} km)</span></dd>
              <dt>HFID months</dt><dd>FEWS {selected.months_fews} · IPC/CH {selected.months_ipcch} · FCS {selected.months_fcs}</dd>
              <dt>Latest FEWS IPC</dt><dd>{selected.fews_latest ? `Phase ${Number(selected.fews_latest)} (${selected.fews_latest_month})` : '—'}</dd>
            </dl>
          {:else}
            <p class="muted small">Livelihood zone {selected.fnid} · {n(selected.area_km2)} km² · map {selected.map_version}</p>
            <dl>
              <dt>HFID units touching it</dt><dd>{selected.n_hfid}</dd>
              <dt>HFID units inside (80%+)</dt><dd>{selected.n_hfid_nested}</dd>
              <dt>Size in SMAP cells</dt><dd>{cells(Number(selected.smap_cells))}</dd>
              <dt>Markets inside</dt><dd>{selected.n_wfp} WFP · {selected.n_fao} FAO</dd>
            </dl>
          {/if}
        </article>
      {/if}

      <section class="panel">
        <h2>Fill HFID units by</h2>
        <div class="fills" role="radiogroup" aria-label="Fill">
          {#each Object.entries(FILLS) as [k, v]}
            <label class:on={fill === k}><input type="radio" name="fill" value={k} bind:group={fill} />{v.label}</label>
          {/each}
        </div>
        <p class="muted small">{f.question}</p>
        {#if f.bins}
          <div class="bins">
            {#each f.bins as b, i}<span><i style="background: var({f.ramp[i]})"></i>{b.label}</span>{/each}
          </div>
        {/if}
      </section>

      {#if s}
        <section class="panel">
          <h2>Unit systems</h2>
          <table>
            <thead><tr><th>Unit</th><th class="num">Count</th><th class="num">Median km²</th><th class="num">SMAP cells</th></tr></thead>
            <tbody>
              {#each table as r}
                <tr><td><i class={r.cls}></i>{r.label}</td><td class="num">{n(r.count)}</td><td class="num">{n(r.km2)}</td><td class="num">{cells(r.cells)}</td></tr>
              {/each}
            </tbody>
          </table>
          <p class="muted small">
            Prices: {s.units.fao.towns} FAO town series, {s.units.fao.areas} FAO area series, {s.units.wfp.n} WFP markets with prices since 2019.
            {s.hfid_without_data ? `${s.hfid_without_data} HFID units have geometry but no rows in the HFID table.` : ''}
          </p>
        </section>

        <section class="panel">
          <h2>Soil-moisture series in the data</h2>
          <p class="muted small">Only names and cell counts are recorded; the cells averaged into each series are unknown, so these regions cannot be drawn. The green grid is SMAP's standard 36 km grid for reference.</p>
          <table>
            <thead><tr><th>Series</th><th class="num">Median cells</th><th class="num">Max</th></tr></thead>
            <tbody>
              {#each s.smap_regions as r}
                <tr><td>{r.region}{#if r.smart}<span class="tag">SMART</span>{/if}</td><td class="num">{n(r.median_cells)}</td><td class="num">{n(r.max_cells)}</td></tr>
              {/each}
            </tbody>
          </table>
          <p class="muted small">{country}'s land touches {s.units.smap.n} grid cells ({s.units.smap.full_cells} fully inside).</p>
        </section>
      {/if}

    </aside>
  </div>
</div>

<style>
  .app { display: grid; grid-template-rows: auto minmax(0, 1fr); height: 100vh; padding: 20px 24px 24px; gap: 12px; }
  .top { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
  .title { display: grid; gap: 4px; }
  h1 { font-size: var(--fs-title); line-height: 1.2; letter-spacing: -0.01em; }
  h2 { font-size: var(--fs-section); }
  .controls { display: flex; gap: 8px; align-items: center; }
  select, .ghost { height: 32px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--control); background: var(--surface); color: var(--text); }
  .body { display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 20px; min-height: 0; }
  .map-card { position: relative; border-radius: var(--radius-card); overflow: hidden; background: var(--surface); min-height: 420px; }
  .key {
    position: absolute; left: 12px; bottom: 12px; display: grid; gap: 2px; padding: 8px 10px; border-radius: 4px;
    background: color-mix(in srgb, var(--surface) 92%, transparent); font-size: var(--fs-small);
  }
  .key label { display: flex; align-items: center; gap: 8px; cursor: pointer; min-height: 22px; }
  input[type='checkbox'], input[type='radio'] { accent-color: var(--accent); margin: 0; }
  i { display: inline-block; flex: none; vertical-align: middle; }
  .k-hfid { width: 18px; border-top: 1px solid var(--sys-hfid); }
  .k-zone { width: 18px; border-top: 3px solid var(--sys-zone); }
  .k-a1 { width: 18px; border-top: 2px dashed var(--sys-admin); }
  .k-a2 { width: 18px; border-top: 1px dotted var(--sys-admin); }
  .k-smap { width: 12px; height: 12px; border: 1px solid var(--sys-smap); }
  .k-fao { width: 10px; height: 10px; border-radius: 50%; border: 2px solid var(--sys-price); }
  .k-wfp { width: 6px; height: 6px; border-radius: 50%; background: var(--sys-price); }
  .k-catch-fao { width: 18px; border-top: 2px solid var(--sys-price); }
  .k-catch-wfp { width: 18px; border-top: 1px solid var(--sys-price); }
  td i { margin-right: 8px; }
  .side { display: flex; flex-direction: column; gap: 12px; overflow-y: auto; min-height: 0; }
  .panel { background: var(--surface); border-radius: var(--radius-card); padding: 14px 16px; display: grid; gap: 8px; }
  .detail header { display: flex; justify-content: space-between; gap: 8px; }
  .close { border: 0; background: none; color: var(--muted); font-size: 18px; line-height: 1; }
  dl { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; margin: 0; font-size: 13px; }
  dt { color: var(--muted); }
  dd { margin: 0; text-align: right; }
  .small { font-size: var(--fs-small); }
  .fills { display: grid; gap: 2px; }
  .fills label { display: flex; gap: 8px; align-items: center; min-height: 26px; padding: 0 6px; border-radius: 4px; cursor: pointer; }
  .fills label.on { background: var(--raised); }
  .bins { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: var(--fs-small); color: var(--muted); }
  .bins i { width: 12px; height: 12px; border-radius: 2px; margin-right: 5px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; font-weight: 400; color: var(--muted); font-size: var(--fs-small); padding: 0 0 4px; }
  td { padding: 5px 0; border-top: 1px solid var(--rule); }
  .num { text-align: right; padding-left: 10px; }
  .tag { margin-left: 6px; font-size: 11px; padding: 1px 6px; border-radius: 999px; background: var(--raised); color: var(--muted); }
  @media (max-width: 1000px) {
    .app { height: auto; }
    .body { grid-template-columns: 1fr; }
    .map-card { height: 60vh; }
  }
  @media (max-width: 600px) {
    .app { padding: 16px; }
    .top { flex-direction: column; }
    .key { position: static; background: none; }
    .map-card { overflow: visible; display: grid; grid-template-rows: 60vh auto; height: auto; }
    .map-card :global(.map) { position: relative; inset: auto; }
  }
</style>
