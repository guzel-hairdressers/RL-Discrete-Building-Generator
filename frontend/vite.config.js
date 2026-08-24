import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      '/api': {
        target: 'http://localhost:8000',
      },
      '/sites': {
        target: 'http://localhost:8000',
      },
      '/data': {
        target: 'http://localhost:8000',
      },
      '/scripts': {
        target: 'http://localhost:8000',
      },
      '/styles': {
        target: 'http://localhost:8000',
      },
      '/vendor': {
        target: 'http://localhost:8000',
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
