/**
 * Preferencias de la interfaz
 * ===========================
 *
 * Idioma y tema. Se guardan en `localStorage` porque son del navegador de
 * esta persona, no del proyecto: cambiar el idioma no debería tocar la base
 * de datos ni afectar a nadie más.
 *
 * Se leen de forma defensiva: en una ventana privada, o con el almacenamiento
 * bloqueado, el acceso lanza. Un fallo ahí no puede impedir que la aplicación
 * arranque.
 */

import { create } from "zustand";

import { en } from "@/i18n/en";
import { es, type Dictionary } from "@/i18n/es";

export type Language = "es" | "en";
export type Theme = "light" | "dark" | "system";

const DICTIONARIES: Record<Language, Dictionary> = { es, en };

const STORAGE_KEY = "sentra.preferences";

interface StoredPreferences {
  language?: Language;
  theme?: Theme;
}

function readStored(): StoredPreferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredPreferences) : {};
  } catch {
    return {};
  }
}

function persist(preferences: StoredPreferences): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  } catch {
    // Sin almacenamiento, la preferencia dura lo que dure la ventana.
  }
}

/** Idioma inicial: lo guardado, y si no, el del sistema. */
function detectLanguage(): Language {
  const stored = readStored().language;
  if (stored === "es" || stored === "en") return stored;
  return navigator.language?.toLowerCase().startsWith("es") ? "es" : "en";
}

/**
 * Aplica el tema al documento.
 *
 * Con "system" se quita el atributo para que mande la media query del CSS,
 * en lugar de resolverlo aquí en JavaScript: así el tema sigue al sistema
 * si cambia mientras la ventana está abierta.
 */
function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", theme);
  }
}

interface SettingsState {
  language: Language;
  theme: Theme;
  t: Dictionary;
  setLanguage: (language: Language) => void;
  setTheme: (theme: Theme) => void;
}

const initialLanguage = detectLanguage();
const initialTheme = readStored().theme ?? "system";
applyTheme(initialTheme);

export const useSettingsStore = create<SettingsState>((set, get) => ({
  language: initialLanguage,
  theme: initialTheme,
  t: DICTIONARIES[initialLanguage],

  setLanguage: (language) => {
    persist({ language, theme: get().theme });
    document.documentElement.lang = language;
    set({ language, t: DICTIONARIES[language] });
  },

  setTheme: (theme) => {
    persist({ language: get().language, theme });
    applyTheme(theme);
    set({ theme });
  },
}));

// El idioma del documento importa para lectores de pantalla y para la
// separación silábica del navegador.
document.documentElement.lang = initialLanguage;

/** Atajo para leer los textos del idioma activo. */
export function useT(): Dictionary {
  return useSettingsStore((state) => state.t);
}

// El estado global no sobrevive a un intercambio en caliente: los componentes
// ya montados siguen apuntando a la instancia anterior y la vista se queda en
// blanco. Recargar la ventana es barato y siempre deja un estado coherente.
if (import.meta.hot) {
  import.meta.hot.accept(() => window.location.reload());
}
