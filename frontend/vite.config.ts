import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // devcontainerのポートフォワーディング(IPv4)からも繋げるよう全アドレスでlistenする
    host: true,
    // フロントは5173、バックエンドは8000で動かし、/apiだけbackendに流す
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
