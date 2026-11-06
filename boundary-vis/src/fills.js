// Fills for the HFID units. Each answers one normalisation question and drives both the map colour
// and the legend. Bins step through the one-hue ramp (--ramp-1..6); "worse fit" is always more ink.

export const FILLS = {
  none: { label: 'None', question: 'Outlines only.' },
  dominant_share: {
    label: 'Fit inside one livelihood zone',
    question: 'Can zone-level IPC be assigned to this unit without splitting it?',
    expr: ['get', 'dominant_share'],
    // low share = straddles zones = worse fit = more ink
    bins: [{ max: 0.5, label: 'under 50%' }, { max: 0.8, label: '50–80%' }, { max: 0.95, label: '80–95%' }, { max: Infinity, label: '95% or more' }],
    ramp: ['--ramp-6', '--ramp-4', '--ramp-2', '--ramp-1'],
  },
  smap_cells: {
    label: 'Size in SMAP 36 km cells',
    question: 'Can soil moisture at 36 km resolve this unit?',
    expr: ['get', 'smap_cells'],
    bins: [{ max: 0.25, label: 'under ¼ cell' }, { max: 0.5, label: '¼–½' }, { max: 1, label: '½–1' }, { max: 2, label: '1–2' }, { max: 4, label: '2–4' }, { max: Infinity, label: '4 or more' }],
    ramp: ['--ramp-6', '--ramp-5', '--ramp-4', '--ramp-3', '--ramp-2', '--ramp-1'],
  },
  markets: {
    label: 'Price markets inside',
    question: 'Can prices be joined directly, or must they be borrowed from elsewhere?',
    expr: ['+', ['get', 'n_wfp'], ['get', 'n_fao']],
    bins: [{ max: 0.5, label: 'none' }, { max: 1.5, label: '1' }, { max: 4.5, label: '2–4' }, { max: Infinity, label: '5 or more' }],
    ramp: ['--ramp-6', '--ramp-4', '--ramp-2', '--ramp-1'],
  },
  wfp_h: {
    label: 'Road time to its WFP price market',
    question: 'How far is this unit from the WFP market whose price would stand in for it?',
    expr: ['coalesce', ['get', 'wfp_h'], 99],
    bins: [{ max: 0.5, label: 'under 30 min' }, { max: 1, label: '½–1 h' }, { max: 2, label: '1–2 h' }, { max: 4, label: '2–4 h' }, { max: 8, label: '4–8 h' }, { max: Infinity, label: '8 h or more' }],
    ramp: ['--ramp-1', '--ramp-2', '--ramp-3', '--ramp-4', '--ramp-5', '--ramp-6'],
  },
  fao_h: {
    label: 'Road time to its FAO price town',
    question: 'How far is this unit from the FAO town series whose price would stand in for it?',
    expr: ['coalesce', ['get', 'fao_h'], 99],
    bins: [{ max: 0.5, label: 'under 30 min' }, { max: 1, label: '½–1 h' }, { max: 2, label: '1–2 h' }, { max: 4, label: '2–4 h' }, { max: 8, label: '4–8 h' }, { max: Infinity, label: '8 h or more' }],
    ramp: ['--ramp-1', '--ramp-2', '--ramp-3', '--ramp-4', '--ramp-5', '--ramp-6'],
  },
  months_fews: {
    label: 'Months with FEWS IPC in HFID',
    question: 'How much harmonised IPC history does this unit have?',
    expr: ['get', 'months_fews'],
    bins: [{ max: 0.5, label: 'none' }, { max: 24.5, label: '1–24' }, { max: 60.5, label: '25–60' }, { max: Infinity, label: '61 or more' }],
    ramp: ['--ramp-6', '--ramp-4', '--ramp-2', '--ramp-1'],
  },
  gb_iou: {
    label: 'Match to geoBoundaries district',
    question: 'Is this the same unit as the district boundaries used elsewhere?',
    expr: ['coalesce', ['get', 'gb_iou'], 0],
    bins: [{ max: 0.25, label: 'under 0.25' }, { max: 0.5, label: '0.25–0.5' }, { max: 0.8, label: '0.5–0.8' }, { max: Infinity, label: '0.8 or more' }],
    ramp: ['--ramp-6', '--ramp-4', '--ramp-2', '--ramp-1'],
  },
};

export function fillColor(key, css) {
  const f = FILLS[key];
  if (!f.bins) return css('--ramp-0');
  const step = ['step', f.expr, css(f.ramp[0])];
  f.bins.slice(0, -1).forEach((b, i) => step.push(b.max, css(f.ramp[i + 1])));
  return step;
}
