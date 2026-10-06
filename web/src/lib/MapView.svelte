<script>
  import * as maplibregl from 'maplibre-gl';
  import { onMount } from 'svelte';

  /** @type {{ layers: Record<string, boolean>, ipcSource: string, basemap: boolean, selectedCountry: string | null, onselect: (sel: any) => void }} */
  let { layers, ipcSource, basemap, selectedCountry, onselect } = $props();

  const BASEMAP_URL = 'https://tiles.openfreemap.org/styles/positron';
  let container;
  let map = $state(null);
  let ready = $state(false);
  let basemapFailed = $state(false);

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const isDark = () => matchMedia('(prefers-color-scheme: dark)').matches;

  function blankStyle() {
    return {
      version: 8,
      sources: {},
      layers: [{ id: 'background', type: 'background', paint: { 'background-color': css('--surface-0') } }],
    };
  }

  function seqStep(prop) {
    // 0..8 datasets -> one-hue sequential ramp
    return ['step', ['get', prop], css('--seq-0'), 1, css('--seq-1'), 3, css('--seq-2'), 5, css('--seq-4'), 7, css('--seq-6')];
  }

  function addOverlay() {
    const src = (id, url) => !map.getSource(id) && map.addSource(id, { type: 'geojson', data: url });
    src('countries', '/data/countries.geojson');
    src('admin1', '/data/admin1.geojson');
    src('districts', '/data/districts.geojson');
    if (!map.getSource('markets')) map.addSource('markets', { type: 'geojson', data: '/data/markets.geojson' });

    map.addLayer({ id: 'countries-fill', type: 'fill', source: 'countries',
      paint: { 'fill-color': seqStep('n_datasets'), 'fill-opacity': 0.55 } });
    map.addLayer({ id: 'gt-ipc', type: 'fill', source: 'districts',
      filter: ['all', ['==', ['get', 'country'], 'Guatemala'], ['has', ipcSource]],
      paint: { 'fill-color': ipcColor(ipcSource), 'fill-opacity': 0.9, 'fill-outline-color': css('--surface-1') } });
    map.addLayer({ id: 'districts-line', type: 'line', source: 'districts',
      paint: { 'line-color': css('--text-muted'), 'line-width': 0.3, 'line-opacity': 0.6 } });
    map.addLayer({ id: 'admin1-line', type: 'line', source: 'admin1',
      paint: { 'line-color': css('--text-secondary'), 'line-width': 0.8, 'line-opacity': 0.8 } });
    map.addLayer({ id: 'countries-line', type: 'line', source: 'countries',
      paint: { 'line-color': css('--text-primary'), 'line-width': ['case', ['==', ['get', 'country'], selectedCountry ?? ''], 2.5, 1.2] } });
    map.addLayer({ id: 'markets', type: 'circle', source: 'markets',
      paint: {
        'circle-color': ['match', ['get', 'kind'], 'town', css('--series-1'), 'admin1', css('--series-2'), 'aggregate', css('--series-3'), css('--text-muted')],
        'circle-radius': ['interpolate', ['linear'], ['sqrt', ['coalesce', ['get', 'n_rows'], 1]], 1, 4, 35, 11],
        'circle-stroke-color': css('--surface-1'),
        'circle-stroke-width': 2,
      } });
    applyVisibility();
  }

  function ipcColor(prop) {
    return ['match', ['to-number', ['get', prop]], 1, css('--ipc-1'), 2, css('--ipc-2'), 3, css('--ipc-3'), 4, css('--ipc-4'), 5, css('--ipc-5'), css('--text-muted')];
  }

  function applyVisibility() {
    if (!map || !map.getLayer('markets')) return;
    const vis = (id, on) => map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
    vis('countries-fill', layers.coverage);
    vis('admin1-line', layers.admin1);
    vis('districts-line', layers.districts);
    vis('gt-ipc', layers.ipc);
    vis('markets', layers.markets);
  }

  function loadStyle(useBasemap) {
    const style = useBasemap && !isDark() && !basemapFailed ? BASEMAP_URL : blankStyle();
    map.setStyle(style);
  }

  onMount(() => {
    map = new maplibregl.Map({
      container,
      style: basemap && !isDark() ? BASEMAP_URL : blankStyle(),
      center: [22, 6],
      zoom: 2.4,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl(), 'bottom-right');

    map.on('style.load', () => { addOverlay(); ready = true; });
    map.on('error', (e) => {
      // basemap unreachable (offline, blocked): fall back to plain background
      if (!basemapFailed && String(e?.error?.message ?? '').match(/openfreemap|Failed to fetch|NetworkError/i)) {
        basemapFailed = true;
        map.setStyle(blankStyle());
      }
    });

    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10, className: 'hover-popup' });
    const hoverable = ['markets', 'gt-ipc', 'countries-fill'];
    map.on('mousemove', (e) => {
      const f = map.queryRenderedFeatures(e.point, { layers: hoverable.filter((l) => map.getLayer(l)) })[0];
      map.getCanvas().style.cursor = f ? 'pointer' : '';
      if (!f) return popup.remove();
      const p = f.properties;
      let html;
      if (f.layer.id === 'markets') html = `<b>${p.region}</b>, ${p.country}<br>${p.kind} · ${p.n_series} series · ${p.first}–${p.last}`;
      else if (f.layer.id === 'gt-ipc') html = `<b>${p.region}</b><br>IPC phase ${p[ipcSource]}`;
      else html = `<b>${p.country}</b><br>${p.n_datasets} of 8 datasets`;
      popup.setLngLat(e.lngLat).setHTML(html).addTo(map);
    });
    map.on('mouseout', () => popup.remove());

    map.on('click', (e) => {
      const f = map.queryRenderedFeatures(e.point, { layers: hoverable.filter((l) => map.getLayer(l)) })[0];
      if (!f) return;
      if (f.layer.id === 'markets') onselect({ type: 'market', ...f.properties });
      else onselect({ type: 'country', country: f.properties.country });
    });

    const mq = matchMedia('(prefers-color-scheme: dark)');
    const onScheme = () => loadStyle(basemap);
    mq.addEventListener('change', onScheme);
    return () => { mq.removeEventListener('change', onScheme); map.remove(); };
  });

  $effect(() => { layers.coverage; layers.admin1; layers.districts; layers.ipc; layers.markets; if (ready) applyVisibility(); });
  $effect(() => {
    if (!ready || !map.getLayer('gt-ipc')) return;
    map.setFilter('gt-ipc', ['all', ['==', ['get', 'country'], 'Guatemala'], ['has', ipcSource]]);
    map.setPaintProperty('gt-ipc', 'fill-color', ipcColor(ipcSource));
  });
  $effect(() => {
    if (!ready || !map.getLayer('countries-line')) return;
    map.setPaintProperty('countries-line', 'line-width', ['case', ['==', ['get', 'country'], selectedCountry ?? ''], 2.5, 1.2]);
  });
  // zoom to the selected country
  let bounds = {};
  onMount(async () => {
    const gj = await (await fetch('/data/countries.geojson')).json();
    for (const f of gj.features) {
      const b = [Infinity, Infinity, -Infinity, -Infinity];
      const walk = (c) => (typeof c[0] === 'number'
        ? (b[0] = Math.min(b[0], c[0]), b[1] = Math.min(b[1], c[1]), b[2] = Math.max(b[2], c[0]), b[3] = Math.max(b[3], c[1]))
        : c.forEach(walk));
      walk(f.geometry.coordinates);
      bounds[f.properties.country] = [[b[0], b[1]], [b[2], b[3]]];
    }
    fitInitial();
  });
  function fitInitial() {
    if (!map || !selectedCountry || !bounds[selectedCountry]) return;
    const fit = () => { map.resize(); map.fitBounds(bounds[selectedCountry], { padding: 40, duration: 0 }); };
    if (map.loaded()) requestAnimationFrame(fit);
    else map.once('load', fit);
    lastCountry = selectedCountry;
  }
  let lastCountry = null;
  $effect(() => {
    if (map && selectedCountry && selectedCountry !== lastCountry && bounds[selectedCountry]) {
      lastCountry = selectedCountry;
      map.fitBounds(bounds[selectedCountry], { padding: 40, duration: 600 });
    }
  });

  let lastBasemap = basemap;
  $effect(() => { if (map && basemap !== lastBasemap) { lastBasemap = basemap; ready = false; loadStyle(basemap); } });
</script>

<div class="map" bind:this={container}></div>
{#if basemapFailed}<div class="note">Base map unavailable, showing boundaries only</div>{/if}

<style>
  .map { position: absolute; inset: 0; }
  .note {
    position: absolute; left: 12px; bottom: 12px; padding: 4px 8px; border-radius: 6px;
    background: var(--surface-1); color: var(--text-secondary); border: 1px solid var(--border); font-size: 12px;
  }
  :global(.hover-popup .maplibregl-popup-content) {
    background: var(--surface-1); color: var(--text-primary); border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 9px; font-size: 12px; box-shadow: 0 2px 8px rgb(0 0 0 / 0.15);
  }
  :global(.hover-popup .maplibregl-popup-tip) { display: none; }
</style>
