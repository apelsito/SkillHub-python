import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    exclude: ['**/node_modules/**', '**/e2e/**'],
  },
  server: {
    host: '127.0.0.1',
    port: 3000,
    watch: {
      usePolling: true,
      interval: 150,
    },
    proxy: {
      // Always IPv4 — on Windows `localhost` resolves to ::1 first and
      // Vite's proxy then races against a backend that only binds IPv4.
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
      '/oauth2': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
    },
  },
})
