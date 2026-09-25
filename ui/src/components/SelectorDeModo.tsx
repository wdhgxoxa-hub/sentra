import { hayQueElegirModo, MODOS } from "@/modos/registro";
import { useT } from "@/stores/settingsStore";
import { useUiStore } from "@/stores/uiStore";

/**
 * Sitio reservado en la barra lateral para elegir modo (P2: Software |
 * Videos). Con un solo modo registrado no se pinta: enseñarlo prometería un
 * modo que no existe. Al registrar el segundo en `modos/registro.ts`, aparece.
 */
export function SelectorDeModo() {
  const t = useT();
  const modo = useUiStore((s) => s.modo);
  if (!hayQueElegirModo(MODOS)) return null;
  return (
    <div role="radiogroup" aria-label={t.modos.titulo} className="mb-2 grid grid-cols-2 gap-1 rounded-lg bg-surface-2 p-1">
      {MODOS.map((m) => (
        <button
          key={m.id}
          type="button"
          role="radio"
          aria-checked={m.id === modo}
          onClick={() => useUiStore.setState({ modo: m.id })}
          className={`h-8 rounded-md text-sm font-medium ${m.id === modo ? "bg-surface text-ink shadow-card" : "text-ink-soft"}`}
        >
          {m.textos(t).nombre}
        </button>
      ))}
    </div>
  );
}
