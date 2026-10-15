import react from '@vitejs/plugin-react'
import { defineConfig } from 'electron-vite'

const define={__LIVE_ENABLED__:JSON.stringify(process.env.TFT_PUBLIC_BUILD!=='1')}

export default defineConfig({
  main: {define},
  preload: {},
  renderer: {
    define,
    plugins: [react()],
  },
})
