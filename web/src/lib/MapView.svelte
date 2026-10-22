<script>
  import * as maplibregl from 'maplibre-gl';
  import { onMount } from 'svelte';
  import { ZONE_METRICS, fmt, rampColors, zoneColor } from './metrics.js';
  import { colorize, loadSurface, sample } from './raster.js';
  import { asset } from './paths.js';

  // Serve MapLibre's worker as a static file (copied to public/vendor by `npm run copy-worker`):
  // Vite's dev server injects its client into module scripts it serves from node_modules, which
  // breaks the worker, and pre-bundling breaks MapLibre's relative worker URL.
  maplibregl.setWorkerUrl(asset('/vendor/maplibre-gl-worker.mjs'));

  /**
   * Layer order, bottom to top. One fill at a time (IPC by zone, or a 1 km travel-time surface),
   * then lines (zones, provinces, districts, FAO areas), then points (WFP markets, FAO towns) and labels.
   * @type {{
   *   zones: any, layers: Record<string, boolean>, ipcSource: string, zoneMetric: string,
   *   country: string, selectedZone: string | null, dark: boolean,
   *   onselectzone: (fnid: string | null, country?: string) => void, onselectmarket: (p: any) => void
   * }}
   */
  let { zones, layers, ipcSource, zoneMetric, country, selectedZone, selectedFaoArea = null, dark, onselectzone, onselectmarket } = $props();

  const GLYPHS = 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf';
  const FONT = ['Noto Sans Regular'];
  const basemapUrl = (isDark) => `https://tiles.openfreemap.org/styles/${isDark ? 'dark' : 'positron'}`;
  let container;
  let map = $state(null);
  let ready = $state(false);
  let basemapFailed = $state(false);
  let surface = null; // the decoded travel-time surface on screen, for reading values under the cursor
  let bounds = {};

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const isRaster = () => Boolean(ZONE_METRICS[zoneMetric].raster);

  function blankStyle() {
    return { version: 8, glyphs: GLYPHS, sources: {}, layers: [{ id: 'background', type: 'background', paint: { 'background-color': css('--ground') } }] };
  }

  // the selected country's zones carry the data; neighbours stay legible as context
  const zoneOpacity = () => (isRaster() ? 0 : ['case', ['==', ['get', 'country'], country], dark ? 0.85 : 0.92, 0.45]);
  const countryWidth = () => ['case', ['==', ['get', 'country'], country], 1.6, 0.8];
  const gtIpcColor = (src) => ['match', ['to-number', ['get', src]], 1, css('--ipc-1'), 2, css('--ipc-2'), 3, css('--ipc-3'), 4, css('--ipc-4'), css('--ramp-0')];
  const faoAreaFilter = (...names) => ['in', ['get', 'region'], ['literal', names.filter(Boolean)]];
  let hoveredFaoArea = null;
  const labelPaint = () => ({
    'text-color': css('--text'), 'text-halo-color': css('--surface'), 'text-halo-width': 1.6, 'text-halo-blur': 0.4,
  });

  function addOverlay() {
    const src = (id, data) => !map.getSource(id) && map.addSource(id, { type: 'geojson', data });
    src('countries', asset('/data/countries.geojson'));
    src('admin1', asset('/data/admin1.geojson'));
    src('districts', asset('/data/districts.geojson'));
    src('zones', zones);
    src('markets', asset('/data/markets.geojson'));
    src('fao-areas', asset('/data/fao_areas.geojson'));
    src('wfp-markets', asset('/data/wfp_markets.geojson'));

    // fills
    map.addLayer({ id: 'zones-fill', type: 'fill', source: 'zones',
      paint: { 'fill-color': zoneColor(zoneMetric, css), 'fill-opacity': zoneOpacity() } });
    map.addLayer({ id: 'gt-ipc', type: 'fill', source: 'districts',
      filter: ['all', ['==', ['get', 'country'], 'Guatemala'], ['has', ipcSource]],
      paint: { 'fill-color': gtIpcColor(ipcSource), 'fill-opacity': 0.9 } });
    // lines
    map.addLayer({ id: 'zones-line', type: 'line', source: 'zones',
      paint: { 'line-color': css('--zone-line'), 'line-width': ['interpolate', ['linear'], ['zoom'], 4, 0.6, 8, 1.2] } });
    map.addLayer({ id: 'districts-line', type: 'line', source: 'districts',
      paint: { 'line-color': css('--muted'), 'line-width': 0.4, 'line-opacity': 0.6 } });
    map.addLayer({ id: 'admin1-line', type: 'line', source: 'admin1',
      paint: { 'line-color': css('--muted'), 'line-width': 0.9, 'line-opacity': 0.8, 'line-dasharray': [4, 2] } });
    map.addLayer({ id: 'countries-line', type: 'line', source: 'countries',
      paint: { 'line-color': css('--text'), 'line-opacity': 0.85, 'line-width': countryWidth() } });
    // an FAO area's outline shows only while it is hovered or selected; the label is always there
    map.addLayer({ id: 'fao-areas-line', type: 'line', source: 'fao-areas', filter: faoAreaFilter(selectedFaoArea),
      paint: { 'line-color': css('--text'), 'line-width': 1.6, 'line-dasharray': [1, 1.5] } });
    map.addLayer({ id: 'zones-hover', type: 'line', source: 'zones', filter: ['==', ['get', 'fnid'], ''],
      paint: { 'line-color': css('--text'), 'line-width': 1.4 } });
    map.addLayer({ id: 'zones-selected', type: 'line', source: 'zones', filter: ['==', ['get', 'fnid'], selectedZone ?? ''],
      paint: { 'line-color': css('--accent'), 'line-width': 2.5 } });
    // points
    map.addLayer({ id: 'wfp-markets', type: 'circle', source: 'wfp-markets',
      paint: {
        'circle-color': css('--text'),
        'circle-opacity': ['case', ['==', ['get', 'country'], country], 0.6, 0.25],
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 1.2, 6, 2.2, 9, 3.5],
      } });
    map.addLayer({ id: 'markets', type: 'circle', source: 'markets',
      paint: {
        'circle-color': css('--surface'),
        'circle-stroke-color': css('--text'),
        'circle-stroke-width': 2,
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 3.5, 8, 6],
      } });
    // labels: FAO price series name the place their prices refer to
    map.addLayer({ id: 'markets-label', type: 'symbol', source: 'markets',
      layout: { 'text-field': ['get', 'region'], 'text-font': FONT, 'text-size': 12, 'text-offset': [0, 0.9], 'text-anchor': 'top',
        'text-optional': true },
      paint: labelPaint() });
    map.addLayer({ id: 'fao-areas-label', type: 'symbol', source: 'fao-areas', filter: ['!=', ['get', 'scope'], 'national average'],
      layout: { 'text-field': ['concat', ['get', 'region'], '\n', 'FAO prices, area'], 'text-font': FONT, 'text-size': 11,
        'symbol-placement': 'point', 'text-max-width': 12 },
      paint: labelPaint() });
    applyVisibility();
    updateRaster();
  }

  function applyVisibility() {
    if (!map?.getLayer('markets')) return;
    const vis = (id, on) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
    vis('zones-line', layers.zoneLines);
    vis('admin1-line', layers.admin1);
    vis('districts-line', layers.districts);
    vis('gt-ipc', layers.gtIpc && !isRaster());
    for (const id of ['markets', 'markets-label', 'fao-areas-line', 'fao-areas-label']) vis(id, layers.fao);
    vis('wfp-markets', layers.wfp);
  }

  // the 1 km travel-time surface: one image per country and measure, coloured from the CSS ramp
  let rasterToken = 0;
  async function updateRaster() {
    const m = ZONE_METRICS[zoneMetric];
    const token = ++rasterToken;
    if (!m.raster) {
      surface = null;
      if (map.getLayer('access-raster')) map.setLayoutProperty('access-raster', 'visibility', 'none');
      return;
    }
    const s = await loadSurface(country, m.raster);
    if (token !== rasterToken || !map?.getLayer('zones-line')) return;
    surface = s;
    if (!s) return;
    const url = colorize(s, m.bins, rampColors(m, css));
    const source = map.getSource('access');
    if (source) source.updateImage({ url, coordinates: s.coordinates });
    else map.addSource('access', { type: 'image', url, coordinates: s.coordinates });
    if (!map.getLayer('access-raster')) {
      map.addLayer({ id: 'access-raster', type: 'raster', source: 'access',
        paint: { 'raster-opacity': dark ? 0.88 : 0.92, 'raster-resampling': 'nearest', 'raster-fade-duration': 0 } }, 'zones-line');
    }
    map.setLayoutProperty('access-raster', 'visibility', 'visible');
  }

  function loadStyle() {
    ready = false;
    map.setStyle(layers.basemap && !basemapFailed ? basemapUrl(dark) : blankStyle());
  }

  function fit(duration = 600) {
    if (map && bounds[country]) map.fitBounds(bounds[country], { padding: 32, duration });
  }

  onMount(() => {
    map = new maplibregl.Map({
      container,
      style: layers.basemap ? basemapUrl(dark) : blankStyle(),
      center: [22, 6],
      zoom: 2.4,
      attributionControl: { compact: true },
    });
    if (import.meta.env.DEV) window.__map = map; // for debugging in the browser console
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl(), 'bottom-right');
    map.on('style.load', () => { addOverlay(); ready = true; });
    map.on('error', (e) => {
      if (!basemapFailed && String(e?.error?.message ?? '').match(/openfreemap|Failed to fetch|NetworkError/i)) {
        basemapFailed = true;
        map.setStyle(blankStyle());
      }
    });

    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: 'hover-popup' });
    const hoverable = () => ['markets', 'fao-areas-label', 'wfp-markets', 'gt-ipc', 'zones-fill'].filter((l) => map.getLayer(l));
    map.on('mousemove', (e) => {
      if (!ready) return;
      const f = map.queryRenderedFeatures(e.point, { layers: hoverable() })[0];
      map.getCanvas().style.cursor = f ? 'pointer' : '';
      map.setFilter('zones-hover', ['==', ['get', 'fnid'], f?.layer.id === 'zones-fill' ? f.properties.fnid : '']);
      const area = f?.layer.id === 'fao-areas-label' ? f.properties.region : null;
      if (area !== hoveredFaoArea) { hoveredFaoArea = area; map.setFilter('fao-areas-line', faoAreaFilter(selectedFaoArea, area)); }
      if (!f) return popup.remove();
      const p = f.properties;
      const m = ZONE_METRICS[zoneMetric];
      let html;
      if (f.layer.id === 'wfp-markets') html = `<strong>${p.market}</strong><span>WFP market · ${p.n_commodities} commodities · ${p.first}–${p.last}</span>`;
      else if (f.layer.id === 'markets') html = `<strong>${p.region}</strong><span>FAO prices for this town · ${p.n_series} series · ${p.first}–${p.last}</span>`;
      else if (f.layer.id === 'fao-areas-label') html = `<strong>${p.region}</strong><span>FAO prices for this area (${p.scope}) · ${p.n_series} series</span>`;
      else if (f.layer.id === 'gt-ipc') html = `<strong>${p.region}</strong><span>IPC phase ${p[ipcSource]}</span>`;
      else if (m.raster) {
        const here = sample(surface, e.lngLat.lng, e.lngLat.lat);
        const hereText = here === null ? 'No data here' : `${fmt(here / 60, { ...m, digits: here < 600 ? 1 : 0 })} from here`;
        html = `<strong>${hereText}</strong><span>${p.zone} · zone median ${fmt(p[zoneMetric], m)}</span>`;
      } else html = `<strong>${p.zone}</strong><span>${p.ipc_label ?? m.tab}: ${p.ipc_fill === null || p.ipc_fill === undefined ? 'no report' : fmt(p.ipc_fill, { ...m, digits: Number.isInteger(p.ipc_fill) ? 0 : 2 })}</span>`;
      popup.setLngLat(e.lngLat).setHTML(html).addTo(map);
    });
    map.on('mouseout', () => {
      popup.remove();
      if (map.getLayer('zones-hover')) map.setFilter('zones-hover', ['==', ['get', 'fnid'], '']);
    });
    map.on('click', (e) => {
      if (!ready) return;
      const f = map.queryRenderedFeatures(e.point, { layers: hoverable() })[0];
      if (!f) return onselectzone(null);
      if (f.layer.id === 'wfp-markets') onselectmarket({ layer: 'wfp', ...f.properties });
      else if (f.layer.id === 'markets') onselectmarket({ layer: 'fao-town', ...f.properties });
      else if (f.layer.id === 'fao-areas-label') onselectmarket({ layer: 'fao-area', ...f.properties });
      else if (f.layer.id === 'zones-fill') onselectzone(f.properties.fnid, f.properties.country);
    });

    fetch(asset('/data/countries.geojson')).then((r) => r.json()).then((gj) => {
      for (const f of gj.features) {
        const b = [Infinity, Infinity, -Infinity, -Infinity];
        const walk = (c) => (typeof c[0] === 'number'
          ? ((b[0] = Math.min(b[0], c[0])), (b[1] = Math.min(b[1], c[1])), (b[2] = Math.max(b[2], c[0])), (b[3] = Math.max(b[3], c[1])))
          : c.forEach(walk));
        walk(f.geometry.coordinates);
        bounds[f.properties.country] = [[b[0], b[1]], [b[2], b[3]]];
      }
      // the camera can be set before the style finishes loading, so fit now rather than waiting
      // for a 'load' event that may already have fired
      map.resize();
      fit(0);
    });

    return () => map.remove();
  });

  // reactive updates
  $effect(() => {
    const data = zones; // new properties (the IPC phase for the selected report) arrive as new data
    if (ready && map.getSource('zones')) map.getSource('zones').setData(data);
  });
  $effect(() => {
    layers.zoneLines; layers.admin1; layers.districts; layers.gtIpc; layers.fao; layers.wfp;
    if (ready) applyVisibility();
  });
  $effect(() => {
    const key = zoneMetric;
    country;
    if (!ready || !map.getLayer('zones-fill')) return;
    map.setPaintProperty('zones-fill', 'fill-color', zoneColor(key, css));
    map.setPaintProperty('zones-fill', 'fill-opacity', zoneOpacity());
    applyVisibility();
    updateRaster();
  });
  $effect(() => {
    const s = ipcSource;
    if (!ready || !map.getLayer('gt-ipc')) return;
    map.setFilter('gt-ipc', ['all', ['==', ['get', 'country'], 'Guatemala'], ['has', s]]);
    map.setPaintProperty('gt-ipc', 'fill-color', gtIpcColor(s));
  });
  $effect(() => {
    const a = selectedFaoArea;
    if (ready && map.getLayer('fao-areas-line')) map.setFilter('fao-areas-line', faoAreaFilter(a, hoveredFaoArea));
  });
  $effect(() => {
    const id = selectedZone ?? '';
    if (ready && map.getLayer('zones-selected')) map.setFilter('zones-selected', ['==', ['get', 'fnid'], id]);
  });
  // the first run with a map records the baseline; later runs react to changes
  let lastCountry = null;
  $effect(() => {
    const c = country;
    if (!map) return;
    if (ready && map.getLayer('countries-line')) {
      map.setPaintProperty('countries-line', 'line-width', countryWidth());
      map.setPaintProperty('wfp-markets', 'circle-opacity', ['case', ['==', ['get', 'country'], c], 0.6, 0.25]);
    }
    if (lastCountry === null) lastCountry = c;
    else if (c !== lastCountry) { lastCountry = c; fit(); }
  });
  let lastLook = null;
  $effect(() => {
    const look = `${dark}|${layers.basemap}`;
    if (!map) return;
    if (lastLook === null) lastLook = look;
    else if (look !== lastLook) { lastLook = look; loadStyle(); }
  });
