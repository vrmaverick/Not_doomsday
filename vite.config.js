import glsl from 'vite-plugin-glsl'
import { resolve } from 'path'

export default {
  publicDir: 'public',
  server: {
    host: true,
    open: true,
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
      },
    },
  },
  plugins: [glsl()],
}
