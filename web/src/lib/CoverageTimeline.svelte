<script>
  /** Dataset x month heatmap of row counts for one country. */
  let { coverage, country } = $props();

  const ROW_H = 20, LABEL_W = 190, GAP = 2, TOP = 18;
  let width = $state(800);
  let hover = $state(null);

  const months = $derived(coverage.months);
  const cellW = $derived(Math.max(2, (width - LABEL_W - 8) / months.length));
  const rows = $derived(coverage.datasets.map((d) => ({ ...d, counts: coverage.counts[d.key][country] })));
  const years = $derived(months.map((m, i) => ({ m, i })).filter(({ m }) => m.endsWith('-01')));

  // log-binned one-hue ramp; empty months use the neutral step
  function fill(n) {
    if (!n) return 'var(--seq-0)';
    const b = Math.min(6, Math.floor(Math.log10(n) * 1.6));
    return `var(--seq-${b + 1})`;
  }
  const span = (counts) => {
    const idx = counts.map((c, i) => (c ? i : -1)).filter((i) => i >= 0);
    return idx.length ? `${months[idx[0]]} – ${months[idx.at(-1)]} · ${idx.length} months` : 'no data';
  };
</script>

<div class="wrap" bind:clientWidth={width}>
  <svg width={width} height={TOP + rows.length * ROW_H + 4} role="img" aria-label="Data coverage by month for {country}">
    {#each years as { m, i }}
      <text x={LABEL_W + i * cellW} y={12} class="year">{m.slice(0, 4)}</text>
      <line x1={LABEL_W + i * cellW} x2={LABEL_W + i * cellW} y1={TOP - 3} y2={TOP + rows.length * ROW_H} class="tick" />
    {/each}
    {#each rows as row, r}
      <text x={0} y={TOP + r * ROW_H + ROW_H / 2 + 4} class="label">{row.label}</text>
      {#each row.counts as n, i}
        <rect
          x={LABEL_W + i * cellW} y={TOP + r * ROW_H + GAP / 2}
          width={Math.max(1, cellW - (cellW > 4 ? 1 : 0))} height={ROW_H - GAP}
          rx={cellW > 6 ? 2 : 0} fill={fill(n)}
          role="presentation"
          onmouseenter={(e) => (hover = { x: e.offsetX, y: e.offsetY, text: `${row.label} · ${months[i]}: ${n.toLocaleString()} rows` })}
          onmouseleave={() => (hover = null)}
        />
      {/each}
    {/each}
  </svg>
  {#if hover}<div class="tip" style="left:{hover.x + 12}px; top:{hover.y - 28}px">{hover.text}</div>{/if}
  <table class="sr-only">
    <caption>Coverage for {country}</caption>
    <tbody>{#each rows as row}<tr><th>{row.label}</th><td>{span(row.counts)}</td></tr>{/each}</tbody>
  </table>
</div>

<style>
  .wrap { position: relative; width: 100%; min-width: 0; overflow: hidden; }
  svg { display: block; }
  .label { fill: var(--text-secondary); font-size: 12px; }
  .year { fill: var(--text-muted); font-size: 11px; }
  .tick { stroke: var(--border); stroke-width: 1; }
  rect:hover { stroke: var(--text-primary); stroke-width: 1; }
  .tip {
    position: absolute; pointer-events: none; white-space: nowrap; padding: 4px 8px; border-radius: 6px;
    background: var(--surface-1); color: var(--text-primary); border: 1px solid var(--border); font-size: 12px;
    box-shadow: 0 2px 8px rgb(0 0 0 / 0.15);
  }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style>
