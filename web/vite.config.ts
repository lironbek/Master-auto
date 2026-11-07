import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, /api/* is proxied to the FastAPI server. In production, vercel.json
// rewrites /api/* to the deployed API so the app stays same-origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: process.env.PT_API_URL || 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
