import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Minimal shim so tsc type-checks this config without pulling in @types/node;
// Node provides `process` at config-evaluation time.
declare const process: { env: Record<string, string | undefined> };

// Static SPA. `base` defaults to "/" for local dev; GitHub Pages builds set
// VITE_BASE=/<repo>/ so assets + data resolve under the project subpath.
export default defineConfig({
  base: process.env.VITE_BASE || "/",
  plugins: [react()],
  server: { port: 5173 },
});
