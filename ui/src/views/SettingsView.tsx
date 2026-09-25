import {
  CheckCircle2,
  Eye,
  Gauge,
  EyeOff,
  Globe,
  Monitor,
  Moon,
  Sparkles,
  Sun,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import { useState } from "react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { comoError } from "@/lib/errors";
import {
  useGeminiBudget,
  useGeminiModels,
  useSaveGeminiBudget,
  useSaveGeminiKey,
  useSettings,
  useTestGeminiKey,
} from "@/lib/queries";
import { haceCuanto } from "@/lib/tiempo";
import {
  useSettingsStore,
  useT,
  type Language,
  type Theme,
} from "@/stores/settingsStore";
import type { GeminiBudget, GeminiModelsResult, ProbeResult } from "@/types/radar";

/**
 * Resultado de «Probar clave» (D1). Solo un rechazo de Google pinta la clave
 * como mala; un fallo de red, de cuota o del servidor dice que no se pudo
 * comprobar, en ámbar: la clave puede estar bien.
 */
function ResultadoDeLaPrueba({ resultado }: { resultado: ProbeResult }) {
  const estado = resultado.ok ? "ok" : resultado.code === "gemini_key_rejected" ? "mala" : "sin_comprobar";
  const estilo = { ok: "bg-ok/10 text-ok", mala: "bg-danger/10 text-danger", sin_comprobar: "bg-warn/10 text-warn" };
  const Icono = { ok: CheckCircle2, mala: XCircle, sin_comprobar: TriangleAlert }[estado];
  return (
    <p className={`flex items-start gap-1.5 rounded-lg p-2.5 text-xs ${estilo[estado]}`}>
      <Icono className="mt-px size-3.5 shrink-0" aria-hidden="true" />
      {resultado.detail}
    </p>
  );
}

const LANGUAGES: Array<{ value: Language; label: string }> = [
  { value: "es", label: "Español" },
  { value: "en", label: "English" },
];

/**
 * Configuración: apariencia y motor de IA (Gemini).
 *
 * Existe para que no haya que abrir una terminal y editar un `.env` a mano.
 * La clave se envía una vez y no vuelve nunca: lo que se muestra después es
 * solo si está configurada y una versión enmascarada. Las credenciales de
 * cada fuente viven en su tarjeta de Fuentes (D-C5).
 */
export function SettingsView() {
  const t = useT();
  const language = useSettingsStore((state) => state.language);
  const setLanguage = useSettingsStore((state) => state.setLanguage);
  const theme = useSettingsStore((state) => state.theme);
  const setTheme = useSettingsStore((state) => state.setTheme);

  const settings = useSettings();
  const guardarGemini = useSaveGeminiKey();
  const probarGemini = useTestGeminiKey();

  const [geminiKey, setGeminiKey] = useState("");
  const [verClave, setVerClave] = useState(false);
  // El modelo elegido gana; si nadie ha tocado el selector, manda el
  // guardado. Sincronizarlo con un efecto solo serviria para pelearse con el
  // refresco de la consulta. "" es "automático".
  const [documentosElegido, setDocumentosElegido] = useState<string | null>(null);
  const [generalElegido, setGeneralElegido] = useState<string | null>(null);
  const modelos = useGeminiModels(Boolean(settings.data?.gemini?.configured));

  const themes: Array<{ value: Theme; label: string; Icon: typeof Sun }> = [
    { value: "light", label: t.settings.themeLight, Icon: Sun },
    { value: "dark", label: t.settings.themeDark, Icon: Moon },
    { value: "system", label: t.settings.themeSystem, Icon: Monitor },
  ];

  const documentos = documentosElegido ?? settings.data?.gemini?.model ?? "";
  const general = generalElegido ?? settings.data?.gemini?.generalModel ?? "";

  const campo =
    "w-full rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm transition-colors focus:border-accent";

  return (
    <div className="flex max-w-3xl flex-col gap-8">
      <header>
        <h2 className="text-base font-semibold">{t.settings.title}</h2>
        <p className="mt-0.5 text-xs text-ink-soft">
          {t.settings.subtitle}
        </p>
      </header>

      {/* --- Apariencia --- */}
      <section className="rounded-card border border-border bg-surface p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <Eye className="size-4 text-ink-soft" aria-hidden="true" />
          {t.settings.appearance}
        </h3>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="flex items-center gap-1.5 text-xs text-ink-soft">
              <Globe className="size-3.5" aria-hidden="true" />
              {t.settings.language}
            </span>
            <select
              value={language}
              onChange={(event) => setLanguage(event.target.value as Language)}
              className={campo}
            >
              {LANGUAGES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <div className="flex flex-col gap-1.5">
            <span className="text-xs text-ink-soft">
              {t.settings.theme}
            </span>
            <div
              className="flex gap-1"
              role="group"
              aria-label={t.settings.theme}
            >
              {themes.map(({ value, label, Icon }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setTheme(value)}
                  aria-pressed={theme === value}
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-2 py-2 text-xs transition-colors ${
                    theme === value
                      ? "border-accent bg-accent-soft text-accent"
                      : "border-border hover:bg-surface-2"
                  }`}
                >
                  <Icon className="size-3.5" aria-hidden="true" />
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* El motor puede no estar levantado. Se dice aquí, una sola vez: las
          dos secciones siguientes dependen de el y se quedarían mudas sin
          explicación. */}
      {settings.isPending && (
        <p className="text-sm text-ink-faint">{t.settings.loading}</p>
      )}
      {settings.isError && (
        <div className="rounded-card border border-danger/30 bg-surface p-3">
          <ErrorNotice {...comoError(settings.error)} title={t.settings.unreachable} />
        </div>
      )}

      {/* --- Motor de arquitectura (Gemini) --- */}
      <section className="rounded-card border border-border bg-surface p-5">
        <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="size-4 text-ink-soft" aria-hidden="true" />
          {t.settings.aiEngine}
          {settings.data?.gemini && (
            <span
              className={`ml-auto rounded-full px-2 py-0.5 text-[11px] font-medium ${
                settings.data.gemini.configured
                  ? "bg-ok/15 text-ok"
                  : "bg-surface-2 text-ink-faint"
              }`}
            >
              {settings.data.gemini.configured
                ? `${t.settings.configured} · ${settings.data.gemini.keyMasked}`
                : t.settings.notConfigured}
            </span>
          )}
        </h3>
        <p className="mb-3 text-xs leading-relaxed text-ink-soft">
          {t.settings.aiHint}
        </p>

        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs text-ink-soft">{t.settings.apiKey}</span>
            <div className="flex gap-2">
              <input
                type={verClave ? "text" : "password"}
                value={geminiKey}
                onChange={(event) => setGeminiKey(event.target.value)}
                autoComplete="off"
                spellCheck={false}
                className={`${campo} flex-1 font-mono text-xs`}
              />
              <button
                type="button"
                onClick={() => setVerClave((previo) => !previo)}
                aria-pressed={verClave}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border px-3 text-xs transition-colors hover:bg-surface-2"
              >
                {verClave ? (
                  <EyeOff className="size-3.5" aria-hidden="true" />
                ) : (
                  <Eye className="size-3.5" aria-hidden="true" />
                )}
                {verClave ? t.settings.hideKey : t.settings.showKey}
              </button>
            </div>
          </label>

          {/* Modelos: solo los que la clave puede usar (lista en vivo). */}
          {!settings.data?.gemini?.configured ? (
            <p className="text-[11px] leading-relaxed text-ink-faint">
              {t.settings.modelsNeedKey}
            </p>
          ) : modelos.isPending ? (
            <p className="text-xs text-ink-soft">{t.settings.modelsLoading}</p>
          ) : modelos.isError ? (
            <ErrorNotice {...comoError(modelos.error)} title={t.settings.modelsFailed} />
          ) : !modelos.data.ok ? (
            <ErrorNotice
              code={modelos.data.code ?? "gemini_error"}
              detail={modelos.data.detail}
              title={t.settings.modelsFailed}
            />
          ) : (
            <>
              <SelectorDeModelo
                etiqueta={t.settings.modelDocuments}
                pista={t.settings.modelDocumentsHint}
                valor={documentos}
                automatico={modelos.data.documents}
                lista={modelos.data}
                onChange={setDocumentosElegido}
                clase={campo}
              />
              <SelectorDeModelo
                etiqueta={t.settings.modelGeneral}
                pista={t.settings.modelGeneralHint}
                valor={general}
                automatico={modelos.data.general}
                lista={modelos.data}
                onChange={setGeneralElegido}
                clase={campo}
              />
              {/* AUD2-019: la llamada a Google no es invisible. */}
              {haceCuanto(modelos.data.listedAt, new Date(), language) && (
                <p className="text-[11px] leading-relaxed text-ink-faint">
                  {t.settings.modelsListedAt.replace(
                    "{ago}",
                    haceCuanto(modelos.data.listedAt, new Date(), language) ?? "",
                  )}
                </p>
              )}
            </>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={
                guardarGemini.isPending ||
                (!geminiKey.trim() && !settings.data?.gemini?.configured)
              }
              onClick={() =>
                guardarGemini.mutate(
                  // Sin clave nueva, el motor conserva la guardada y solo
                  // cambia los modelos.
                  { apiKey: geminiKey.trim(), model: documentos, generalModel: general },
                  {
                    // La clave se borra del formulario en cuanto viaja: no
                    // tiene por que seguir en pantalla ni en memoria.
                    onSuccess: () => setGeminiKey(""),
                  },
                )
              }
              className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-40"
            >
              {guardarGemini.isPending
                ? t.settings.saving
                : geminiKey.trim()
                  ? t.settings.saveKey
                  : t.settings.saveModels}
            </button>

            <button
              type="button"
              disabled={probarGemini.isPending || !settings.data?.gemini?.configured}
              onClick={() => probarGemini.mutate()}
              className="rounded-lg border border-border px-3 py-2 text-sm transition-colors hover:bg-surface-2 disabled:opacity-40"
            >
              {probarGemini.isPending ? t.settings.testing : t.settings.testKey}
            </button>
          </div>

          {guardarGemini.isError && <ErrorNotice {...comoError(guardarGemini.error)} />}
          {guardarGemini.isSuccess && !guardarGemini.isPending && (
            <p className="flex items-center gap-1 text-xs text-ok">
              <CheckCircle2 className="size-3.5" aria-hidden="true" />
              {t.settings.keySaved}
            </p>
          )}
          {probarGemini.isError && (
            <ErrorNotice {...comoError(probarGemini.error)} title={t.settings.probeFailed} />
          )}

          {probarGemini.data && <ResultadoDeLaPrueba resultado={probarGemini.data} />}
        </div>
      </section>

      <PresupuestoDeGemini campo={campo} />
    </div>
  );
}

type Topes = Omit<GeminiBudget, "spentToday">;
const CAMPOS_DE_TOPE: Array<{ clave: keyof Topes; texto: "scanCalls" | "scanTokens" | "dailyCalls" | "dailyTokens" }> = [
  { clave: "scanMaxCalls", texto: "scanCalls" },
  { clave: "scanMaxTokens", texto: "scanTokens" },
  { clave: "dailyMaxCalls", texto: "dailyCalls" },
  { clave: "dailyMaxTokens", texto: "dailyTokens" },
];

/**
 * Configuración › Presupuesto de Gemini (Fase 1, B4): los cuatro topes que el
 * motor aplica antes de cada llamada, guardados en la base, y lo gastado hoy.
 * Los avisos de tope alcanzado nombran estos campos por su texto exacto.
 */
function PresupuestoDeGemini({ campo }: { campo: string }) {
  const t = useT();
  const presupuesto = useGeminiBudget();
  const guardar = useSaveGeminiBudget();
  // Lo tecleado gana; sin tocar, manda lo guardado.
  const [editados, setEditados] = useState<Partial<Record<keyof Topes, string>>>({});
  const guardado = presupuesto.data;
  const valor = (clave: keyof Topes) => editados[clave] ?? (guardado ? String(guardado[clave]) : "");
  const numeros = Object.fromEntries(CAMPOS_DE_TOPE.map(({ clave }) => [clave, Number(valor(clave))])) as Topes;
  const validos = CAMPOS_DE_TOPE.every(({ clave }) => valor(clave) !== "" && Number.isInteger(numeros[clave]) && numeros[clave] >= 0);

  return (
    <section className="rounded-card border border-border bg-surface p-5" aria-labelledby="presupuesto-gemini">
      <h3 id="presupuesto-gemini" className="mb-1 flex items-center gap-2 text-sm font-semibold">
        <Gauge className="size-4 text-ink-soft" aria-hidden="true" />
        {t.settings.budget.title}
      </h3>
      <p className="mb-4 text-xs text-ink-soft">{t.settings.budget.hint}</p>

      {presupuesto.isPending && <p className="text-xs text-ink-soft">{t.settings.budget.loading}</p>}
      {presupuesto.isError && (
        <ErrorNotice {...comoError(presupuesto.error)} title={t.settings.budget.failed} />
      )}

      {guardado && (
        <div className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            {CAMPOS_DE_TOPE.map(({ clave, texto }) => (
              <label key={clave} className="flex flex-col gap-1.5">
                <span className="text-xs text-ink-soft">{t.settings.budget[texto]}</span>
                <input
                  type="number"
                  min={0}
                  step={1}
                  inputMode="numeric"
                  value={valor(clave)}
                  onChange={(event) => setEditados((previos) => ({ ...previos, [clave]: event.target.value }))}
                  className={campo}
                />
              </label>
            ))}
          </div>
          <p className="text-xs text-ink-soft">
            {t.settings.budget.spentToday
              .replace("{calls}", guardado.spentToday.calls.toLocaleString())
              .replace("{tokens}", guardado.spentToday.tokens.toLocaleString())}
          </p>
          <div>
            <button
              type="button"
              disabled={!validos || guardar.isPending}
              onClick={() => guardar.mutate(numeros, { onSuccess: () => setEditados({}) })}
              className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-40"
            >
              {guardar.isPending ? t.settings.saving : t.settings.budget.save}
            </button>
          </div>
          {guardar.isError && <ErrorNotice {...comoError(guardar.error)} />}
          {guardar.isSuccess && !guardar.isPending && (
            <p className="flex items-center gap-1 text-xs text-ok">
              <CheckCircle2 className="size-3.5" aria-hidden="true" />
              {t.settings.budget.saved}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

/**
 * Selector de un modelo de Gemini. La primera opción es «automático» y dice
 * cuál se usaría; el resto son los modelos que la clave puede usar.
 */
function SelectorDeModelo({
  etiqueta,
  pista,
  valor,
  automatico,
  lista,
  onChange,
  clase,
}: {
  etiqueta: string;
  pista: string;
  valor: string;
  automatico: string | null;
  lista: GeminiModelsResult;
  onChange: (valor: string) => void;
  clase: string;
}) {
  const t = useT();
  const guardadoAusente = valor !== "" && !lista.models.some((m) => m.id === valor);
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-ink-soft">{etiqueta}</span>
      <select value={valor} onChange={(event) => onChange(event.target.value)} className={clase}>
        <option value="">
          {`${t.settings.automatic} (${automatico ?? t.settings.noCandidate})`}
        </option>
        {guardadoAusente && (
          <option value={valor}>{`${valor} — ${t.settings.modelGone}`}</option>
        )}
        {lista.models.map((modelo) => (
          <option key={modelo.id} value={modelo.id}>
            {modelo.id}
          </option>
        ))}
      </select>
      {guardadoAusente && <ErrorNotice code="llm_model_unavailable" detail={valor} />}
      <span className="text-[11px] leading-relaxed text-ink-faint">{pista}</span>
    </label>
  );
}
