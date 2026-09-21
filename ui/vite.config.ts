import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Tauri sirve la app desde un puerto fijo y espera el build en dist/.
// `clearScreen: false` deja ver a la vez los errores de Rust y los de Vite.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  clearScreen: false,
  resolve: {
    alias: {
      // El alias tiene que estar aqui ademas de en tsconfig: TypeScript lo
      // usa para comprobar tipos, pero quien resuelve los imports al
      // empaquetar es Rollup, y lee esta configuracion.
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    watch: { ignored: ["**/src-tauri/**"] },
  },
  build: {
    // Tauri v2 usa WebView2 en Windows y WKWebView en macOS: no hace falta
    // transpilar para navegadores antiguos.
    target: "chrome105",
    sourcemap: true,
  },
});
