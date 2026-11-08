import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Front: solo llama a la API local. En desarrollo, /api va al servidor Fastify (127.0.0.1).
const API = `http://127.0.0.1:${process.env.CF_PUERTO ?? 4747}`;

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': API },
  },
  preview: { host: '127.0.0.1' },
});
