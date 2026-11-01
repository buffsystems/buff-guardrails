import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev: the UI runs on :5173 and proxies /api to the demo backend (DEMO_API, default :8080).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: process.env.HOST || '127.0.0.1',
    port: 5173,
    proxy: { '/api': process.env.DEMO_API || 'http://127.0.0.1:8080' },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