</script>

<div class="map" bind:this={container} role="region" aria-label="Map of livelihood zones"></div>
{#if basemapFailed}<p class="note">Base map unavailable; showing boundaries only.</p>{/if}

<style>
  .map { position: absolute; inset: 0; }
  .note {
    position: absolute; right: 12px; bottom: 36px; padding: 4px 8px; border-radius: 4px;
    background: var(--surface); color: var(--muted); font-size: var(--fs-small);
  }
  :global(.hover-popup .maplibregl-popup-content) {
    display: grid; gap: 2px; background: var(--raised); color: var(--text);
    border-radius: 4px; padding: 7px 10px; font: 400 var(--fs-small) / 1.4 var(--font);
    box-shadow: var(--shadow); /* taste-skill-ignore: tooltip */
  }
  :global(.hover-popup .maplibregl-popup-content strong) { font-size: var(--fs-body); font-weight: 600; }
  :global(.hover-popup .maplibregl-popup-content span) { color: var(--muted); }
  :global(.hover-popup .maplibregl-popup-tip) { display: none; }
  :global(.maplibregl-ctrl-group) { background: var(--surface) !important; box-shadow: none !important; border: 1px solid var(--border); } /* taste-skill-ignore: removes MapLibre's shadow */
  :global(.maplibregl-ctrl-group button + button) { border-top: 1px solid var(--border) !important; }
  :global(.maplibregl-ctrl-scale) { background: color-mix(in srgb, var(--surface) 85%, transparent) !important; color: var(--muted) !important; border-color: var(--muted) !important; font-size: 11px; }
  :global(.maplibregl-ctrl-attrib) { background: color-mix(in srgb, var(--surface) 85%, transparent) !important; color: var(--muted); font-size: 11px; }
  :global(.maplibregl-ctrl-attrib a) { color: var(--muted) !important; }
</style>
