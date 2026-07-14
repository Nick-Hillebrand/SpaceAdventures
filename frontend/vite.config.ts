/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import path from "node:path";

export default defineConfig({
  plugins: [
    react(),
    // 19-notification-channels-v2.md B1.2: custom `src/sw.ts` (push +
    // notificationclick handlers) via injectManifest — never the generated
    // strategy, since we hand-write the push event handling. The SW is only
    // registered in production builds (`registerType: "prompt"` + the
    // frontend's own `import.meta.env.PROD` gate around `registerSW()`) so
    // it never collides with the MSW mock worker in dev/test.
    VitePWA({
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      injectRegister: false,
      manifest: false,
      devOptions: { enabled: false },
      injectManifest: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico}"],
      },
    }),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    sourcemap: false,
    // Read by scripts/check-bundle.mjs to walk the real chunk graph rather
    // than guess from filenames (26-performance.md §2.1 bundle budget gate).
    manifest: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_BASE_URL ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/msw/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**"],
      exclude: ["src/msw/**", "src/types/**", "src/locales/**", "src/main.tsx"],
      thresholds: {
        perFile: true,
        branches: 80,
      },
    },
  },
});
