// Zone metrics: one definition drives the map colours and the legend.
// Travel times use a one-hue sequential ramp with roughly doubling bins; IPC uses the IPC phase colours.

export const ZONE_METRICS = {
  city_motorized_median_h: {
    label: 'Travel time to a 50k+ city, by vehicle',
    unit: 'h',
    bins: [0.5, 1, 2, 4, 8],
    note: 'Median over the zone, MAP 2019 friction surface. Use for ranking zones; absolute times are optimistic.',
  },
  city_walking_median_h: {
    label: 'Travel time to a 50k+ city, on foot',
    unit: 'h',
    bins: [2, 4, 8, 16, 32],
    note: 'Median over the zone, walking-only friction surface.',
  },
  market_motorized_median_h: {
    label: 'Travel time to a WFP market, by vehicle',
    unit: 'h',
    bins: [0.5, 1, 2, 4, 8],
    note: 'WFP places markets where it operates, so this partly measures WFP presence rather than access.',
  },
  ipc_mean: {
    label: 'Mean observed IPC phase, 2020 onward',
    unit: '',
    ipc: true,
    note: 'FEWS NET current situation, averaged over reports since 2020. Not available for Guatemala or Somalia zones.',
  },
};

const SEQ = ['--seq-1', '--seq-3', '--seq-4', '--seq-5', '--seq-6', '--seq-7']; // skip a step so neighbouring bins stay distinct

export function binLabels(m) {
  const b = m.bins;
  return [`< ${b[0]}`, ...b.slice(0, -1).map((x, i) => `${x}–${b[i + 1]}`), `> ${b.at(-1)}`].map((s) => `${s} ${m.unit}`);
}

export function seqVars(m) {
  return SEQ.slice(0, m.bins.length + 1);
}

/** MapLibre fill-color expression for a metric; `css` resolves CSS custom properties. */
export function zoneColor(key, css) {
  const m = ZONE_METRICS[key];
  const missing = css('--seq-0');
  if (m.ipc) {
    return ['case', ['==', ['get', key], null], missing,
      ['interpolate', ['linear'], ['get', key], 1, css('--ipc-1'), 2, css('--ipc-2'), 3, css('--ipc-3'), 4, css('--ipc-4')]];
  }
  const colors = seqVars(m).map(css);
  const step = ['step', ['get', key], colors[0]];
  m.bins.forEach((b, i) => step.push(b, colors[i + 1]));
  return ['case', ['==', ['get', key], null], missing, step];
}
