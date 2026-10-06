<script>
  import { onMount } from 'svelte';
  import MapView from './lib/MapView.svelte';
  import CoverageTimeline from './lib/CoverageTimeline.svelte';

  let coverage = $state(null);
  let selected = $state({ type: 'country', country: 'Kenya' });
  let layers = $state({ coverage: true, admin1: true, districts: false, ipc: true, markets: true });
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
    coverage: 'Countries shaded by datasets covered',
    admin1: 'Admin1 boundaries',
    districts: 'District boundaries',
    ipc: 'Guatemala district IPC',
    markets: 'FAO price markets',
  };
</script>

<div class="app">
  <aside>
    <header>
      <h1>Data coverage</h1>
      <p class="muted">Which datasets exist where and when. Click a country or market.</p>
    </header>

    <section>
      <h2>Layers</h2>
      {#each Object.keys(LAYER_LABELS) as key}
        <label class="check"><input type="checkbox" bind:checked={layers[key]} /> {LAYER_LABELS[key]}</label>
      {/each}
      {#if layers.ipc}
        <select bind:value={ipcSource} aria-label="Guatemala IPC source">
          <option value="ipc_fews_2019_02">Observed, FEWS Feb 2019</option>
          <option value="ipc_ml1_2018_12">Projected, ML1 Dec 2018</option>
        </select>
      {/if}
      <label class="check"><input type="checkbox" bind:checked={basemap} /> Base map (OpenFreeMap, light mode)</label>
    </section>

    <section>
      <h2>Legend</h2>
      <div class="legend-row"><span class="ramp"></span><span class="muted">Countries: 1 → 8 datasets</span></div>
      <div class="legend-row"><span class="dot" style="background:var(--series-1)"></span>Market town</div>
      <div class="legend-row"><span class="dot" style="background:var(--series-2)"></span>County/district price (Kenya)</div>
      <div class="legend-row"><span class="dot" style="background:var(--series-3)"></span>Aggregate (national / Nigerian zone)</div>
      <div class="legend-row muted">Dot size = number of price rows</div>
      <div class="legend-row ipc">
        {#each [1, 2, 3, 4] as p}<span class="swatch" style="background:var(--ipc-{p})"></span>{p}{/each}
        <span class="muted">IPC phase</span>
      </div>
      <div class="legend-row"><span class="swatch-sq" style="background:var(--text-muted)"></span><span class="muted">Guatemala district with no IPC name match</span></div>
    </section>

    <section class="details">
      {#if selected?.type === 'market'}
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
        <p class="muted small">CPI is annual (shown across each year's months in the timeline). Livelihood zones and soil-moisture regions have no geometry yet, so they aren't drawn.</p>
      {/if}
    </section>
  </aside>

  <main>
    <div class="map-wrap">
      <MapView {layers} {ipcSource} {basemap} selectedCountry={country} onselect={(s) => (selected = s)} />
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
  .swatch-sq { width: 12px; height: 12px; border-radius: 3px; }
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
