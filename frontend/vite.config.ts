import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;

          if (id.includes('@ant-design/plots') || id.includes('@antv')) {
            return 'vendor-charts';
          }
          if (id.includes('@xyflow') || id.includes('reactflow') || id.includes('dagre')) {
            return 'vendor-flow';
          }
          return undefined;
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/v1': 'http://localhost:8000',
    }
  }
})
