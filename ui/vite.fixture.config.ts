import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  define:{__LIVE_ENABLED__:JSON.stringify(process.env.TFT_PUBLIC_BUILD!=='1')},
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5178, strictPort: true },
})
