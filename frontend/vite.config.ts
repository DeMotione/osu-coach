import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// `npm run dev` serves the app on :5173 and forwards the API to a running `osu-coach-api` (default :8501).
const api = process.env.OSU_COACH_API ?? "http://127.0.0.1:8501";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: false,
      includeAssets: ["favicon.svg", "apple-touch-icon.png"],
      manifest: {
        id: "/",
        name: "osu! coach",
        short_name: "osu! coach",
        description: "Analyses your osu!standard replays and tells you what to work on.",
        lang: "en",
        start_url: "/",
        scope: "/",
        display: "standalone",
        theme_color: "#16161f",
        background_color: "#111118",
        categories: ["games", "sports", "utilities"],
        icons: [
          { src: "pwa-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "pwa-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
          { src: "pwa-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // the app shell works offline; the API is the local server, so its answers are never cached
        globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/docs/],
        cleanupOutdatedCaches: true,
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: { "/api": { target: api }, "/docs": { target: api } },
  },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 1100,
    rolldownOptions: {
      output: {
        // the chart library is large and changes rarely: its own chunk, cached apart from the app
        codeSplitting: {
          groups: [
            { name: "charts", test: /node_modules[\\/](echarts|zrender)[\\/]/, priority: 2 },
            { name: "vendor", test: /node_modules[\\/]/, priority: 1 },
          ],
        },
      },
    },
  },
});
