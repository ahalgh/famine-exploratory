<script>
  import { onMount } from 'svelte';
  import MapView from './lib/MapView.svelte';
  import CoverageView from './lib/CoverageView.svelte';
  import { ZONE_METRICS, METRIC_KEYS, colorCss, fmt, isMissing, legendSwatches, spearman } from './lib/metrics.js';

  const COUNTRIES = ['Kenya', 'Malawi', 'Nigeria', 'Uganda', 'Somalia', 'Guatemala'];

  // ---- state -------------------------------------------------------------------------------
  let view = $state('zones');
  let country = $state('Kenya');
  let zoneMetric = $state('ipc_mean');
  let selectedZone = $state(null);
  let selectedMarket = $state(null);
  let layers = $state({ zoneLines: true, fao: true, wfp: true, admin1: false, districts: false, gtIpc: true, basemap: true });
  let ipcSource = $state('ipc_fews_2019_02');
  let layersOpen = $state(false);
  let coverage = $state(null);
  let zonesGeo = $state(null);
  let wfpCount = $state(null);
  let faoCount = $state(null);
  let faoAreas = $state([]);
  let loadError = $state(null);

  // theme: auto follows the system; light/dark pin it
  let theme = $state('auto');
  let systemDark = $state(false);
  const dark = $derived(theme === 'dark' || (theme === 'auto' && systemDark));
  const THEME_NEXT = { auto: 'light', light: 'dark', dark: 'auto' };

  // the view lives in the URL hash so any view can be linked to: #country=Nigeria&measure=ipc_mean&theme=light
  function readHash() {
    const h = new URLSearchParams(location.hash.slice(1));
    if (COUNTRIES.includes(h.get('country'))) country = h.get('country');
    if (METRIC_KEYS.includes(h.get('measure'))) zoneMetric = h.get('measure');
    if (['zones', 'coverage'].includes(h.get('view'))) view = h.get('view');
    if (['auto', 'light', 'dark'].includes(h.get('theme'))) theme = h.get('theme');
    if (h.get('zone')) selectedZone = h.get('zone');
  }

  onMount(() => {
    try { theme = localStorage.getItem('theme') ?? 'auto'; } catch {}
    readHash();
    addEventListener('hashchange', readHash);
    const mq = matchMedia('(prefers-color-scheme: dark)');
    systemDark = mq.matches;
    const onChange = (e) => (systemDark = e.matches);
    mq.addEventListener('change', onChange);
    Promise.all([
      fetch('/data/coverage.json').then((r) => r.json()),
      fetch('/data/zones.geojson').then((r) => r.json()),
      fetch('/data/wfp_markets.geojson').then((r) => r.json()),
      fetch('/data/markets.geojson').then((r) => r.json()),
      fetch('/data/fao_areas.geojson').then((r) => r.json()),
    ])
      .then(([c, z, w, fm, fa]) => {
        coverage = c; zonesGeo = z; wfpCount = w.features.length;
        faoCount = fm.features.length + fa.features.length;
        faoAreas = fa.features.map((f) => f.properties);
      })
      .catch((e) => (loadError = String(e)));
    return () => { mq.removeEventListener('change', onChange); removeEventListener('hashchange', readHash); };
  });

  $effect(() => {
    const h = new URLSearchParams({ view, country, measure: zoneMetric });
    if (selectedZone) h.set('zone', selectedZone);
    if (theme !== 'auto') h.set('theme', theme);
    const next = `#${h}`;
    if (location.hash !== next) history.replaceState(null, '', next);
  });

  $effect(() => {
    if (theme === 'auto') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('theme', theme); } catch {}
  });

  // ---- derived data ------------------------------------------------------------------------
  const metric = $derived(ZONE_METRICS[zoneMetric]);
  const zones = $derived(zonesGeo ? zonesGeo.features.map((f) => f.properties).filter((p) => p.country === country) : []);
  const ranked = $derived(
    [...zones].sort((a, b) => {
      const va = isMissing(a[zoneMetric]) ? -Infinity : Number(a[zoneMetric]);
      const vb = isMissing(b[zoneMetric]) ? -Infinity : Number(b[zoneMetric]);
      return vb - va;
    }),
  );
  const zone = $derived(selectedZone ? zones.find((z) => z.fnid === selectedZone) ?? null : null);
  const hasIpc = $derived(zones.some((z) => !isMissing(z.ipc_mean)));
  const nationalFao = $derived(faoAreas.find((a) => a.country === country && a.scope === 'national average'));

  const finding = $derived.by(() => {
    if (!zones.length) return '';
    const road = ZONE_METRICS.city_motorized_median_h;
    if (hasIpc) {
      const top = zones.filter((z) => !isMissing(z.ipc_mean)).sort((a, b) => b.ipc_mean - a.ipc_mean)[0];
      let s = `${top.zone} has the highest mean IPC since 2020 (${Number(top.ipc_mean).toFixed(2)}), ${fmt(top.city_motorized_median_h, road)} by road from a city of 50,000+.`;
      const { rho, n } = spearman(zones.map((z) => z.city_motorized_median_h), zones.map((z) => z.ipc_mean));
      if (rho !== null && n >= 8) {
        s += Math.abs(rho) >= 0.3
          ? ` Across ${n} zones, more remote zones average ${rho > 0 ? 'higher' : 'lower'} IPC (Spearman ρ ${rho.toFixed(2)}).`
          : ` Across ${n} zones, remoteness and IPC are only weakly related (Spearman ρ ${rho.toFixed(2)}).`;
      }
      return s;
    }
    const far = [...zones].sort((a, b) => (b.city_motorized_median_h ?? 0) - (a.city_motorized_median_h ?? 0))[0];
    return `No zone-level IPC for ${country}. The most remote zone, ${far.zone}, is ${fmt(far.city_motorized_median_h, road)} by road from a city of 50,000+.`;
  });

  function selectZone(fnid, zoneCountry) {
    selectedMarket = null;
    if (zoneCountry && zoneCountry !== country) country = zoneCountry; // a click on a neighbour's zone moves there
    selectedZone = fnid === selectedZone ? null : fnid;
  }
  function selectMarket(p) {
    selectedZone = null;
    selectedMarket = p;
  }
  function setCountry(c) {
    country = c;
    selectedZone = null;
    selectedMarket = null;
  }

  function onWindowKey(e) {
    if (e.key === 'Escape') {
      if (layersOpen) layersOpen = false;
      else { selectedZone = null; selectedMarket = null; }
    }
  }
  function onWindowClick(e) {
    if (layersOpen && !e.target.closest('.layers')) layersOpen = false;
  }
  const pct = (v) => (isMissing(v) ? '—' : `${Math.round(Number(v) * 100)}%`);
  const h = (v, digits = 1) => (isMissing(v) ? '—' : `${Number(v).toFixed(digits)} h`);
