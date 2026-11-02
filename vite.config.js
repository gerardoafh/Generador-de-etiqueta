import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
// HTTPS local (para usar la cámara desde el celular en la red de la planta).
// Es opcional: si el plugin no está instalado (p. ej. en el servidor AWS), se omite.
let basicSsl = null
try { basicSsl = (await import('@vitejs/plugin-basic-ssl')).default } catch { /* no instalado */ }

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    ...(basicSsl ? [basicSsl()] : [])
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    },
    watch: {
      ignored: [
        '**/data.json',
        '**/drying_state.json',
        '**/print_queue.json',
        '**/generated_labels.json',
        '**/telegram_queue.json',
      ]
    }
  }
})


