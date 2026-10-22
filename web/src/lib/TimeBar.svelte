<script>
  /**
   * Picks which FEWS report the map shows. Each report is a column whose height is the share of the
   * country's zones at IPC phase 3 or worse, so the bar is also a small chart of when things were bad.
   * `asOf` is a report month ('YYYY-MM') or 'mean' for the average of every report since 2020.
   */
  let { dates, shares, asOf, onchange } = $props();

  const FIRST = '2019-01';
  const LAST = '2026-09';
  const toIndex = (m) => (Number(m.slice(0, 4)) - 2019) * 12 + Number(m.slice(5, 7)) - 1;
  const span = toIndex(LAST) - toIndex(FIRST) + 1;
  const x = (m) => ((toIndex(m) + 0.5) / span) * 100;
  const years = Array.from({ length: 8 }, (_, i) => 2019 + i);
  const label = (m) => new Date(`${m}-15`).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' });

  const i = $derived(dates.indexOf(asOf));
  const step = (d) => {
    if (asOf === 'mean') return onchange(d > 0 ? dates[0] : dates.at(-1));
    const j = Math.min(dates.length - 1, Math.max(0, i + d));
    onchange(dates[j]);
  };
  function onkey(e) {
    if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
    if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
  }
</script>

<div class="timebar">
  <div class="controls">
    <button class="chip" class:active={asOf === 'mean'} aria-pressed={asOf === 'mean'} onclick={() => onchange('mean')}>Mean since 2020</button>
    <button class="arrow" aria-label="Previous report" disabled={asOf !== 'mean' && i <= 0} onclick={() => step(-1)}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 6-6 6 6 6" /></svg>
    </button>
    <span class="current num" aria-live="polite">{asOf === 'mean' ? `${dates.length} reports` : `${label(asOf)} report`}</span>
    <button class="arrow" aria-label="Next report" disabled={asOf !== 'mean' && i >= dates.length - 1} onclick={() => step(1)}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6" /></svg>
    </button>
  </div>
  <div class="track" role="listbox" tabindex="0" aria-label="FEWS report date" onkeydown={onkey}>
    {#each years as y}
      <span class="year" style="left: {x(`${y}-01`) - (0.5 / span) * 100}%">{y}</span>
    {/each}
    {#each dates as d}
      {@const share = shares[d] ?? 0}
      <button role="option" aria-selected={d === asOf} class="col" class:on={d === asOf} style="left: {x(d)}%"
        title="{label(d)}: {Math.round(share * 100)}% of zones at phase 3+" onclick={() => onchange(d)}>
        <i style="height: {Math.max(2, share * 26)}px"></i>
      </button>
    {/each}
  </div>
</div>

<style>
  .timebar { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 16px; align-items: end; padding: 10px 2px 0; }
  .controls { display: flex; align-items: center; gap: 4px; padding-bottom: 2px; }
  .chip {
    height: 26px; padding: 0 10px; border-radius: 999px; border: 1px solid var(--control); background: none;
    color: var(--muted); font-size: var(--fs-small); margin-right: 6px;
  }
  .chip.active { color: var(--text); border-color: var(--accent); }
  .arrow { width: 26px; height: 26px; display: grid; place-items: center; border: 0; border-radius: 4px; background: none; color: var(--muted); }
  .arrow:hover:not(:disabled) { color: var(--text); background: var(--raised); }
  .arrow:disabled { opacity: 0.35; cursor: default; }
  .arrow svg { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 2; }
  .current { min-width: 92px; text-align: center; font-size: var(--fs-small); }
  .track { position: relative; height: 44px; border-bottom: 1px solid var(--border); outline-offset: 4px; }
  .year { position: absolute; top: 0; font-size: 11px; color: var(--faint); padding-left: 3px; border-left: 1px solid var(--rule); height: 44px; }
  .col {
    position: absolute; bottom: 0; transform: translateX(-50%); width: 14px; height: 32px; border: 0; padding: 0;
    background: none; display: flex; align-items: flex-end; justify-content: center;
  }
  .col i { display: block; width: 6px; border-radius: 1px 1px 0 0; background: var(--muted); transition: background-color 150ms var(--ease-out); }
  .col:hover i { background: var(--text); }
  .col.on i { background: var(--accent); }
  .col.on::after { content: ''; position: absolute; bottom: -1px; left: 2px; right: 2px; height: 1px; background: var(--accent); }
  @media (max-width: 760px) {
    .timebar { grid-template-columns: 1fr; gap: 6px; }
  }
</style>
