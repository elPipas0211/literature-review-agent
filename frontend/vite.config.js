import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,   // start.bat opens :5173, so never silently move to another port
    proxy: {
      '/api': {
        target: process.env.LRA_API || 'http://localhost:8000',  // LRA_API: run a second copy side by side
        changeOrigin: true,
      },
    },
  },
})
