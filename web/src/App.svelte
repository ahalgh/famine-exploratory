<script>
  import { onMount } from 'svelte';
  import MapView from './lib/MapView.svelte';
  import CoverageTimeline from './lib/CoverageTimeline.svelte';
  import { ZONE_METRICS, binLabels, seqVars } from './lib/metrics.js';

  let coverage = $state(null);
  let selected = $state({ type: 'country', country: 'Kenya' });
  let layers = $state({ zones: true, coverage: false, admin1: true, districts: false, ipc: true, markets: false, wfp: true });
  let zoneMetric = $state('city_motorized_median_h');
  const metric = $derived(ZONE_METRICS[zoneMetric]);
  const fmtH = (v) => (v === null || v === undefined ? '—' : `${Number(v).toFixed(1)} h`);
  let ipcSource = $state('ipc_fews_2019_02');
  let basemap = $state(true);

  const country = $derived(selected?.country ?? 'Kenya');
  const summary = $derived(
    coverage
      ? coverage.datasets.map((d) => {
          const c = coverage.counts[d.key][country];
          const idx = c.map((n, i) => (n ? i : -1)).filter((i) => i >= 0);
          return { ...d, rows: d.rows_by_country[country], first: coverage.months[idx[0]], last: coverage.months[idx.at(-1)] };
        })
      : []
  );

  onMount(async () => {
    coverage = await (await fetch('/data/coverage.json')).json();
  });

  const LAYER_LABELS = {
    zones: 'Livelihood zones',
    coverage: 'Countries shaded by datasets covered',
    admin1: 'Admin1 boundaries',
    districts: 'District boundaries',
    ipc: 'Guatemala district IPC',
    markets: 'FAO price markets',
    wfp: 'WFP markets (prices since 2019)',
  };
</script>

