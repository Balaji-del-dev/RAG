/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The browser talks only to Vite (localhost:5173); Vite forwards /api to Django,
// so the session cookie and CSRF token stay on one origin (no CORS).
// Django runs on 8001 because 8000 is used by another project on this machine.
export default defineConfig({
  plugins: [react()],
  server: {
    host: 'localhost',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8001', changeOrigin: false },
    },
  },
  test: {
    environment: 'jsdom',
    css: false,
  },
})
