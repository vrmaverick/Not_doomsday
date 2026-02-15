import glsl from 'vite-plugin-glsl'
import { resolve } from 'path'

export default {
  publicDir: 'public',
  server: {
    host: true,
    open: true,
    proxy: {
      // Forward API calls to the FastAPI backend (uvicorn Backend:app --port 8000)
      '/health': 'http://127.0.0.1:8000',
      '/run_pipeline': 'http://127.0.0.1:8000',
      '/mitigate': 'http://127.0.0.1:8000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        globe: resolve(__dirname, 'globe.html'),
        dashboard: resolve(__dirname, 'dashboard.html'),
        mitigation: resolve(__dirname, 'mitigation.html'),
      },
    },
  },
  plugins: [glsl()],
}
