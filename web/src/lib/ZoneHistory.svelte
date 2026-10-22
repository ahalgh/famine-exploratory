<script>
  /**
   * One zone's history on a shared monthly axis, as three small charts rather than one crowded one:
   * observed IPC (with what ML1 and ML2 had projected for each report date), a real staple-price index
   * at the zone's WFP markets, and national conflict. The selected report date is marked in all three.
   */
  import { colorCss } from './metrics.js';

  let { zone, history, country, asOf } = $props();

  const MONTHS = (() => {
    const out = [];
    for (let y = 2019; y <= 2026; y++) for (let m = 1; m <= 12; m++) out.push(`${y}-${String(m).padStart(2, '0')}`);
    return out.slice(0, out.indexOf('2026-09') + 1);
  })();
  const idx = new Map(MONTHS.map((m, i) => [m, i]));
  const label = (m) => new Date(`${m}-15`).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' });

  let width = $state(320);
  let hover = $state(null);
  const LEFT = 30, RIGHT = 8;
  const plotW = $derived(Math.max(120, width - LEFT - RIGHT));
  const x = (m) => LEFT + ((idx.get(m) ?? 0) + 0.5) / MONTHS.length * plotW;

  const h = $derived(history.zones[zone.fnid] ?? { obs: [], ml1: [], ml2: [], markets: [] });

  // IPC panel
  const IPC_H = 84, IPC_TOP = 6;
  const obs = $derived(h.obs.filter(([m]) => idx.has(m)));
  const maxPhase = $derived(Math.max(4, ...obs.map(([, p]) => p)));
  const yP = (p) => IPC_TOP + ((maxPhase - p) / (maxPhase - 1)) * (IPC_H - IPC_TOP - 8);
  const stepPath = $derived.by(() => {
    if (!obs.length) return '';
    let d = `M${x(obs[0][0])},${yP(obs[0][1])}`;
    for (let i = 1; i < obs.length; i++) d += `H${x(obs[i][0])}V${yP(obs[i][1])}`;
    return d;
  });
  // what each projection said for a report month: the latest issue whose window covers it
  function projected(list, m) {
    let best = null;
    for (const [issued, from, until, p] of list) if (from <= m && m <= until && issued <= m && (!best || issued > best[0])) best = [issued, p];
    return best ? best[1] : null;
  }
  const proj = $derived(obs.map(([m, p]) => ({ m, p, ml1: projected(h.ml1, m), ml2: projected(h.ml2, m) })));
  const misses = $derived(proj.filter((r) => r.ml2 !== null && r.ml2 !== r.p).length);
  const withMl2 = $derived(proj.filter((r) => r.ml2 !== null).length);

  // price panel
  const PRICE_H = 70;
  const markets = $derived(h.markets.map((m) => ({ ...m, ...history.markets[m.id] })).filter((m) => m.points).slice(0, 3));
  const priceRange = $derived.by(() => {
    const v = markets.flatMap((m) => m.points.map(([, y]) => y));
    if (!v.length) return [80, 120];
    return [Math.min(80, Math.floor(Math.min(...v) / 10) * 10), Math.max(120, Math.ceil(Math.max(...v) / 10) * 10)];
  });
  const yPrice = (v) => 4 + ((priceRange[1] - v) / (priceRange[1] - priceRange[0])) * (PRICE_H - 10);
  const linePath = (pts) => {
    let d = '', prev = -2;
    for (const [m, v] of pts) {
      const i = idx.get(m);
      if (i === undefined) continue;
      d += `${i === prev + 1 ? 'L' : 'M'}${x(m).toFixed(1)},${yPrice(v).toFixed(1)}`; // break the line over gaps
      prev = i;
    }
    return d;
  };

  // conflict panel
  const CONF_H = 40;
  const conflict = $derived((history.conflict[country] ?? []).filter(([m]) => idx.has(m)));
  const confMax = $derived(Math.max(1, ...conflict.map(([, e]) => e)));
  const barW = $derived(Math.max(1, plotW / MONTHS.length - 1));

  const years = [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026];

  function onmove(e) {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.floor(((e.clientX - r.left - LEFT) / plotW) * MONTHS.length);
    if (i < 0 || i >= MONTHS.length) return (hover = null);
    const m = MONTHS[i];
    const last = [...obs].reverse().find(([om]) => om <= m);
    hover = {
      m, x: x(m),
      ipc: last ? `Phase ${last[1]} (report ${label(last[0])})` : 'no report yet',
      prices: markets.map((mk) => ({ name: mk.name, v: mk.points.find(([pm]) => pm === m)?.[1] })),
      conflict: conflict.find(([cm]) => cm === m),
    };
  }
