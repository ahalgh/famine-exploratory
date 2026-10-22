// Zone metrics: one definition drives the map colours, the legend, the tabs and the ranked list.
// Travel times use the one-hue ramp (--ramp-1..6, more remote = more ink); IPC uses the official IPC
// phase colours. Every metric ranks "worse" first: higher IPC, longer travel.

export const ZONE_METRICS = {
  ipc_mean: {
    tab: 'Mean IPC',
    list: 'Zones by mean IPC',
    label: 'Mean observed IPC phase since 2020',
    unit: '',
    digits: 2,
    ipc: true,
    note: 'FEWS NET current situation, averaged over every report since 2020.',
  },
  city_motorized_median_h: {
    tab: 'To a city by road',
    list: 'Zones by road time to a city',
    label: 'Travel time to a city of 50,000+, by road',
    unit: 'h',
    digits: 1,
    bins: [0.5, 1, 2, 4, 8],
    note: 'Median over the zone on the MAP 2019 friction surface. Ranks zones well; absolute times are optimistic.',
  },
  city_walking_median_h: {
    tab: 'To a city on foot',
    list: 'Zones by walking time to a city',
    label: 'Travel time to a city of 50,000+, on foot',
    unit: 'h',
    digits: 0,
    bins: [2, 4, 8, 16, 32],
    note: 'Median over the zone on the MAP 2019 walking-only surface.',
  },
  market_motorized_median_h: {
    tab: 'To a WFP market',
    list: 'Zones by road time to a WFP market',
    label: 'Travel time to a WFP market, by road',
    unit: 'h',
    digits: 1,
    bins: [0.5, 1, 2, 4, 8],
    note: 'WFP places markets where it operates, so short times partly reflect WFP presence, not access.',
  },
};

export const METRIC_KEYS = Object.keys(ZONE_METRICS);
const RAMP = ['--ramp-1', '--ramp-2', '--ramp-3', '--ramp-4', '--ramp-5', '--ramp-6'];
const IPC = ['--ipc-1', '--ipc-2', '--ipc-3', '--ipc-4'];

export const isMissing = (v) => v === null || v === undefined || v === 'null' || Number.isNaN(Number(v));

export function fmt(v, m) {
  if (isMissing(v)) return '—';
  const s = Number(v).toFixed(m.digits);
  return m.unit ? `${s} ${m.unit}` : s;
}

export function binLabels(m) {
  const b = m.bins;
  return [`< ${b[0]}`, ...b.slice(0, -1).map((x, i) => `${x}–${b[i + 1]}`), `> ${b.at(-1)}`];
}

export function legendSwatches(m) {
  if (m.ipc) return IPC.map((v, i) => ({ var: v, label: String(i + 1) }));
  return binLabels(m).map((label, i) => ({ var: RAMP[i], label }));
}

/** CSS colour for one value, matching the map exactly (IPC blends between phases as the map does). */
export function colorCss(key, v) {
  const m = ZONE_METRICS[key];
  if (isMissing(v)) return 'var(--ramp-0)';
  if (!m.ipc) return `var(${colorVar(key, v)})`;
  const x = Math.min(4, Math.max(1, Number(v)));
  const lo = Math.floor(x), hi = Math.min(4, lo + 1), t = Math.round((x - lo) * 100);
  return lo === hi ? `var(--ipc-${lo})` : `color-mix(in srgb, var(--ipc-${hi}) ${t}%, var(--ipc-${lo}))`;
}

/** CSS variable for one value (bin), used where a single stepped colour is wanted. */
export function colorVar(key, v) {
  const m = ZONE_METRICS[key];
  if (isMissing(v)) return '--ramp-0';
  if (m.ipc) return IPC[Math.min(3, Math.max(0, Math.round(Number(v)) - 1))];
  const i = m.bins.findIndex((b) => Number(v) < b);
  return RAMP[i === -1 ? m.bins.length : i];
}

/** MapLibre fill-color expression for a metric; `css` resolves CSS custom properties. */
export function zoneColor(key, css) {
  const m = ZONE_METRICS[key];
  const missing = css('--ramp-0');
  if (m.ipc) {
    return ['case', ['==', ['get', key], null], missing,
      ['interpolate', ['linear'], ['get', key], 1, css('--ipc-1'), 2, css('--ipc-2'), 3, css('--ipc-3'), 4, css('--ipc-4')]];
  }
  const colors = RAMP.map(css);
  const step = ['step', ['get', key], colors[0]];
  m.bins.forEach((b, i) => step.push(b, colors[i + 1]));
  return ['case', ['==', ['get', key], null], missing, step];
}

/** Spearman rank correlation of two equal-length arrays (pairs with a missing value dropped). */
export function spearman(xs, ys) {
  const pairs = xs.map((x, i) => [Number(x), Number(ys[i])]).filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
  const n = pairs.length;
  if (n < 5) return { rho: null, n };
  const rank = (vals) => {
    const order = vals.map((v, i) => [v, i]).sort((a, b) => a[0] - b[0]);
    const r = new Array(n);
    for (let i = 0; i < n; ) {
      let j = i;
      while (j + 1 < n && order[j + 1][0] === order[i][0]) j++;
      for (let k = i; k <= j; k++) r[order[k][1]] = (i + j) / 2 + 1;
      i = j + 1;
    }
    return r;
  };
  const rx = rank(pairs.map((p) => p[0]));
  const ry = rank(pairs.map((p) => p[1]));
  const mean = (n + 1) / 2;
  let num = 0, dx = 0, dy = 0;
  for (let i = 0; i < n; i++) {
    num += (rx[i] - mean) * (ry[i] - mean);
    dx += (rx[i] - mean) ** 2;
    dy += (ry[i] - mean) ** 2;
  }
  return { rho: num / Math.sqrt(dx * dy), n };
}
