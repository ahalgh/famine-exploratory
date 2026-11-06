<script>
  import * as maplibregl from 'maplibre-gl';
  import { onMount } from 'svelte';
  import { asset } from './paths.js';
  import { FILLS, fillColor } from './fills.js';

  maplibregl.setWorkerUrl(asset('/vendor/maplibre-gl-worker.mjs'));

  /**
   * Every unit system drawn as lines in its own colour and style, so overlaps read directly; one
   * optional fill on the HFID units shows how well they fit the others.
   */
  let { country, layers, fill, dark, selected, onselect } = $props();

  const GLYPHS = 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf';
  const FONT = ['Noto Sans Regular'];
  const basemapUrl = (d) => `https://tiles.openfreemap.org/styles/${d ? 'dark' : 'positron'}`;
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  let container;
  let map = $state(null);
  let ready = $state(false);
  let failed = false;
  let bounds = {};

  const inCountry = () => ['==', ['get', 'country'], country];
  // the market whose catchment is highlighted: a selected market or catchment of that source
  const selMarket = (source) => (selected?.kind === 'market' && selected.source === source ? selected.market : '');
  const blank = () => ({ version: 8, glyphs: GLYPHS, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': css('--ground') } }] });

  function addLayers() {
    const src = (id, file) => !map.getSource(id) && map.addSource(id, { type: 'geojson', data: asset(`/data/${file}.geojson`) });
    ['countries', 'admin1', 'admin2', 'zones', 'hfid', 'smap_grid', 'fao_towns', 'fao_areas', 'wfp_markets', 'catchments_wfp', 'catchments_fao', 'catchments_fao_road'].forEach((f) => src(f, f));

    map.addLayer({ id: 'hfid-fill', type: 'fill', source: 'hfid', filter: inCountry(),
      paint: { 'fill-color': fillColor(fill, css), 'fill-opacity': fill === 'none' ? 0 : 0.75 } });
    map.addLayer({ id: 'smap', type: 'line', source: 'smap_grid', filter: inCountry(),
      paint: { 'line-color': css('--sys-smap'), 'line-width': 0.9, 'line-opacity': 0.9 } });
    map.addLayer({ id: 'admin2', type: 'line', source: 'admin2', filter: inCountry(),
      paint: { 'line-color': css('--sys-admin'), 'line-width': 0.7, 'line-dasharray': [1, 1.5] } });
    map.addLayer({ id: 'hfid-line', type: 'line', source: 'hfid', filter: inCountry(),
      paint: { 'line-color': css('--sys-hfid'), 'line-width': 0.6, 'line-opacity': 0.75 } });
    map.addLayer({ id: 'admin1', type: 'line', source: 'admin1', filter: inCountry(),
      paint: { 'line-color': css('--sys-admin'), 'line-width': 1.6, 'line-dasharray': [4, 2] } });
    map.addLayer({ id: 'zones', type: 'line', source: 'zones', filter: inCountry(),
      paint: { 'line-color': css('--sys-zone'), 'line-width': 2.2 } });
    map.addLayer({ id: 'countries', type: 'line', source: 'countries',
      paint: { 'line-color': css('--text'), 'line-width': ['case', inCountry(), 1.8, 0.7], 'line-opacity': 0.9 } });
    // price catchments: the area each market's price stands in for (nearest market in a straight line)
    map.addLayer({ id: 'catch-wfp-fill', type: 'fill', source: 'catchments_wfp', filter: inCountry(),
      paint: { 'fill-color': css('--sys-price'), 'fill-opacity': ['case', ['==', ['get', 'market'], selMarket('wfp')], 0.28, 0] } });
    map.addLayer({ id: 'catch-fao-fill', type: 'fill', source: 'catchments_fao', filter: inCountry(),
      paint: { 'fill-color': css('--sys-price'), 'fill-opacity': ['case', ['==', ['get', 'market'], selMarket('fao')], 0.28, 0] } });
    map.addLayer({ id: 'catch-faoroad-fill', type: 'fill', source: 'catchments_fao_road', filter: inCountry(),
      paint: { 'fill-color': css('--sys-price'), 'fill-opacity': ['case', ['==', ['get', 'market'], selMarket('fao')], 0.28, 0] } });
    map.addLayer({ id: 'catch-wfp', type: 'line', source: 'catchments_wfp', filter: inCountry(),
      paint: { 'line-color': css('--sys-price'), 'line-width': 1, 'line-opacity': 0.8 } });
    map.addLayer({ id: 'catch-fao', type: 'line', source: 'catchments_fao', filter: inCountry(),
      paint: { 'line-color': css('--sys-price'), 'line-width': 1.8 } });
    map.addLayer({ id: 'catch-faoroad', type: 'line', source: 'catchments_fao_road', filter: inCountry(),
      paint: { 'line-color': css('--sys-price'), 'line-width': 2.2, 'line-dasharray': [2.5, 1.5] } });
    map.addLayer({ id: 'selected', type: 'line', source: 'hfid', filter: ['==', ['get', 'hfid'], ''],
      paint: { 'line-color': css('--accent'), 'line-width': 3 } });
    map.addLayer({ id: 'selected-zone', type: 'line', source: 'zones', filter: ['==', ['get', 'fnid'], ''],
      paint: { 'line-color': css('--accent'), 'line-width': 3 } });
    map.addLayer({ id: 'fao-areas', type: 'line', source: 'fao_areas', filter: inCountry(),
      paint: { 'line-color': css('--sys-price'), 'line-width': 1.8, 'line-dasharray': [1, 1.5] } });
    map.addLayer({ id: 'wfp', type: 'circle', source: 'wfp_markets', filter: inCountry(),
      paint: { 'circle-color': css('--sys-price'), 'circle-opacity': 0.9, 'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 1.8, 9, 4] } });
    map.addLayer({ id: 'fao', type: 'circle', source: 'fao_towns', filter: inCountry(),
      paint: { 'circle-color': css('--surface'), 'circle-stroke-color': css('--sys-price'), 'circle-stroke-width': 2.5,
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 4, 9, 7] } });
    map.addLayer({ id: 'fao-label', type: 'symbol', source: 'fao_towns', filter: inCountry(),
      layout: { 'text-field': ['get', 'region'], 'text-font': FONT, 'text-size': 11, 'text-offset': [0, 0.9], 'text-anchor': 'top' },
      paint: { 'text-color': css('--text'), 'text-halo-color': css('--surface'), 'text-halo-width': 1.5 } });
    map.addLayer({ id: 'fao-areas-label', type: 'symbol', source: 'fao_areas', filter: inCountry(),
      layout: { 'text-field': ['concat', ['get', 'region'], '\n(FAO area)'], 'text-font': FONT, 'text-size': 11 },
      paint: { 'text-color': css('--text'), 'text-halo-color': css('--surface'), 'text-halo-width': 1.5 } });
    applyLayers();
  }

  function applyLayers() {
    if (!map?.getLayer('fao')) return;
    const vis = (id, on) => map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
    vis('hfid-line', layers.hfid);
    vis('zones', layers.zones);
    vis('admin1', layers.admin1);
    vis('admin2', layers.admin2);
    vis('smap', layers.smap);
    for (const id of ['fao', 'fao-label', 'fao-areas', 'fao-areas-label']) vis(id, layers.fao);
    vis('wfp', layers.wfp);
    for (const id of ['catch-wfp', 'catch-wfp-fill']) vis(id, layers.wfpCatch);
    for (const id of ['catch-fao', 'catch-fao-fill']) vis(id, layers.faoCatch);
    for (const id of ['catch-faoroad', 'catch-faoroad-fill']) vis(id, layers.faoRoadCatch);
  }

  function applyCountry() {
    if (!map?.getLayer('fao')) return;
    for (const id of ['hfid-fill', 'smap', 'admin2', 'hfid-line', 'admin1', 'zones', 'fao-areas', 'wfp', 'fao', 'fao-label', 'fao-areas-label', 'catch-wfp', 'catch-wfp-fill', 'catch-fao', 'catch-fao-fill', 'catch-faoroad', 'catch-faoroad-fill']) {
      map.setFilter(id, inCountry());
    }
    map.setPaintProperty('countries', 'line-width', ['case', inCountry(), 1.8, 0.7]);
  }

  const fit = (duration = 600) => bounds[country] && map.fitBounds(bounds[country], { padding: 28, duration });

  onMount(() => {
    map = new maplibregl.Map({ container, style: basemapUrl(dark), center: [22, 6], zoom: 2.4, attributionControl: { compact: true } });
    if (import.meta.env.DEV) window.__map = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl(), 'bottom-right');
    map.on('style.load', () => { addLayers(); ready = true; });
    map.on('error', (e) => {
      if (!failed && /openfreemap|Failed to fetch|NetworkError/i.test(String(e?.error?.message ?? ''))) { failed = true; map.setStyle(blank()); }
    });

    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: 'hover-popup' });
    const hit = () => ['fao', 'wfp', 'fao-areas-label', 'hfid-fill', 'zones', 'catch-fao-fill', 'catch-faoroad-fill', 'catch-wfp-fill'].filter((l) => map.getLayer(l) && map.getLayoutProperty(l, 'visibility') !== 'none');
    map.on('mousemove', (e) => {
      const f = map.queryRenderedFeatures(e.point, { layers: hit() })[0];
      map.getCanvas().style.cursor = f ? 'pointer' : '';
      if (!f) return popup.remove();
      const p = f.properties;
      const html = {
        fao: () => `<strong>${p.region}</strong><span>FAO price series, town</span>`,
        wfp: () => `<strong>${p.market}</strong><span>WFP market</span>`,
        'fao-areas-label': () => `<strong>${p.region}</strong><span>FAO price series priced over an area (${p.scope})</span>`,
        'hfid-fill': () => `<strong>${p.admin2 || p.admin1}</strong><span>HFID unit · ${p.admin1} · ${Number(p.smap_cells).toFixed(2)} SMAP cells</span>`,
        zones: () => `<strong>${p.zone}</strong><span>Livelihood zone ${p.fnid}</span>`,
        'catch-wfp-fill': () => `<strong>${p.market}</strong><span>Nearest WFP price market · ${Number(p.area_km2).toLocaleString()} km² · median ${p.median_km} km away</span>`,
        'catch-fao-fill': () => `<strong>${p.market}</strong><span>Nearest FAO price market (straight line) · ${Number(p.area_km2).toLocaleString()} km² · median ${p.median_km} km away</span>`,
        'catch-faoroad-fill': () => `<strong>${p.market}</strong><span>Nearest FAO price market (road time) · ${Number(p.area_km2).toLocaleString()} km² · median ${p.median_h} h by road</span>`,
      }[f.layer.id]();
      popup.setLngLat(e.lngLat).setHTML(html).addTo(map);
    });
    map.on('mouseout', () => popup.remove());
    map.on('click', (e) => {
      const visible = (l) => map.getLayer(l) && map.getLayoutProperty(l, 'visibility') !== 'none';
      const f = map.queryRenderedFeatures(e.point, { layers: ['fao', 'wfp', 'catch-fao-fill', 'catch-faoroad-fill', 'catch-wfp-fill', 'hfid-fill', 'zones'].filter(visible) })[0];
      if (!f) return onselect(null);
      const p = f.properties;
      if (f.layer.id === 'fao') onselect({ kind: 'market', source: 'fao', market: p.region, country: p.country });
      else if (f.layer.id === 'wfp') onselect({ kind: 'market', source: 'wfp', market: p.market, country: p.country });
      else if (f.layer.id.startsWith('catch-')) onselect({ kind: 'market', ...p });
      else onselect({ kind: f.layer.id === 'zones' ? 'zone' : 'hfid', ...p });
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
      map.resize();
      fit(0);
    });
    return () => map.remove();
  });

  $effect(() => { layers.hfid; layers.zones; layers.admin1; layers.admin2; layers.smap; layers.fao; layers.wfp; layers.wfpCatch; layers.faoCatch; layers.faoRoadCatch; if (ready) applyLayers(); });
  $effect(() => {
    const f = fill;
    if (!ready || !map.getLayer('hfid-fill')) return;
    map.setPaintProperty('hfid-fill', 'fill-color', fillColor(f, css));
    map.setPaintProperty('hfid-fill', 'fill-opacity', f === 'none' ? 0 : 0.75);
  });
  $effect(() => {
    const s = selected;
    if (!ready || !map.getLayer('selected')) return;
    map.setFilter('selected', ['==', ['get', 'hfid'], s?.kind === 'hfid' ? s.hfid : '']);
    map.setFilter('selected-zone', ['==', ['get', 'fnid'], s?.kind === 'zone' ? s.fnid : '']);
    for (const [layer, source] of [['wfp', 'wfp'], ['fao', 'fao'], ['faoroad', 'fao']]) {
      map.setPaintProperty(`catch-${layer}-fill`, 'fill-opacity', ['case', ['==', ['get', 'market'], selMarket(source)], 0.28, 0]);
    }
  });
  let lastCountry = null;
  $effect(() => {
    const c = country;
    if (!map) return;
    if (ready) applyCountry();
    if (lastCountry === null) lastCountry = c;
    else if (c !== lastCountry) { lastCountry = c; fit(); }
  });
  let lastDark = null;
  $effect(() => {
    const d = dark;
    if (!map) return;
    if (lastDark === null) lastDark = d;
    else if (d !== lastDark) { lastDark = d; ready = false; map.setStyle(failed ? blank() : basemapUrl(d)); }
  });
</script>

<div class="map" bind:this={container} role="region" aria-label="Map of unit boundaries"></div>

<style>
  .map { position: absolute; inset: 0; }
  :global(.hover-popup .maplibregl-popup-content) {
    display: grid; gap: 2px; background: var(--raised); color: var(--text); border-radius: 4px; padding: 7px 10px;
    font: 400 var(--fs-small) / 1.4 var(--font); box-shadow: var(--shadow); /* taste-skill-ignore: tooltip */
  }
  :global(.hover-popup .maplibregl-popup-content strong) { font-size: var(--fs-body); font-weight: 600; }
  :global(.hover-popup .maplibregl-popup-content span) { color: var(--muted); }
  :global(.hover-popup .maplibregl-popup-tip) { display: none; }
  :global(.maplibregl-ctrl-group) { background: var(--surface) !important; box-shadow: none !important; border: 1px solid var(--border); } /* taste-skill-ignore: removes MapLibre's shadow */
  :global(.maplibregl-ctrl-attrib), :global(.maplibregl-ctrl-scale) { background: color-mix(in srgb, var(--surface) 85%, transparent) !important; color: var(--muted) !important; font-size: 11px; }
  :global(.maplibregl-ctrl-attrib a) { color: var(--muted) !important; }
</style>
