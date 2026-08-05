import { defineConfig } from 'vite'
import path from 'path'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  assetsInclude: ['**/*.svg', '**/*.csv'],
  server: {
    watch: {
      ignored: [
        '**/backend/**',
        '**/.git/**',
        '**/__pycache__/**',
        '**/*.pyc',
      ],
    },
  },
})
