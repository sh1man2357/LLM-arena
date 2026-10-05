import { defineConfig, type ProxyOptions } from 'vite';
import react from '@vitejs/plugin-react';

const proxy: ProxyOptions = {
    target: 'http://127.0.0.1:8787', changeOrigin: true,
    configure(proxy) {
      proxy.on('proxyReq', (outgoing, incoming) => {
        const origin = incoming.headers.origin;
        // Only this local dev origin may be rewritten to the production same-origin boundary.
        if (origin === `http://${incoming.headers.host}` && /^127\.0\.0\.1:\d+$/.test(incoming.headers.host || '')) outgoing.setHeader('origin', 'http://127.0.0.1:8787');
      });
    },
};
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': proxy, '/health': proxy } },
  build: { sourcemap: true },
});
