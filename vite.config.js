import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // In development, keep browser requests on Vite's origin and forward only API traffic to Python.
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
});
