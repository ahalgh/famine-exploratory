// 1 km travel-time surfaces, decoded in the browser.
// scripts/export_map_data.py packs minutes into each PNG's red (high byte) and green (low byte)
// channels with alpha 0 where there is no data, in Web Mercator, so colour comes from the CSS tokens
// at draw time and the exact value under the cursor can be read back.

import { asset } from './paths.js';

const cache = new Map();
let index = null;

export async function loadIndex() {
  index ??= await (await fetch(asset('/data/access/index.json'))).json();
  return index;
}

/** Decode one surface: { minutes: Uint16Array, valid: Uint8Array, width, height, coordinates }. */
export async function loadSurface(country, layer) {
  const idx = await loadIndex();
  const meta = idx[country]?.[layer];
  if (!meta) return null;
  if (cache.has(meta.url)) return cache.get(meta.url);
  const img = new Image();
  img.src = asset(meta.url);
  await img.decode();
  const canvas = new OffscreenCanvas(meta.width, meta.height);
  const ctx = canvas.getContext('2d', { colorSpace: 'srgb' });
  ctx.drawImage(img, 0, 0);
  const px = ctx.getImageData(0, 0, meta.width, meta.height).data;
  const n = meta.width * meta.height;
  const minutes = new Uint16Array(n);
  const valid = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    valid[i] = px[i * 4 + 3] === 255 ? 1 : 0;
    minutes[i] = (px[i * 4] << 8) | px[i * 4 + 1];
  }
  const surface = { ...meta, minutes, valid };
  cache.set(meta.url, surface);
  return surface;
}

/** Colour a surface into a data URL using hour bins and their CSS colours. */
export function colorize(surface, binsHours, colors) {
  const { width, height, minutes, valid } = surface;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  const out = ctx.createImageData(width, height);
  const rgb = colors.map(hexToRgb);
  const edges = binsHours.map((h) => h * 60);
  for (let i = 0; i < minutes.length; i++) {
    if (!valid[i]) continue;
    const m = minutes[i];
    let b = 0;
    while (b < edges.length && m >= edges[b]) b++;
    const [r, g, bl] = rgb[b];
    out.data[i * 4] = r;
    out.data[i * 4 + 1] = g;
    out.data[i * 4 + 2] = bl;
    out.data[i * 4 + 3] = 255;
  }
  ctx.putImageData(out, 0, 0);
  return canvas.toDataURL('image/png');
}

/** Minutes at a longitude/latitude, or null outside the surface or where there is no data. */
export function sample(surface, lon, lat) {
  if (!surface) return null;
  const [[west, north], , [east, south]] = surface.coordinates;
  const x = (mercX(lon) - mercX(west)) / (mercX(east) - mercX(west));
  const y = (mercY(north) - mercY(lat)) / (mercY(north) - mercY(south));
  if (x < 0 || x >= 1 || y < 0 || y >= 1) return null;
  const i = Math.floor(y * surface.height) * surface.width + Math.floor(x * surface.width);
  return surface.valid[i] ? surface.minutes[i] : null;
}

const mercX = (lon) => (lon * Math.PI) / 180;
const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));

function hexToRgb(color) {
  const c = color.trim();
  if (c.startsWith('#')) {
    const h = c.length === 4 ? [...c.slice(1)].map((x) => x + x).join('') : c.slice(1);
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  }
  const m = c.match(/\d+(\.\d+)?/g);
  return m ? m.slice(0, 3).map(Number) : [128, 128, 128];
}
