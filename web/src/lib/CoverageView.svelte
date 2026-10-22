<script>
  /** Which datasets exist for one country, and in which months: one table whose last column is the timeline. */
  let { coverage, country } = $props();

  let stripWidth = $state(600);
  let hover = $state(null);

  const months = $derived(coverage.months);
  const rows = $derived(
    coverage.datasets.map((d) => {
      const counts = coverage.counts[d.key][country];
      const idx = counts.map((n, i) => (n ? i : -1)).filter((i) => i >= 0);
      return {
        ...d,
        counts,
        rows: d.rows_by_country[country],
        first: idx.length ? months[idx[0]] : null,
        last: idx.length ? months[idx.at(-1)] : null,
        nMonths: idx.length,
      };
    }),
  );
  const covered = $derived(rows.filter((r) => r.rows));
  const missing = $derived(rows.filter((r) => !r.rows));
  const thin = $derived(covered.filter((r) => !r.annual && r.nMonths <= 2));
  const finding = $derived.by(() => {
    let s = `${covered.length} of ${rows.length} datasets cover ${country}.`;
    if (missing.length) s += ` Not covered: ${missing.map((r) => r.label).join(', ')}.`;
    if (thin.length) s += ` ${thin.map((r) => `${r.label} has ${r.nMonths === 1 ? 'a single month' : `${r.nMonths} months`}`).join('; ')}.`;
    return s;
  });

  const cellW = $derived(stripWidth / months.length);
  const yearStep = $derived(cellW * 12 >= 36 ? 1 : 2);
  const years = $derived(
    months.map((m, i) => ({ m, i })).filter(({ m }) => m.endsWith('-01') && Number(m.slice(0, 4)) % yearStep === 0),
  );
  const maxLog = $derived(Math.max(1, ...rows.flatMap((r) => r.counts).map((n) => Math.log10(n + 1))));
  // ink at an opacity that rises with the log row count; an empty month is the rule colour
  const opacity = (n) => 0.3 + 0.7 * (Math.log10(n + 1) / maxLog);
</script>

<section class="coverage" aria-labelledby="coverage-title">
  <header class="title-row">
    <h1 id="coverage-title">{country} data coverage</h1>
    <p class="finding">{finding}</p>
  </header>

  <div class="panel">
    <div class="grid head" aria-hidden="true">
      <span>Dataset</span>
      <span class="num">Rows</span>
      <span>Span</span>
      <div class="years" bind:clientWidth={stripWidth}>
        {#each years as { m, i }}<span style="left:{(i / months.length) * 100}%">{m.slice(0, 4)}</span>{/each}
      </div>
    </div>
    {#each rows as row}
      <div class="grid row" class:empty={!row.rows}>
        <span class="name">{row.label}<small>{row.group}</small></span>
        <span class="num">{row.rows ? row.rows.toLocaleString() : '—'}</span>
        <span class="span muted">{row.rows ? (row.first === row.last ? row.first : `${row.first} – ${row.last}`) : 'not covered'}</span>
        <svg class="strip" viewBox="0 0 {months.length} 1" preserveAspectRatio="none" role="img"
          aria-label="{row.label}: {row.nMonths} of {months.length} months covered">
          {#each row.counts as n, i}
            <rect x={i + 0.08} y="0" width="0.84" height="1" class:on={n} fill-opacity={n ? opacity(n) : 1}
              role="presentation"
              onmouseenter={(e) => (hover = { x: e.clientX, y: e.clientY, text: `${row.label} · ${months[i]} · ${n.toLocaleString()} rows` })}
              onmouseleave={() => (hover = null)} />
          {/each}
        </svg>
      </div>
    {/each}
  </div>
  <p class="note muted">Each cell is a month from {months[0]} to {months.at(-1)}; stronger ink means more rows. CPI is annual and fills each year's months.</p>
  {#if hover}<div class="tip" style="left:{hover.x + 12}px; top:{hover.y - 34}px">{hover.text}</div>{/if}
</section>

<style>
  .coverage { padding: var(--pad); display: grid; gap: var(--gap); align-content: start; max-width: 1400px; }
  .title-row { display: grid; gap: 6px; }
  h1 { font-size: var(--fs-title); line-height: 1.2; letter-spacing: -0.01em; }
  .finding { color: var(--muted); font-size: 14px; max-width: 80ch; }
  .panel { background: var(--surface); border-radius: var(--radius-card); padding: 8px 20px 12px; }
  .grid {
    display: grid; grid-template-columns: minmax(180px, 240px) 72px 150px minmax(0, 1fr);
    gap: 16px; align-items: center;
  }
  .head { height: 36px; color: var(--muted); font-size: var(--fs-small); }
  .row { min-height: 42px; border-top: 1px solid var(--rule); }
  .num { text-align: right; }
  .name { display: grid; line-height: 1.3; }
  .name small { color: var(--faint); font-size: 11px; }
  .row.empty .name { color: var(--muted); }
  .span { font-size: var(--fs-small); }
  .years { position: relative; height: 100%; }
  .years span { position: absolute; top: 50%; transform: translateY(-50%); }
  .strip { width: 100%; height: 18px; display: block; }
  .strip rect { fill: var(--rule); }
  .strip rect.on { fill: var(--text); }
  .strip rect:hover { fill: var(--accent); fill-opacity: 1; }
  .note { font-size: var(--fs-small); }
  .tip {
    position: fixed; pointer-events: none; white-space: nowrap; padding: 6px 9px; border-radius: 4px;
    background: var(--raised); color: var(--text); font-size: var(--fs-small); box-shadow: var(--shadow); z-index: 10; /* taste-skill-ignore: tooltip */
  }
  @media (max-width: 760px) {
    .coverage { padding: 16px; }
    .grid { grid-template-columns: minmax(0, 1fr) 64px; row-gap: 6px; }
    .head .years, .head span:nth-child(3) { display: none; }
    .span { grid-column: 1 / -1; order: 3; }
    .strip { grid-column: 1 / -1; order: 4; }
    .row { padding: 8px 0; }
  }
</style>
