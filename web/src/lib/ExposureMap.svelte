<script module>
  // share of a zone's people hit, in percent
  export const BINS = [
    { max: 0, label: 'None', ramp: '--ramp-0' },
    { max: 10, label: 'Under 10%', ramp: '--ramp-1' },
    { max: 25, label: '10–25%', ramp: '--ramp-2' },
    { max: 50, label: '25–50%', ramp: '--ramp-3' },
    { max: 75, label: '50–75%', ramp: '--ramp-4' },
    { max: 101, label: '75% or more', ramp: '--ramp-6' },
  ];
</script>

<script>
  import * as maplibregl from 'maplibre-gl';
  import { onMount } from 'svelte';
  import { asset } from './paths.js';

  maplibregl.setWorkerUrl(asset('/vendor/maplibre-gl-worker.mjs'));

  /**
   * Livelihood zones of one country, filled by the share of each zone's people affected by the chosen scenario.
   * `zones`: the zones GeoJSON; `stats`: { [fnid]: { pct, hit, pop, known, exposed } } for the chosen scenario.
   * Not exposed (the profile doesn't list the scenario's hazard): no fill. No breakdown: grey, dashed edge.
   */
  let { zones, stats, country, dark, selected = null, onselect } = $props();


  const basemapUrl = (isDark) => `https://tiles.openfreemap.org/styles/${isDark ? 'dark' : 'positron'}`;
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  let container;
  let map = null;
  let ready = $state(false);
  let hover = $state(null);

  const data = () => ({
    type: 'FeatureCollection',
    features: zones.features
      .filter((f) => f.properties.country === country)
      .map((f) => {
        const s = stats[f.properties.fnid];
        return { ...f, properties: { fnid: f.properties.fnid, zone: f.properties.zone, known: s?.known ? 1 : 0, exposed: s?.exposed === false ? 0 : 1, pct: s?.pct ?? 0 } };
      }),
  });

  const fillColor = () => {
    const step = ['step', ['get', 'pct'], css(BINS[0].ramp), 0.0001, css(BINS[1].ramp)];
    BINS.slice(2).forEach((b, i) => step.push(BINS[i + 1].max, css(b.ramp)));
    return ['case', ['==', ['get', 'exposed'], 0], 'rgba(0,0,0,0)', ['==', ['get', 'known'], 1], step, css('--raised')];
  };

  function addLayers() {
    if (map.getSource('exposure')) return;
    map.addSource('exposure', { type: 'geojson', data: data() });
    map.addLayer({ id: 'exp-fill', type: 'fill', source: 'exposure', paint: { 'fill-color': fillColor(), 'fill-opacity': 0.92 } });
    map.addLayer({ id: 'exp-line', type: 'line', source: 'exposure', paint: { 'line-color': css('--zone-line'), 'line-width': 0.8 } });
    map.addLayer({ id: 'exp-nodata', type: 'line', source: 'exposure', filter: ['all', ['==', ['get', 'known'], 0], ['==', ['get', 'exposed'], 1]],
      paint: { 'line-color': css('--muted'), 'line-width': 1, 'line-dasharray': [2, 2] } });
    map.addLayer({ id: 'exp-selected', type: 'line', source: 'exposure', filter: ['==', ['get', 'fnid'], selected ?? ''],
      paint: { 'line-color': css('--text'), 'line-width': 2.4 } });
    ready = true;
  }

  function fit() {
    const b = new maplibregl.LngLatBounds();
    for (const f of zones.features) {
      if (f.properties.country !== country) continue;
      const walk = (c) => (typeof c[0] === 'number' ? b.extend(c) : c.forEach(walk));
      walk(f.geometry.coordinates);
    }
    if (!b.isEmpty()) map.fitBounds(b, { padding: 24, duration: 0 });
  }

  onMount(() => {
    map = new maplibregl.Map({ container, style: basemapUrl(dark), attributionControl: { compact: true }, dragRotate: false });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.on('style.load', () => { ready = false; addLayers(); });
    map.on('load', fit);
    map.on('mousemove', 'exp-fill', (e) => {
      const p = e.features[0].properties;
      map.getCanvas().style.cursor = 'pointer';
      hover = { x: e.point.x, y: e.point.y, fnid: p.fnid, zone: p.zone };
    });
    map.on('mouseleave', 'exp-fill', () => { map.getCanvas().style.cursor = ''; hover = null; });
    map.on('click', (e) => {
      const f = map.queryRenderedFeatures(e.point, { layers: ['exp-fill'] })[0];
      onselect(f ? f.properties.fnid : null);
    });
    return () => map.remove();
  });

  // basemap follows the theme; layers are re-added on style.load
  let lastDark = dark;
  $effect(() => { if (map && dark !== lastDark) { lastDark = dark; map.setStyle(basemapUrl(dark)); } });
  $effect(() => { stats; country; if (ready) { map.getSource('exposure').setData(data()); map.setPaintProperty('exp-fill', 'fill-color', fillColor()); } });
  let lastCountry = country;
  $effect(() => { if (map && ready && country !== lastCountry) { lastCountry = country; fit(); } });
  $effect(() => { if (ready) map.setFilter('exp-selected', ['==', ['get', 'fnid'], selected ?? '']); });

  const M = (n) => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : `${n}`);
</script>

<div class="map" bind:this={container}>
  {#if hover}
    {@const s = stats[hover.fnid]}
    <div class="tip" style="left:{hover.x + 12}px; top:{hover.y + 12}px">
      <strong>{hover.zone}</strong>
      {#if s?.exposed === false}<span>Hazard not listed in profile</span>
      {:else if s?.known}<span>{M(s.hit)} of {M(s.pop)} people affected ({Math.round(s.pct)}%)</span>
      {:else}<span>No shares in profile</span>{/if}
    </div>
  {/if}
</div>

<style>
  .map { position: relative; width: 100%; height: 100%; min-height: 460px; border-radius: var(--radius-card); overflow: hidden; }
  .tip {
    position: absolute; pointer-events: none; display: grid; gap: 2px; padding: 6px 9px; border-radius: 4px; z-index: 5; /* taste-skill-ignore: tooltip */
    background: var(--raised); color: var(--text); font-size: var(--fs-small); box-shadow: var(--shadow); max-width: 260px;
  }
</style>