<div class="app">
  <aside>
    <header>
      <h1>Data coverage</h1>
      <p class="muted">Which datasets exist where and when, and how accessible each livelihood zone is. Click a zone, market or country.</p>
    </header>

    <section>
      <h2>Layers</h2>
      {#each Object.keys(LAYER_LABELS) as key}
        <label class="check"><input type="checkbox" bind:checked={layers[key]} /> {LAYER_LABELS[key]}</label>
        {#if key === 'zones' && layers.zones}
          <select bind:value={zoneMetric} aria-label="Zone metric">
            {#each Object.entries(ZONE_METRICS) as [k, m]}<option value={k}>{m.label}</option>{/each}
          </select>
        {/if}
        {#if key === 'ipc' && layers.ipc}
          <select bind:value={ipcSource} aria-label="Guatemala IPC source">
            <option value="ipc_fews_2019_02">Observed, FEWS Feb 2019</option>
            <option value="ipc_ml1_2018_12">Projected, ML1 Dec 2018</option>
          </select>
        {/if}
      {/each}
      <label class="check"><input type="checkbox" bind:checked={basemap} /> Base map (OpenFreeMap)</label>
    </section>

    <section>
      <h2>Legend</h2>
      {#if layers.zones}
        <div class="legend-title">{metric.label}</div>
        {#if metric.ipc}
          <div class="legend-row"><span class="ramp ipc-ramp"></span><span class="muted">1 → 4 (mean phase)</span></div>
        {:else}
          <div class="bins">
            {#each binLabels(metric) as label, i}<span class="bin"><span class="swatch-sq" style="background:var({seqVars(metric)[i]})"></span>{label}</span>{/each}
          </div>
        {/if}
        <div class="legend-row"><span class="swatch-sq" style="background:var(--seq-0)"></span><span class="muted">No data</span></div>
        <p class="muted small">{metric.note}</p>
      {/if}
      {#if layers.wfp}<div class="legend-row"><span class="dot small-dot" style="background:var(--text-primary)"></span>WFP market</div>{/if}
      {#if layers.coverage}<div class="legend-row"><span class="ramp"></span><span class="muted">Countries: 1 → 9 datasets</span></div>{/if}
      {#if layers.markets}
        <div class="legend-row"><span class="dot" style="background:var(--series-1)"></span>FAO market town</div>
        <div class="legend-row"><span class="dot" style="background:var(--series-2)"></span>FAO county/district price (Kenya)</div>
        <div class="legend-row"><span class="dot" style="background:var(--series-3)"></span>FAO aggregate (national / Nigerian zone)</div>
        <div class="legend-row muted">FAO dot size = number of price rows</div>
      {/if}
      {#if layers.ipc}<div class="legend-row ipc">
        {#each [1, 2, 3, 4] as p}<span class="swatch" style="background:var(--ipc-{p})"></span>{p}{/each}
        <span class="muted">IPC phase</span>
      </div>
      <div class="legend-row"><span class="swatch-sq" style="background:var(--text-muted)"></span><span class="muted">Guatemala district with no IPC name match</span></div>{/if}
    </section>

    <section class="details">
      {#if selected?.type === 'zone'}
        <h2>{selected.zone}</h2>
        <p class="muted small">{selected.country} · {selected.lzcode} · map {selected.map_version} · {Number(selected.area_km2).toLocaleString()} km²</p>
        <table>
          <thead><tr><th>Travel time to nearest</th><th>Median</th><th>90th pct</th></tr></thead>
          <tbody>
            <tr><td>City 50k+, vehicle</td><td class="num">{fmtH(selected.city_motorized_median_h)}</td><td class="num">{fmtH(selected.city_motorized_p90_h)}</td></tr>
            <tr><td>City 50k+, on foot</td><td class="num">{fmtH(selected.city_walking_median_h)}</td><td class="num">{fmtH(selected.city_walking_p90_h)}</td></tr>
            <tr><td>WFP market, vehicle</td><td class="num">{fmtH(selected.market_motorized_median_h)}</td><td class="num">{fmtH(selected.market_motorized_p90_h)}</td></tr>
            <tr><td>WFP market, on foot</td><td class="num">{fmtH(selected.market_walking_median_h)}</td><td class="num">{fmtH(selected.market_walking_p90_h)}</td></tr>
          </tbody>
        </table>
        <dl class="zone-dl">
          <dt>WFP markets</dt><dd>{selected.wfp_markets_in_zone} inside the zone</dd>
          {#if selected.ipc_mean !== null && selected.ipc_mean !== undefined}
            <dt>Observed IPC</dt><dd>mean {Number(selected.ipc_mean).toFixed(2)} over {selected.ipc_reports} reports since 2020; {Math.round(selected.ipc3_share * 100)}% at phase 3+</dd>
            <dt>Latest</dt><dd>phase {selected.ipc_latest} ({selected.ipc_latest_date})</dd>
          {:else}
            <dt>Observed IPC</dt><dd class="muted">none for this zone</dd>
          {/if}
        </dl>
        <button class="link" onclick={() => (selected = { type: 'country', country: selected.country })}>Show {selected.country} coverage</button>
      {:else if selected?.type === 'wfp'}
        <h2>{selected.market}, {selected.country}</h2>
        <dl>
          <dt>Source</dt><dd>WFP (HDX), market {selected.market_id}</dd>
          <dt>Admin</dt><dd>{selected.admin1}{selected.admin2 ? `, ${selected.admin2}` : ''}</dd>
          <dt>Since 2019</dt><dd>{selected.n_rows} prices · {selected.n_commodities} commodities · {selected.n_months} months</dd>
          <dt>Period</dt><dd>{selected.first} – {selected.last}</dd>
        </dl>
        <button class="link" onclick={() => (selected = { type: 'country', country: selected.country })}>Show {selected.country} coverage</button>
      {:else if selected?.type === 'market'}
        <h2>{selected.region}, {selected.country}</h2>
        <dl>
          <dt>Location type</dt><dd>{selected.kind}</dd>
          <dt>Price series</dt><dd>{selected.n_series} ({selected.n_rows} rows)</dd>
          <dt>Period</dt><dd>{selected.first} – {selected.last} · {selected.n_months} months</dd>
          <dt>Commodities</dt><dd>{selected.commodities}</dd>
          {#if selected.admin1}<dt>Admin1</dt><dd>{selected.admin1.replaceAll(';', ', ')}</dd>{/if}
          <dt>Located by</dt><dd>{selected.source}<br /><span class="muted">{selected.note}</span></dd>
        </dl>
        <button class="link" onclick={() => (selected = { type: 'country', country: selected.country })}>Show {selected.country} coverage</button>
      {:else}
        <h2>{country}</h2>
        <table>
          <thead><tr><th>Dataset</th><th>Rows</th><th>Span</th></tr></thead>
          <tbody>
            {#each summary as d}
              <tr class:empty={!d.rows}>
                <td>{d.label}</td>
                <td class="num">{d.rows ? d.rows.toLocaleString() : '—'}</td>
                <td class="muted">{d.rows ? `${d.first} – ${d.last}` : 'not covered'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
        <p class="muted small">CPI is annual (shown across each year's months in the timeline). Soil-moisture regions have no boundaries in the data, so they aren't drawn. Click a livelihood zone for its access and IPC details.</p>
      {/if}
    </section>
  </aside>

  <main>
    <div class="map-wrap">
      <MapView {layers} {ipcSource} {zoneMetric} {basemap} selectedCountry={country} onselect={(s) => (selected = s)} />
    </div>
    <div class="timeline">
      <div class="timeline-head">
        <h2>{country}: rows per month</h2>
        <select bind:value={() => country, (c) => (selected = { type: 'country', country: c })} aria-label="Country">
          {#each coverage?.countries ?? [] as c}<option>{c}</option>{/each}
        </select>
      </div>
      {#if coverage}<CoverageTimeline {coverage} {country} />{/if}
    </div>
  </main>
</div>

<style>
  .app { display: grid; grid-template-columns: 320px minmax(0, 1fr); height: 100vh; }
  aside {
    background: var(--surface-1); border-right: 1px solid var(--border);
    overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 18px;
  }
  h1 { font-size: 18px; }
  h2 { font-size: 13px; margin-bottom: 6px; }
  .muted { color: var(--text-secondary); }
  .small { font-size: 12px; margin: 8px 0 0; }
  header p { margin: 4px 0 0; }
  .check { display: flex; gap: 6px; align-items: center; margin: 3px 0; cursor: pointer; }
  select { margin: 4px 0 4px 22px; padding: 3px 6px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface-1); }
  .legend-row { display: flex; align-items: center; gap: 6px; margin: 4px 0; }
  .dot { width: 11px; height: 11px; border-radius: 50%; border: 2px solid var(--surface-1); box-shadow: 0 0 0 1px var(--border); }
  .ramp { width: 64px; height: 10px; border-radius: 3px; background: linear-gradient(90deg, var(--seq-1), var(--seq-2), var(--seq-4), var(--seq-6)); }
  .swatch-sq { width: 12px; height: 12px; border-radius: 3px; flex: none; }
  .small-dot { width: 8px; height: 8px; border-width: 1px; }
  .legend-title { font-size: 12px; margin: 2px 0 4px; }
  .bins { display: grid; grid-template-columns: 1fr 1fr; gap: 3px 10px; font-size: 12px; }
  .bin { display: flex; align-items: center; gap: 6px; }
  .ipc-ramp { background: linear-gradient(90deg, var(--ipc-1), var(--ipc-2), var(--ipc-3), var(--ipc-4)); }
  .zone-dl { margin-top: 8px; }
  .ipc .swatch { width: 12px; height: 12px; border-radius: 3px; margin-left: 4px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th { text-align: left; color: var(--text-secondary); font-weight: 500; border-bottom: 1px solid var(--border); padding: 3px 4px; }
  td { padding: 3px 4px; border-bottom: 1px solid var(--border); vertical-align: top; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  tr.empty td:first-child { color: var(--text-muted); }
  dl { display: grid; grid-template-columns: 92px 1fr; gap: 4px 8px; margin: 0; font-size: 12px; }
  dt { color: var(--text-secondary); }
  dd { margin: 0; }
  .link { margin-top: 10px; background: none; border: none; color: var(--accent); padding: 0; cursor: pointer; }
  main { display: grid; grid-template-rows: 1fr auto; min-width: 0; }
  .map-wrap { position: relative; min-height: 300px; }
  .timeline { min-width: 0; overflow: hidden; background: var(--surface-1); border-top: 1px solid var(--border); padding: 10px 16px 12px; }
  .timeline-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
  .timeline-head select { margin: 0; }
  @media (max-width: 760px) {
    .app { grid-template-columns: 1fr; grid-template-rows: auto 1fr; height: auto; }
    aside { border-right: none; border-bottom: 1px solid var(--border); }
    main { height: 80vh; }
  }
</style>
