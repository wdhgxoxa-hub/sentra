import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

/**
 * Límite por chunk, en kB como los cuenta Vite (1 kB = 1000 bytes). Su aviso
 * se quedaba en aviso y la release salía igual: aquí el build falla (C3). El
 * límite no se sube; si algo no cabe, se divide el código. La variable de
 * entorno solo existe para que tests/test_bundle_limite.py pruebe el guardia.
 */
const LIMITE_KB = Number(process.env.SENTRA_CHUNK_LIMIT_KB ?? 500);

function limiteDeChunks(): Plugin {
  return {
    name: "limite-de-chunks",
    apply: "build",
    generateBundle(_opciones, bundle) {
      for (const pieza of Object.values(bundle)) {
        if (pieza.type !== "chunk") continue;
        const kb = pieza.code.length / 1000;
        if (kb > LIMITE_KB) {
          this.error(`${pieza.fileName} ocupa ${kb.toFixed(1)} kB y supera el límite de ${LIMITE_KB} kB`);
        }
      }
    },
  };
}

// Tauri sirve la app desde un puerto fijo y espera el build en dist/.
// `clearScreen: false` deja ver a la vez los errores de Rust y los de Vite.
export default defineConfig({
  plugins: [react(), tailwindcss(), limiteDeChunks()],
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
