import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  // BASE_PATH=/famine-exploratory/ for a GitHub Pages project site; '/' everywhere else
  base: process.env.BASE_PATH ?? '/',
  plugins: [svelte()],
  server: { port: 5173 },
  // the worker is served from public/vendor (see MapView.svelte); keep maplibre-gl out of pre-bundling
  optimizeDeps: { exclude: ['maplibre-gl'] },
});
