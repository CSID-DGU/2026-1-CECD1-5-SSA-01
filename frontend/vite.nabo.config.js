import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Separate build for the cost-estimate service page (nabo.html); the ERCE app build is untouched.
// API calls go to the same origin (backend/nabo_style/web.py serves this build).
export default defineConfig({
  plugins: [react()],
  define: { 'import.meta.env.VITE_NABO_API_URL': JSON.stringify('') },
  build: {
    outDir: 'dist-nabo',
    emptyOutDir: true,
    rollupOptions: { input: { nabo: 'nabo.html' } },
  },
})
