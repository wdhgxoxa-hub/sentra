import {
  CheckCircle2,
  Database,
  Eye,
  EyeOff,
  Globe,
  KeyRound,
  Monitor,
  Moon,
  Sparkles,
  Sun,
  XCircle,
} from "lucide-react";
import { useState } from "react";

import { ErrorNotice } from "@/components/ErrorNotice";
import { Explain } from "@/components/Explain";
import { comoError } from "@/lib/errors";
import {
  useGeminiModels,
  useSaveCredentials,
  useSaveGeminiKey,
  useSetFetcherMode,
  useSettings,
  useTestConnection,
  useTestGeminiKey,
} from "@/lib/queries";
import {
  useSettingsStore,
  useT,
  type Language,
  type Theme,
} from "@/stores/settingsStore";
import type { FetcherMode, GeminiModelsResult } from "@/types/radar";

const LANGUAGES: Array<{ value: Language; label: string }> = [
  { value: "es", label: "Español" },
  { value: "en", label: "English" },
];

/**
 * Configuración: apariencia, fuente de datos y credenciales.
 *
 * Existe para que no haya que abrir una terminal y editar un `.env` a mano.
 * El secreto se envía una vez y no vuelve nunca: lo que se muestra después
 * es solo si está configurado y un Client ID enmascarado.
 */
