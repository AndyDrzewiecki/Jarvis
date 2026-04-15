import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // base must match the static mount path so asset URLs resolve correctly
  base: '/static/',
  build: {
    outDir: '../static',
    emptyOutDir: true,
  },
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://192.168.111.28:8000',
      '/ws':  'ws://192.168.111.28:8000',
    },
  },
})
