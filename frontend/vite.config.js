import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'path'

// Dev/preview fallback for the supplier portal's router paths: /supplier and
// /supplier/* must serve supplier.html (nginx does this in production).
// NOT /suppliers — that's the internal portal's admin route.
const supplierSpaFallback = {
  name: 'supplier-spa-fallback',
  configureServer(server) {
    server.middlewares.use((req, _res, next) => {
      if (/^\/supplier(\/|$)/.test(req.url.split('?')[0])) req.url = '/supplier.html'
      next()
    })
  },
  configurePreviewServer(server) {
    server.middlewares.use((req, _res, next) => {
      if (/^\/supplier(\/|$)/.test(req.url.split('?')[0])) req.url = '/supplier.html'
      next()
    })
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), supplierSpaFallback],
  build: {
    rollupOptions: {
      input: {
        // Internal / Admin portal  →  http://localhost:5173/
        main: resolve(__dirname, 'index.html'),
        // Supplier portal          →  http://localhost:5173/supplier.html
        supplier: resolve(__dirname, 'supplier.html'),
      },
    },
  },
})
