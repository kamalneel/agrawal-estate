import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    // Expose to network so other devices can access
    host: '0.0.0.0',
    // Allow custom local hostname and network access
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  // For production build, API calls go to same origin
  build: {
    outDir: 'dist',
  },
})
