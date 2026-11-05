import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The stand is built into ./dist and committed, so `uv run pytest -q` exercises the
// kits against the real components without Node. `base: './'` keeps asset URLs
// relative; `license: true` writes the third-party notices next to the bundle.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    license: true,
    reportCompressedSize: false,
  },
})