</script>

<svelte:window onkeydown={onWindowKey} onclick={onWindowClick} />

{#snippet countrySelect()}
  <label class="scope">
    <span class="sr-only">Country</span>
    <select value={country} onchange={(e) => setCountry(e.currentTarget.value)}>
      {#each COUNTRIES as c}<option>{c}</option>{/each}
    </select>
  </label>
{/snippet}

<div class="app">
  <nav class="rail" aria-label="Views">
    <span class="mark" title="Famine exploratory" aria-label="Famine exploratory">
      <svg viewBox="0 0 20 20" aria-hidden="true">
        <rect x="3" y="3" width="14" height="3" rx="1" fill="var(--ipc-1)" />
        <rect x="3" y="7" width="14" height="3" rx="1" fill="var(--ipc-2)" />
        <rect x="3" y="11" width="14" height="3" rx="1" fill="var(--ipc-3)" />
        <rect x="3" y="15" width="14" height="3" rx="1" fill="var(--ipc-4)" />
      </svg>
    </span>
    <button class="nav" class:active={view === 'zones'} aria-current={view === 'zones' ? 'page' : undefined} onclick={() => (view = 'zones')}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6.5 9 4l6 2.5L21 4v13.5L15 20l-6-2.5L3 20z" /><path d="M9 4v13.5M15 6.5V20" /></svg>
      <span class="label">Zones</span>
    </button>
    <button class="nav" class:active={view === 'coverage'} aria-current={view === 'coverage' ? 'page' : undefined} onclick={() => (view = 'coverage')}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16M4 10h16M4 15h16M4 20h10" /></svg>
      <span class="label">Coverage</span>
    </button>
    <span class="spacer"></span>
    <button class="nav util" onclick={() => (theme = THEME_NEXT[theme])} title="Theme: {theme}" aria-label="Theme: {theme}. Switch to {THEME_NEXT[theme]}">
      {#if theme === 'auto'}
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8" /><path d="M12 4v16" /><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" stroke="none" /></svg>
      {:else if theme === 'light'}
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" /></svg>
      {:else}
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" /></svg>
      {/if}
      <span class="label">Theme</span>
    </button>
  </nav>

  <main>
    {#if loadError}
      <p class="error">Couldn't load the map data ({loadError}). Run <code>python scripts/export_map_data.py</code>, then reload.</p>
    {:else if view === 'coverage'}
      {#if coverage}
        <div class="coverage-wrap">
          <div class="coverage-scope">{@render countrySelect()}</div>
          <CoverageView {coverage} {country} />
        </div>
      {/if}
    {:else}
      <section class="zones">
        <header class="title-row">
          <div class="title">
            <h1>{country} livelihood zones</h1>
            <p class="finding">{#if zonesGeo}{finding}{:else}<span class="skeleton" style="width: 60%"></span>{/if}</p>
          </div>
          {@render countrySelect()}
        </header>

        <div class="toolbar">
          <div class="tabs" role="tablist" aria-label="Zone measure">
            {#each METRIC_KEYS as key}
              <button role="tab" aria-selected={zoneMetric === key} class:active={zoneMetric === key} onclick={() => (zoneMetric = key)}>
                {ZONE_METRICS[key].tab}
              </button>
            {/each}
          </div>
          <div class="layers">
            <button class="ghost" aria-expanded={layersOpen} aria-controls="layers-panel" onclick={() => (layersOpen = !layersOpen)}>
              Layers
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
            </button>
            {#if layersOpen}
              <div class="menu" id="layers-panel" role="group" aria-label="Map layers">
                <p class="menu-head">Points</p>
                <label><input type="checkbox" bind:checked={layers.fao} /> FAO price series, labelled <span class="muted num">{faoCount}</span></label>
                <label><input type="checkbox" bind:checked={layers.wfp} /> WFP markets <span class="muted num">{wfpCount ?? ''}</span></label>
                <p class="menu-head">Lines</p>
                <label><input type="checkbox" bind:checked={layers.zoneLines} /> Livelihood zone boundaries</label>
                <label><input type="checkbox" bind:checked={layers.admin1} /> Province and state boundaries</label>
                <label><input type="checkbox" bind:checked={layers.districts} /> District boundaries</label>
                {#if country === 'Guatemala'}
                  <p class="menu-head">Guatemala</p>
                  <label><input type="checkbox" bind:checked={layers.gtIpc} disabled={Boolean(metric.raster)} /> District IPC (Mean IPC view)</label>
                  {#if layers.gtIpc && !metric.raster}
                    <select bind:value={ipcSource} aria-label="Guatemala district IPC source">
                      <option value="ipc_fews_2019_02">Observed, Feb 2019</option>
                      <option value="ipc_ml1_2018_12">Projected (ML1), Dec 2018</option>
                    </select>
                  {/if}
                {/if}
                <p class="menu-head">Background</p>
                <label><input type="checkbox" bind:checked={layers.basemap} /> Base map</label>
              </div>
            {/if}
          </div>
        </div>

        <div class="body">
          <div class="map-card">
            {#if zonesGeo}
              <MapView zones={zonesGeo} {layers} {ipcSource} {zoneMetric} {country} {selectedZone} {dark}
                selectedFaoArea={selectedMarket?.layer === 'fao-area' ? selectedMarket.region : null}
                onselectzone={selectZone} onselectmarket={selectMarket} />
            {/if}
            <div class="legend" aria-label="Legend">
              <p class="legend-title">{metric.label} <span class="muted">({metric.raster ? '1 km cells' : 'one value per zone'})</span></p>
              <div class="swatches">
                {#each legendSwatches(metric) as s}
                  <span class="sw"><i style="background: var({s.var})"></i>{s.label}</span>
                {/each}
                <span class="sw"><i style="background: var(--ramp-0)"></i>No data</span>
              </div>
              <p class="legend-note">{metric.note}</p>
              <div class="keys">
                {#if layers.fao}<span class="key"><i class="k-town"></i>FAO prices for a town</span>
                <span class="key"><i class="k-area"></i>FAO prices for an area</span>{/if}
                {#if layers.wfp}<span class="key"><i class="k-wfp"></i>WFP market</span>{/if}
                {#if layers.zoneLines}<span class="key"><i class="k-zone"></i>Livelihood zone</span>{/if}
              </div>
            </div>
          </div>

          <aside class="side" aria-label="Zones">
            {#if zone}
              <article class="detail" aria-labelledby="zone-name">
                <header>
                  <div>
                    <h2 id="zone-name">{zone.zone}</h2>
                    <p class="muted meta">{zone.lzcode} · {Number(zone.area_km2).toLocaleString()} km² · map {zone.map_version}</p>
                  </div>
                  <button class="close" aria-label="Clear selection" onclick={() => (selectedZone = null)}>
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
                  </button>
                </header>
                <dl class="kv">
                  <dt>Mean IPC since 2020</dt>
                  <dd>{#if isMissing(zone.ipc_mean)}<span class="muted">—</span>{:else}<i class="dot" style="background: {colorCss('ipc_mean', zone.ipc_mean)}"></i>{Number(zone.ipc_mean).toFixed(2)}{/if}</dd>
                  <dt>Reports at phase 3+</dt>
                  <dd>{isMissing(zone.ipc3_share) ? '—' : `${pct(zone.ipc3_share)} of ${zone.ipc_reports}`}</dd>
                  <dt>Latest report</dt>
                  <dd>{isMissing(zone.ipc_latest) ? '—' : `Phase ${zone.ipc_latest}, ${zone.ipc_latest_date}`}</dd>
                  <dt>WFP markets in zone</dt>
                  <dd>{zone.wfp_markets_in_zone}</dd>
                </dl>
                <table class="times">
                  <thead><tr><th>Travel time to nearest</th><th class="num">Median</th><th class="num">90th pct</th></tr></thead>
                  <tbody>
                    <tr><td>City 50,000+, by road</td><td class="num">{h(zone.city_motorized_median_h)}</td><td class="num">{h(zone.city_motorized_p90_h)}</td></tr>
                    <tr><td>City 50,000+, on foot</td><td class="num">{h(zone.city_walking_median_h, 0)}</td><td class="num">{h(zone.city_walking_p90_h, 0)}</td></tr>
                    <tr><td>WFP market, by road</td><td class="num">{h(zone.market_motorized_median_h)}</td><td class="num">{h(zone.market_motorized_p90_h)}</td></tr>
                    <tr><td>WFP market, on foot</td><td class="num">{h(zone.market_walking_median_h, 0)}</td><td class="num">{h(zone.market_walking_p90_h, 0)}</td></tr>
                  </tbody>
                </table>
              </article>
            {:else if selectedMarket}
              <article class="detail" aria-labelledby="market-name">
                <header>
                  <div>
                    <h2 id="market-name">{selectedMarket.market ?? selectedMarket.region}</h2>
                    <p class="muted meta">
                      {#if selectedMarket.layer === 'wfp'}WFP market, {selectedMarket.country}
                      {:else if selectedMarket.layer === 'fao-town'}FAO price series for this town
                      {:else}FAO price series for an area: {selectedMarket.scope}{/if}
                    </p>
                  </div>
                  <button class="close" aria-label="Clear selection" onclick={() => (selectedMarket = null)}>
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
                  </button>
                </header>
                <dl class="kv">
                  {#if selectedMarket.layer === 'wfp'}
                    <dt>Area</dt><dd>{selectedMarket.admin2 || selectedMarket.admin1}</dd>
                    <dt>Commodities since 2019</dt><dd>{selectedMarket.n_commodities}</dd>
                    <dt>Prices since 2019</dt><dd>{Number(selectedMarket.n_rows).toLocaleString()} over {selectedMarket.n_months} months</dd>
                  {:else}
                    <dt>Prices refer to</dt>
                    <dd class="wrap">{selectedMarket.layer === 'fao-town' ? `${selectedMarket.region} (town)` : (selectedMarket.admin1 || selectedMarket.region).replaceAll(';', ', ')}</dd>
                    {#if selectedMarket.layer === 'fao-town'}<dt>Located by</dt><dd>{selectedMarket.source}</dd>{/if}
                    <dt>Series</dt><dd>{selectedMarket.n_series} · {Number(selectedMarket.n_rows).toLocaleString()} prices</dd>
                  {/if}
                  <dt>Period</dt><dd>{selectedMarket.first} – {selectedMarket.last}</dd>
                </dl>
                {#if selectedMarket.commodities}
                  <div class="commodities"><p class="muted small">Commodities</p><p>{selectedMarket.commodities}</p></div>
                {/if}
              </article>
            {/if}

            <div class="list-head">
              <h2>{metric.list}</h2>
              <span class="muted num">{zones.length}</span>
            </div>
            {#if nationalFao && layers.fao}
              <button class="national" onclick={() => selectMarket({ layer: 'fao-area', ...nationalFao })}>
                FAO national-average prices for {country}: {nationalFao.n_series} {nationalFao.n_series === 1 ? 'commodity' : 'commodities'} (not drawn on the map)
              </button>
            {/if}
            {#if !zonesGeo}
              <ol class="ranked">{#each Array(6) as _}<li><span class="skeleton" style="width: 80%"></span></li>{/each}</ol>
            {:else}
              <ol class="ranked">
                {#each ranked as z (z.fnid)}
                  <li>
                    <button class="row" class:selected={z.fnid === selectedZone} aria-pressed={z.fnid === selectedZone} onclick={() => selectZone(z.fnid)}>
                      <i class="dot" style="background: {colorCss(zoneMetric, z[zoneMetric])}"></i>
                      <span class="zone-name">{z.zone}</span>
                      <span class="value num">{fmt(z[zoneMetric], metric)}</span>
                      <span class="sub muted">
                        {#if metric.ipc}{fmt(z.city_motorized_median_h, ZONE_METRICS.city_motorized_median_h)} to a city by road (median)
                        {:else}Median; 90th pct {fmt(z[zoneMetric.replace('_median_', '_p90_')], metric)} · {isMissing(z.ipc_mean) ? 'no IPC' : `IPC ${Number(z.ipc_mean).toFixed(2)}`}{/if}
                      </span>
                    </button>
                  </li>
                {/each}
              </ol>
            {/if}
          </aside>
        </div>
      </section>
    {/if}
  </main>
</div>

<style>
  .app { display: grid; grid-template-columns: var(--rail) minmax(0, 1fr); height: 100vh; }

  /* rail: unlabelled icons; the active view is a 1px accent line on the rail's edge */
  .rail {
    display: flex; flex-direction: column; align-items: stretch; gap: 4px; padding: 14px 0;
    border-right: 1px solid var(--border); background: var(--ground);
  }
  .mark { display: grid; place-items: center; height: 36px; margin-bottom: 14px; }
  .mark svg { width: 22px; height: 22px; }
  .nav {
    position: relative; display: grid; place-items: center; height: 42px; border: 0; background: none;
    color: var(--muted); transition: color 150ms var(--ease-out);
  }
  .nav svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
  .nav:hover { color: var(--text); }
  .nav.active { color: var(--text); }
  .nav.active::after { content: ''; position: absolute; right: -1px; top: 9px; bottom: 9px; width: 1px; background: var(--accent); }
  .nav .label { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .spacer { flex: 1; }

  main { min-width: 0; overflow: auto; }

  /* zones view */
  .zones { display: grid; grid-template-columns: minmax(0, 1fr); grid-template-rows: auto auto minmax(0, 1fr); height: 100%; padding: 22px var(--pad) var(--pad); gap: 14px; }
  .title-row { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--gap); }
  .title { display: grid; gap: 6px; min-width: 0; }
  h1 { font-size: var(--fs-title); line-height: 1.2; letter-spacing: -0.01em; }
  .finding { color: var(--muted); font-size: 14px; max-width: 90ch; min-height: 21px; }

  .scope select, .menu select {
    height: var(--control-height); padding: 0 30px 0 12px; border-radius: 999px; border: 1px solid var(--control);
    background: var(--surface) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23888' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E") no-repeat right 10px center / 14px;
    appearance: none; cursor: pointer;
  }
  .coverage-wrap { position: relative; }
  .coverage-scope { position: absolute; right: var(--pad); top: 22px; z-index: 2; }

  .toolbar { min-width: 0; display: flex; justify-content: space-between; align-items: flex-end; gap: var(--gap); border-bottom: 1px solid var(--border); }
  .tabs { display: flex; gap: 22px; overflow-x: auto; min-width: 0; scrollbar-width: none; }
  .tabs button {
    position: relative; height: 36px; padding: 0; border: 0; background: none; color: var(--muted); white-space: nowrap;
    transition: color 150ms var(--ease-out);
  }
  .tabs button:hover { color: var(--text); }
  .tabs button.active { color: var(--text); font-weight: 500; }
  .tabs button.active::after { content: ''; position: absolute; left: 0; right: 0; bottom: -1px; height: 1px; background: var(--accent); }

  .layers { position: relative; padding-bottom: 6px; }
  .ghost {
    display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px; border-radius: 999px;
    border: 1px solid var(--control); background: none; color: var(--text);
  }
  .ghost svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2; }
  .ghost[aria-expanded='true'] svg { transform: rotate(180deg); }
  .menu {
    position: absolute; right: 0; top: calc(100% + 4px); z-index: 20; width: 260px; display: grid; gap: 2px;
    padding: 8px; border-radius: var(--radius-card); background: var(--raised); box-shadow: var(--shadow); /* taste-skill-ignore: floating menu */
  }
  .menu-head { font-size: 11px; color: var(--muted); padding: 8px 6px 2px; }
  .menu-head:first-child { padding-top: 2px; }
  .menu label:has(input:disabled) { color: var(--muted); cursor: default; }
  .menu label { display: flex; align-items: center; gap: 8px; min-height: 32px; padding: 0 6px; border-radius: 4px; cursor: pointer; }
  .menu label:hover { background: color-mix(in srgb, var(--text) 6%, transparent); }
  .menu label .muted { margin-left: auto; }
  .menu select { width: calc(100% - 28px); margin: 2px 0 4px 28px; }
  input[type='checkbox'] { accent-color: var(--accent); width: 14px; height: 14px; margin: 0; }

  .body { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: var(--gap); min-height: 0; }
  .map-card { position: relative; min-height: 420px; border-radius: var(--radius-card); overflow: hidden; background: var(--surface); }
  .legend {
    position: absolute; left: 12px; bottom: 12px; max-width: 340px; padding: 10px 12px; border-radius: 4px;
    background: color-mix(in srgb, var(--surface) 92%, transparent); display: grid; gap: 6px;
  }
  .legend-title { font-size: var(--fs-small); font-weight: 600; }
  .swatches { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 11px; color: var(--muted); }
  .sw { display: inline-flex; align-items: center; gap: 4px; }
  .sw i, .dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px; flex: none; }
  .row .dot { margin-top: 4px; }
  .legend-note { font-size: 11px; color: var(--muted); line-height: 1.4; }
  .legend-title .muted { font-weight: 400; }
  .keys { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 11px; color: var(--muted); padding-top: 4px; border-top: 1px solid var(--rule); }
  .key { display: inline-flex; align-items: center; gap: 5px; }
  .key i { display: inline-block; flex: none; }
  .k-town { width: 9px; height: 9px; border-radius: 50%; border: 2px solid var(--text); background: var(--surface); }
  .k-area { width: 16px; height: 0; border-top: 2px dotted var(--text); }
  .k-wfp { width: 5px; height: 5px; border-radius: 50%; background: var(--text); opacity: 0.6; }
  .k-zone { width: 16px; height: 0; border-top: 1px solid var(--zone-line); }
  .wrap { white-space: normal; text-align: right; max-width: 200px; }
  .commodities { display: grid; gap: 2px; }
  .national {
    margin: 0 18px 8px; padding: 6px 10px; border: 1px dashed var(--control); border-radius: 4px; background: none;
    color: var(--muted); font-size: var(--fs-small); text-align: left;
  }
  .national:hover { color: var(--text); border-color: var(--muted); }

  .side { display: flex; flex-direction: column; min-height: 0; background: var(--surface); border-radius: var(--radius-card); overflow: hidden; }
  .detail { padding: 16px 18px 18px; border-bottom: 1px solid var(--border); display: grid; gap: 14px; }
  .detail header { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
  .detail h2 { font-size: var(--fs-section); line-height: 1.3; }
  .meta { font-size: var(--fs-small); margin-top: 2px; }
  .close { flex: none; width: 28px; height: 28px; display: grid; place-items: center; border: 0; border-radius: 4px; background: none; color: var(--muted); }
  .close:hover { color: var(--text); background: var(--raised); }
  .close svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.8; }
  .kv { display: grid; grid-template-columns: 1fr auto; gap: 6px 12px; margin: 0; }
  .kv dt { color: var(--muted); }
  .kv dd { margin: 0; text-align: right; display: inline-flex; gap: 6px; align-items: center; justify-content: flex-end; }
  .times { width: 100%; border-collapse: collapse; }
  .times th { text-align: left; font-weight: 400; font-size: var(--fs-small); color: var(--muted); padding: 0 0 6px; }
  .times td { padding: 6px 0; border-top: 1px solid var(--rule); }
  .times .num { text-align: right; padding-left: 12px; }
  .small { font-size: var(--fs-small); }

  .list-head { display: flex; justify-content: space-between; align-items: baseline; padding: 14px 18px 8px; }
  .list-head h2 { font-size: var(--fs-section); }
  .ranked { list-style: none; margin: 0; padding: 0 8px 8px; overflow-y: auto; min-height: 0; }
  .ranked li + li .row { border-top-color: var(--rule); }
  .row {
    width: 100%; display: grid; grid-template-columns: 10px minmax(0, 1fr) auto; column-gap: 10px; row-gap: 1px;
    align-items: start; padding: 8px 10px; border: 0; border-top: 1px solid transparent; background: none; text-align: left;
    border-radius: 4px; transition: background-color 150ms var(--ease-out);
  }
  .row:hover { background: var(--raised); }
  .row.selected { background: var(--raised); box-shadow: inset 1px 0 0 var(--accent); /* taste-skill-ignore: the 1px selection line */ }
  .zone-name { overflow-wrap: anywhere; line-height: 1.35; }
  .value { text-align: right; }
  .sub { grid-column: 2 / -1; font-size: var(--fs-small); }

  .skeleton { display: inline-block; height: 0.9em; border-radius: 3px; background: var(--raised); vertical-align: middle; }
  .error { padding: var(--pad); color: var(--muted); }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

  /* tablet: the list goes under the map */
  @media (max-width: 1100px) {
    .zones { height: auto; }
    .body { grid-template-columns: 1fr; }
    .map-card { height: 58vh; }
    .ranked { overflow: visible; }
  }
  /* phone: the rail becomes a bottom bar */
  @media (max-width: 760px) {
    .app { grid-template-columns: 1fr; grid-template-rows: minmax(0, 1fr) auto; height: 100dvh; }
    .rail { order: 2; flex-direction: row; justify-content: space-around; padding: 0; border-right: 0; border-top: 1px solid var(--border); }
    .mark, .spacer { display: none; }
    .nav { flex: 1; height: 56px; grid-template-rows: auto auto; gap: 2px; }
    .nav .label { position: static; width: auto; height: auto; clip: auto; font-size: 11px; }
    .nav.active::after { left: 30%; right: 30%; top: -1px; bottom: auto; width: auto; height: 1px; }
    .zones { padding: 16px; gap: 12px; }
    .title-row { flex-direction: column; gap: 10px; }
    h1 { font-size: 22px; }
    .toolbar { flex-direction: column; align-items: stretch; border-bottom: 0; gap: 8px; }
    .tabs { border-bottom: 1px solid var(--border); }
    .layers { align-self: flex-start; }
    .map-card { height: 48vh; min-height: 300px; overflow: visible; display: grid; grid-template-rows: minmax(0, 1fr) auto; }
    .map-card :global(.map) { position: relative; inset: auto; height: 100%; border-radius: var(--radius-card); overflow: hidden; }
    .legend { position: static; max-width: none; background: none; padding: 10px 2px 0; }
    .ranked { padding: 0 6px 8px; }
    .list-head { padding: 14px 16px 8px; }
    .coverage-scope { position: static; padding: 16px 16px 0; }
  }
</style>
