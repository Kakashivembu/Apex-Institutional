import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendHttpUrl = env.VITE_BACKEND_URL || 'http://127.0.0.1:8000'
  const backendWsUrl = backendHttpUrl.replace(/^http/i, 'ws')

  return {
    plugins: [react()],
    server: {
      host: true,
      port: 5173,
      allowedHosts: true,
      proxy: {
        '/api': {
          target: backendHttpUrl,
          changeOrigin: true,
          secure: false,
          configure: (proxy) => {
            proxy.on('error', (_err, _req, res) => {
              if (res && !res.headersSent) {
                res.writeHead(503, { 'Content-Type': 'application/json' })
              }
              if (res) {
                res.end(JSON.stringify({ error: 'Backend unavailable' }))
              }
            })
          },
        },
        '/ws': {
          target: backendWsUrl,
          ws: true,
          changeOrigin: true,
          secure: false,
          configure: (proxy) => {
            proxy.on('error', () => {
              // Silent during backend restarts; the React client retries automatically.
            })
          },
        },
      },
    },
    preview: {
      host: true,
      port: 4173,
      allowedHosts: true,
    },
  }
})
