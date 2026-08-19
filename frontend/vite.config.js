import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In local dev, Vite proxies /api -> the local backend (localhost:8000).
// In production on Vercel, the frontend calls the backend directly via
// VITE_API_BASE (set to your Render URL) — see src/api.js and DEPLOY.md.
const BACKEND = process.env.VITE_BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
    },
  },
});