export function SettingsView() {
  const t = useT();
  const language = useSettingsStore((state) => state.language);
  const setLanguage = useSettingsStore((state) => state.setLanguage);
  const theme = useSettingsStore((state) => state.theme);
  const setTheme = useSettingsStore((state) => state.setTheme);

  const settings = useSettings();
  const setMode = useSetFetcherMode();
  const saveCredentials = useSaveCredentials();
  const testConnection = useTestConnection();
  const guardarGemini = useSaveGeminiKey();
  const probarGemini = useTestGeminiKey();

  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  // Sin valor por defecto: cualquiera sería de relleno, y el motor lo
  // rechaza (AUD-014). El formato se enseña como marcador.
  const [userAgent, setUserAgent] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
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

  const guardar = (event: React.FormEvent) => {
    event.preventDefault();
    saveCredentials.mutate(
      { clientId, clientSecret, userAgent, username, password },
      {
        onSuccess: () => {
          // El secreto se borra del formulario en cuanto viaja: no tiene
          // por qué seguir en memoria ni visible en pantalla.
          setClientSecret("");
          setPassword("");
        },
      },
    );
  };

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

      {/* --- Fuente de datos --- */}
      <section className="rounded-card border border-border bg-surface p-5">
        <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold">
          <Database className="size-4 text-ink-soft" aria-hidden="true" />
          {t.settings.source}
        </h3>
        <p className="mb-3 text-xs leading-relaxed text-ink-soft">
          {t.settings.sourceHint}
        </p>

        <div className="grid gap-2 sm:grid-cols-2">
          {(["synthetic", "reddit"] as FetcherMode[]).map((mode) => {
            const activo = settings.data?.fetcherMode === mode;
            const titulo =
              mode === "synthetic"
                ? t.settings.modeSynthetic
                : t.settings.modeReddit;
            const descripcion =
              mode === "synthetic"
                ? t.settings.modeSyntheticDesc.replace(
                    "{count}",
                    String(settings.data?.syntheticPosts ?? 0),
                  )
                : t.settings.modeRedditDesc;

            return (
              <button
                key={mode}
                type="button"
                disabled={setMode.isPending || !settings.data}
                onClick={() => setMode.mutate(mode)}
                aria-pressed={activo}
                className={`rounded-lg border p-3 text-left transition-colors disabled:opacity-50 ${
                  activo
                    ? "border-accent bg-accent-soft"
                    : "border-border hover:bg-surface-2"
                }`}
              >
                <span className="block text-sm font-medium">{titulo}</span>
                <span className="mt-0.5 block text-xs text-ink-soft">
                  {descripcion}
                </span>
              </button>
            );
          })}
        </div>
        {setMode.isError && (
          <div className="mt-2">
            <ErrorNotice {...comoError(setMode.error)} title={t.settings.modeFailed} />
          </div>
        )}
      </section>

      {/* --- Credenciales --- */}
      <section className="rounded-card border border-border bg-surface p-5">
        <h3 className="mb-1 flex items-center gap-2 text-sm font-semibold">
          <KeyRound className="size-4 text-ink-soft" aria-hidden="true" />
          {t.settings.credentials}
          {settings.data?.credentials && (
            <span
              className={`ml-auto rounded-full px-2 py-0.5 text-[11px] font-medium ${
                settings.data.credentials.configured
                  ? "bg-ok/15 text-ok"
                  : "bg-surface-2 text-ink-faint"
              }`}
            >
              {settings.data.credentials.configured
                ? `${t.settings.configured} · ${settings.data.credentials.clientIdMasked}`
                : t.settings.notConfigured}
            </span>
          )}
        </h3>
        <p className="mb-3 text-xs leading-relaxed text-ink-soft">
          {t.settings.credentialsHint}
        </p>

        <form onSubmit={guardar} className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs text-ink-soft">
                {t.settings.clientId}
              </span>
              <input
                value={clientId}
                onChange={(event) => setClientId(event.target.value)}
                autoComplete="off"
                className={campo}
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs text-ink-soft">
                {t.settings.clientSecret}
              </span>
              <input
                type="password"
                value={clientSecret}
                onChange={(event) => setClientSecret(event.target.value)}
                autoComplete="off"
                className={campo}
              />
            </label>
          </div>

          <label className="flex flex-col gap-1.5">
            <span className="flex items-center gap-1 text-xs text-ink-soft">
              {t.settings.userAgent}
              <Explain
                title={t.settings.userAgent}
                body={t.settings.userAgentHint}
              />
            </span>
            <input
              value={userAgent}
              onChange={(event) => setUserAgent(event.target.value)}
              placeholder={t.settings.userAgentPlaceholder}
              className={`${campo} font-mono text-xs`}
            />
          </label>

          <details className="text-xs">
            <summary className="cursor-pointer text-ink-soft">
              {t.settings.userHint}
            </summary>
            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="text-ink-soft">
                  {t.settings.username}
                </span>
                <input
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  autoComplete="off"
                  className={campo}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-ink-soft">
                  {t.settings.password}
                </span>
                <input
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="off"
                  className={campo}
                />
              </label>
            </div>
          </details>

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="submit"
              disabled={saveCredentials.isPending || !clientId || !clientSecret || !userAgent.trim()}
              className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-on-accent transition-colors hover:bg-accent-hover disabled:opacity-40"
            >
              {saveCredentials.isPending ? t.pipeline.saving : t.settings.save}
            </button>

            <button
              type="button"
              disabled={
                testConnection.isPending || !settings.data?.credentials?.configured
              }
              onClick={() => testConnection.mutate()}
              className="rounded-lg border border-border px-3 py-2 text-sm transition-colors hover:bg-surface-2 disabled:opacity-40"
            >
              {testConnection.isPending ? t.settings.testing : t.settings.test}
            </button>

            {saveCredentials.isSuccess && !saveCredentials.isPending && (
              <span className="inline-flex items-center gap-1 text-xs text-ok">
                <CheckCircle2 className="size-3.5" aria-hidden="true" />
                {t.settings.saved}
              </span>
            )}
          </div>

          {(saveCredentials.isError || testConnection.isError) && (
            <ErrorNotice {...comoError(saveCredentials.error ?? testConnection.error)} />
          )}

          {testConnection.data && (
            <p
              className={`flex items-start gap-1.5 rounded-lg p-2.5 text-xs ${
                testConnection.data.ok
                  ? "bg-ok/10 text-ok"
                  : "bg-danger/10 text-danger"
              }`}
            >
              {testConnection.data.ok ? (
                <CheckCircle2 className="mt-px size-3.5 shrink-0" aria-hidden="true" />
              ) : (
                <XCircle className="mt-px size-3.5 shrink-0" aria-hidden="true" />
              )}
              {testConnection.data.detail}
            </p>
          )}

          {settings.data && (
            <p className="text-[11px] text-ink-faint">
              {t.settings.storedIn}{" "}
              <code className="font-mono">{settings.data.envPath}</code>.{" "}
              {t.settings.secretNeverShown}
            </p>
          )}
        </form>
      </section>

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
                ? t.pipeline.saving
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

          {probarGemini.data && (
            <p
              className={`flex items-start gap-1.5 rounded-lg p-2.5 text-xs ${
                probarGemini.data.ok ? "bg-ok/10 text-ok" : "bg-danger/10 text-danger"
              }`}
            >
              {probarGemini.data.ok ? (
                <CheckCircle2 className="mt-px size-3.5 shrink-0" aria-hidden="true" />
              ) : (
                <XCircle className="mt-px size-3.5 shrink-0" aria-hidden="true" />
              )}
              {probarGemini.data.detail}
            </p>
          )}
        </div>
      </section>
    </div>
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
