import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/health": backend,
      "/auth": backend,
      "/admin": backend,
      "/kbs": backend,
      // Only forward the /eval API, not the /evals SPA route.
      "^/eval(?:/|$)": backend,
    },
  },
});
