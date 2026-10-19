import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  server: { port: 5173 },
  // the worker is served from public/vendor (see MapView.svelte); keep maplibre-gl out of pre-bundling
  optimizeDeps: { exclude: ['maplibre-gl'] },
});
