import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The bundle is built into ../static, which server.py serves. `base: './'` keeps
// asset URLs relative so the same build works under any mount point.
//
// The dev server proxies /api to server.py rather than reimplementing it: there is
// one stub back end and both modes must meet the same one, or a defect would
// behave differently while it is being written than while it is being measured.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: '../static',
    emptyOutDir: true,
    // Readable output: an evidence pack quoting minified frames helps nobody, and
    // this bundle is a fixture, not something whose size anyone pays for.
    minify: false,
    sourcemap: true,
  },
  server: {
    port: 8801,
    proxy: { '/api': 'http://127.0.0.1:8800' },
  },
})