</script>

<section class="history" aria-label="History of {zone.zone}" bind:clientWidth={width}>
  <div class="panel-head">
    <h3>IPC phase</h3>
    <span class="key"><i class="k-obs"></i>observed <i class="k-ml1"></i>ML1 <i class="k-ml2"></i>ML2</span>
  </div>
  {#if obs.length}
    <svg width={width} height={IPC_H} role="img" aria-label="Observed IPC phase over time">
      {#each Array.from({ length: maxPhase }, (_, k) => k + 1) as p}
        <line x1={LEFT} x2={LEFT + plotW} y1={yP(p)} y2={yP(p)} class="grid" />
        <text x={LEFT - 8} y={yP(p) + 4} class="tick" text-anchor="end">{p}</text>
      {/each}
      {#if asOf !== 'mean' && idx.has(asOf)}<line x1={x(asOf)} x2={x(asOf)} y1="0" y2={IPC_H} class="asof" />{/if}
      <path d={stepPath} class="step" />
      {#each proj as r}
        {#if r.ml2 !== null}<rect x={x(r.m) - 4} y={yP(r.ml2) - 4} width="8" height="8" class="ml2" transform="rotate(45 {x(r.m)} {yP(r.ml2)})" />{/if}
        {#if r.ml1 !== null}<circle cx={x(r.m)} cy={yP(r.ml1)} r="5.5" class="ml1" />{/if}
        <circle cx={x(r.m)} cy={yP(r.p)} r="3.5" fill={colorCss('ipc_mean', r.p)} class="obs" />
      {/each}
      {#if hover}<line x1={hover.x} x2={hover.x} y1="0" y2={IPC_H} class="cursor" />{/if}
      <rect x={LEFT} y="0" width={plotW} height={IPC_H} fill="transparent" role="presentation" onmousemove={onmove} onmouseleave={() => (hover = null)} />
    </svg>
    {#if withMl2}<p class="note">ML2 differed from the observed phase in {misses} of {withMl2} reports.</p>{/if}
  {:else}
    <p class="empty">No zone-level IPC reports for this zone.</p>
  {/if}

  <div class="panel-head">
    <h3>Staple prices, real</h3>
    <span class="key">100 = the market's own average</span>
  </div>
  {#if markets.length}
    <svg width={width} height={PRICE_H} role="img" aria-label="Real staple price index at nearby WFP markets">
      {#each [priceRange[0], 100, priceRange[1]] as v}
        <line x1={LEFT} x2={LEFT + plotW} y1={yPrice(v)} y2={yPrice(v)} class={v === 100 ? 'ref' : 'grid'} />
        <text x={LEFT - 8} y={yPrice(v) + 4} class="tick" text-anchor="end">{v}</text>
      {/each}
      {#if asOf !== 'mean' && idx.has(asOf)}<line x1={x(asOf)} x2={x(asOf)} y1="0" y2={PRICE_H} class="asof" />{/if}
      {#each [...markets].reverse() as mk, k}
        <path d={linePath(mk.points)} class="price" class:lead={k === markets.length - 1} />
      {/each}
      {#if hover}<line x1={hover.x} x2={hover.x} y1="0" y2={PRICE_H} class="cursor" />{/if}
      <rect x={LEFT} y="0" width={plotW} height={PRICE_H} fill="transparent" role="presentation" onmousemove={onmove} onmouseleave={() => (hover = null)} />
    </svg>
    <ul class="market-key">
      {#each markets as mk, k}
        <li><i class:lead={k === 0}></i>{mk.name} <span class="muted">· {mk.series}{mk.km ? ` · ${mk.km} km away` : ' · in zone'}{mk.real ? '' : ' · nominal (no CPI)'}</span></li>
      {/each}
    </ul>
  {:else}
    <p class="empty">No WFP staple series near this zone.</p>
  {/if}

  {#if conflict.length}
  <div class="panel-head">
    <h3>Political violence, {country}</h3>
    <span class="key">events per month, national</span>
  </div>
  <svg width={width} height={CONF_H + 16} role="img" aria-label="Monthly political violence events in {country}">
    {#each conflict as [m, e]}
      <rect x={x(m) - barW / 2} y={CONF_H - (e / confMax) * (CONF_H - 4)} width={barW} height={(e / confMax) * (CONF_H - 4)} class="bar" />
    {/each}
    <text x={LEFT - 8} y="10" class="tick" text-anchor="end">{confMax}</text>
    <line x1={LEFT} x2={LEFT + plotW} y1={CONF_H} y2={CONF_H} class="base" />
    {#if asOf !== 'mean' && idx.has(asOf)}<line x1={x(asOf)} x2={x(asOf)} y1="0" y2={CONF_H} class="asof" />{/if}
    {#each years as y}<text x={x(`${y}-01`)} y={CONF_H + 13} class="tick">{y}</text>{/each}
    {#if hover}<line x1={hover.x} x2={hover.x} y1="0" y2={CONF_H} class="cursor" />{/if}
    <rect x={LEFT} y="0" width={plotW} height={CONF_H} fill="transparent" role="presentation" onmousemove={onmove} onmouseleave={() => (hover = null)} />
  </svg>
  {:else}
  <svg width={width} height="16" aria-hidden="true">
    {#each years as y}<text x={x(`${y}-01`)} y="12" class="tick">{y}</text>{/each}
  </svg>
  {/if}

  <div class="readout" aria-live="polite">
    {#if hover}
      <strong>{label(hover.m)}</strong>
      <span>IPC: {hover.ipc}</span>
      {#each hover.prices as p}<span>{p.name}: {p.v ?? '—'}</span>{/each}
      {#if conflict.length}<span>Political violence: {hover.conflict ? `${hover.conflict[1]} events, ${hover.conflict[2]} deaths` : '—'}</span>{/if}
    {:else}
      <span class="muted">Hover a chart to read every series at one month.</span>
    {/if}
  </div>
</section>

<style>
  .history { display: grid; gap: 4px; }
  .panel-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; margin-top: 8px; }
  h3 { font-size: var(--fs-small); font-weight: 600; }
  .key { font-size: 11px; color: var(--muted); display: inline-flex; align-items: center; gap: 4px; }
  .key i { display: inline-block; width: 8px; height: 8px; margin-left: 6px; }
  .k-obs { border-radius: 50%; background: var(--text); }
  .k-ml1 { border-radius: 50%; border: 1.5px solid var(--text); }
  .k-ml2 { border: 1.5px solid var(--muted); transform: rotate(45deg) scale(0.8); }
  svg { display: block; overflow: visible; }
  .grid { stroke: var(--rule); }
  .ref { stroke: var(--muted); stroke-dasharray: 3 3; }
  .base { stroke: var(--border); }
  .tick { fill: var(--faint); font-size: 11px; }
  .step { fill: none; stroke: var(--text); stroke-width: 1.5; }
  .obs { stroke: var(--surface); stroke-width: 1.5; }
  .ml1 { fill: none; stroke: var(--text); stroke-width: 1.2; opacity: 0.8; }
  .ml2 { fill: none; stroke: var(--muted); stroke-width: 1.2; }
  .price { fill: none; stroke: var(--muted); stroke-width: 1.2; opacity: 0.7; }
  .price.lead { stroke: var(--accent); stroke-width: 1.8; opacity: 1; }
  .bar { fill: var(--muted); opacity: 0.7; }
  .asof { stroke: var(--accent); stroke-width: 1; }
  .cursor { stroke: var(--text); stroke-width: 1; opacity: 0.35; }
  .note, .empty { font-size: 11px; color: var(--muted); }
  .market-key { list-style: none; margin: 2px 0 0; padding: 0; display: grid; gap: 1px; font-size: 11px; }
  .market-key i { display: inline-block; width: 10px; height: 2px; background: var(--muted); vertical-align: middle; margin-right: 6px; }
  .market-key i.lead { background: var(--accent); height: 2px; }
  .readout { display: grid; gap: 1px; font-size: 11px; min-height: 70px; padding-top: 6px; border-top: 1px solid var(--rule); margin-top: 6px; }
  .readout strong { font-size: var(--fs-small); }
</style>
