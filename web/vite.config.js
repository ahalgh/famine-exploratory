import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  server: { port: 5173 },
  // maplibre-gl loads its worker by relative URL; pre-bundling breaks that path
  optimizeDeps: { exclude: ['maplibre-gl'] },
});
