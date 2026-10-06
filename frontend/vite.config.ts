/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// The backend (uvicorn) listens on 7171 in development; the dev server
// forwards API calls to it so the browser only talks to one origin.
const backend = process.env.REELHAVEN_BACKEND ?? 'http://127.0.0.1:7171';

export default defineConfig({
  plugins: [react()],
  // Relative asset paths so the built UI works behind any path prefix
  // (reverse proxies, code-server's port proxy).
  base: './',
  server: {
    port: 5173,
    proxy: {
      '/api': { target: backend, ws: true },
      '/healthz': backend,
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
