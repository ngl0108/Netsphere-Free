import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      'web-worker': '/src/shims/web-worker.js',
    },
  },
  build: {
    sourcemap: false,
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/src/i18n/')) return 'i18n-bundle';
          if (id.includes('/src/components/topology/')) return 'topology-editor';
          return undefined;
        },
      },
    },
  },
})
