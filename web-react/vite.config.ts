import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  server: {
    port:80,
    proxy: {
      "/upload": "http://127.0.0.1:5000",
      "/upload_chunk_init": "http://127.0.0.1:5000",
      "/upload_chunk": "http://127.0.0.1:5000",
      "/upload_chunk_finalize": "http://127.0.0.1:5000",
      "/analyze": "http://127.0.0.1:5000",
      "/analyze_batch": "http://127.0.0.1:5000",
      "/single_progress": "http://127.0.0.1:5000",
      "/batch_progress": "http://127.0.0.1:5000",
      "/history": "http://127.0.0.1:5000",
      "/download_zip": "http://127.0.0.1:5000",
      "/download_batch_zip": "http://127.0.0.1:5000",
      "/regenerate": "http://127.0.0.1:5000",
      "/test_model": "http://127.0.0.1:5000",
      "/output": "http://127.0.0.1:5000",
    },
  },
  plugins: [react(), tailwindcss()],
});
