import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Separate UI development from another running backend without editing routes.
const backendUrl = process.env.MODULE_LAB_BACKEND_URL || 'http://localhost:8000';
const websocketUrl = backendUrl.replace(/^http/, 'ws');

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/ws': {
        target: websocketUrl,
        ws: true,
      },
      '/api': {
        target: backendUrl,
      },
      '/sites': {
        target: backendUrl,
      },
      '/data': {
        target: backendUrl,
      },
      // Renderer source comes from frontend/public during development.
      // The integration build copies it into dist once the branches are merged.
      '/styles': {
        target: backendUrl,
      },
      '/vendor': {
        target: backendUrl,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
