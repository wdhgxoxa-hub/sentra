/**
 * Diccionario en español (idioma de referencia).
 *
 * `en.ts` debe cumplir este mismo tipo, así que añadir una clave aquí sin
 * traducirla allí es un error de compilación, no un texto que aparece en
 * español en medio de la interfaz inglesa.
 */
export const es = {
  app: {
    name: "SENTRA",
    tagline: "Escucha el mercado antes de construir",
  },

  error: {
    title: "Esta vista no se pudo pintar",
    hint: "El fallo se queda aqui: el resto de la aplicación sigue funcionando. Puedes cambiar de sección en el menú de la izquierda o volver a intentarlo.",
    details: "Ver detalle técnico",
    retry: "Reintentar",
  },
  nav: {
    radar: "Radar en vivo",
    search: "Búsqueda semántica",
    settings: "Configuración",
    sources: "Fuentes",
  },

  health: {
    checking: "comprobando…",
    database: "Base de datos",
    engine: "Motor",
    up: "activo",
    down: "sin respuesta",
    noBackend: "sin respuesta del backend",
    retryEngine: "Reintentar motor",
    retrying: "Arrancando el motor…",
  },

  radar: {
    title: "Top {target} del juez",
    subtitle: "Los nichos de la última ejecución juzgada: CONSTRUIR primero, sin rellenar",
    empty: "Todavía no hay ningún escaneo juzgado.",
    emptyHint: "Lanza un escaneo desde Fuentes: el juez agrupa la evidencia y decide cada nicho.",
    loading: "Cargando…",
    error: "No se pudo leer el juez.",
    restTitle: "Resto de veredictos ({n})",
    restSubtitle: "Mismo escaneo y mismo orden; el detalle completo está en el Top",
    members: "{n} piezas",
    feedEmpty: "Todavía no hay evidencia. Lanza un escaneo desde Fuentes.",
    feedError: "No se pudo leer la evidencia reciente.",
    feedTitle: "Evidencia reciente",
    feedSubtitle: "Lo último que han traído las fuentes, con su atribución",
    mentions: "menciones",
    communities: "comunidades",
    intensity: "Intensidad",
    validate: "Validar",
    points: "pts",
    filterAll: "Todas",
    filterPending: "Sin revisar",
  },

  search: {
    title: "Búsqueda semántica",
    subtitle:
      "Busca por significado, no solo por palabras exactas. Compara ambas.",
    placeholder: "describe un problema con tus palabras",
    error: "La búsqueda falló.",
    searching: "Buscando…",
    empty: "Sin resultados para esa consulta.",
    emptyHint: "Prueba con una de las sugerencias, o lanza un escaneo desde Fuentes.",
    suggestions: "Prueba con",
    colText: "Texto",
    colSemantic: "Semántica",
    colExact: "Exacta",
    colCombined: "Combinada",
    onlySemantic: "Solo por significado",
    onlyExact: "Solo por palabras",
    both: "Por ambas vías",
  },

  settings: {
    saving: "Guardando…",
    title: "Configuración",
    subtitle: "Idioma, tema y motor de IA",
    appearance: "Apariencia",
    language: "Idioma",
    theme: "Tema",
    themeLight: "Claro",
    themeDark: "Oscuro",
    themeSystem: "Automático",
    testing: "Probando…",
    configured: "Configurada",
    notConfigured: "Sin configurar",
    loading: "Consultando al motor…",
    unreachable:
      "No se pudo leer la configuración del motor. El idioma y el tema siguen funcionando; la clave y los modelos de Gemini necesitan que el motor esté en marcha.",
    aiEngine: "Motor de IA (Google Gemini)",
    aiHint:
      "La clave se pide en aistudio.google.com y se guarda en el .env del proyecto. Sin ella, el juez no etiqueta la evidencia (nada sale Construir) y no se pueden generar el dossier ni el plan.",
    apiKey: "Clave de API",
    showKey: "Mostrar",
    hideKey: "Ocultar",
    modelDocuments: "Modelo para documentos",
    modelDocumentsHint:
      "Escribe el dossier y el plan de construcción de cada veredicto. Automático: el Pro 3.x más reciente que admita tu clave.",
    modelGeneral: "Modelo general",
    modelGeneralHint:
      "Etiqueta la evidencia para el juez y hace de abogado del diablo. Automático: el Flash 3.x estable más reciente que admita tu clave.",
    automatic: "Automático",
    noCandidate: "sin candidato disponible",
    modelGone: "ya no está disponible",
    modelsNeedKey:
      "Guarda la clave para ver los modelos que puede usar. La lista se pide a Google, no está escrita en la aplicación.",
    modelsLoading: "Consultando los modelos de tu clave…",
    modelsListedAt:
      "Lista de modelos pedida a Google {ago}; se reutiliza un día. «Probar clave» la vuelve a pedir.",
    modelsFailed: "No se pudo obtener la lista de modelos.",
    saveModels: "Guardar modelos",
    keySaved: "Clave guardada",
    probeFailed: "No se pudo probar la clave.",
    saveKey: "Guardar clave",
    testKey: "Probar clave",
  },

  /** Explicaciones didácticas de cada métrica. */
  explain: {
    rrf: {
      title: "Fusión de resultados (RRF)",
      body:
        "Combina dos búsquedas: la que entiende el significado y la que busca palabras exactas. Un resultado que aparece alto en ambas sube al principio; uno que solo aparece en una, queda por debajo.",
    },
    semantic: {
      title: "Búsqueda por significado",
      body:
        "Encuentra textos parecidos aunque no compartan ni una palabra: «los avisos llegan tarde» encuentra «las notificaciones tardan horas». Falla con nombres propios raros.",
    },
    exact: {
      title: "Búsqueda por palabras",
      body:
        "Busca las palabras tal cual en el título y el texto, sin reducirlas a su raíz, y ordena por cuántas aparecen y lo juntas que están. Es la que rescata nombres de herramientas como «pgpool» o «Stripe», donde el significado no ayuda.",
    },
  },

  source: {
    demo: "Datos de demostración",
    real: "Datos reales",
    unknown: "Fuente desconocida",
  },

  /**
   * Un texto por cada código de error que puede llegar a la interfaz (D-A).
   * Los de Rust los exige src-tauri/src/db.rs; los del motor Gemini,
   * tests/test_gemini_robustness.py.
   */
  errors: {
    env_value_invalid: "El valor no se puede guardar tal cual: lleva saltos de línea u otros caracteres de control.",
    documents_unavailable: "Los documentos necesitan PostgreSQL y un escaneo juzgado; revisa la salud del motor.",
    verdict_not_found: "Ese veredicto ya no existe. Vuelve a cargar el juez.",
    plan_not_recommended:
      "El juez no recomienda construir este nicho: el plan solo se genera si lo fuerzas, y lleva la advertencia en cada página.",
    search_unavailable: "La búsqueda necesita PostgreSQL y los vectores de la evidencia; revisa la salud del motor.",
    source_error: "La fuente rechazó la petición.",
    source_credentials_missing: "Esta fuente necesita credenciales: configúralas en la sección Fuentes.",
    source_auth_failed: "La fuente rechazó las credenciales guardadas: revísalas y vuelve a probarla.",
    source_forbidden: "La fuente denegó el acceso a lo pedido.",
    source_not_found: "La fuente no encontró lo pedido (comunidad, sitio o recurso inexistente).",
    source_unavailable: "La fuente no responde ahora mismo. Se reintentó; prueba más tarde.",
    source_rate_limited: "La fuente pide esperar: se agotó su cuota. El resto de fuentes sigue.",
    source_budget_exhausted: "Se agotó el presupuesto de esta fuente para el escaneo.",
    source_pending_approval:
      "Esta fuente aún no tiene aprobación para llamadas reales: no se consulta ni se prueba.",
    no_active_sources: "No hay ninguna fuente activa: enciende o configura alguna en la sección Fuentes.",
    migrations_pending:
      "La base de datos va por detrás de la aplicación: faltan migraciones. Aplícalas con scripts/migrate.py (el detalle dice cuáles).",
    unknown: "Ocurrió un error inesperado.",
    database: "No se pudo leer o escribir en la base de datos. Comprueba que PostgreSQL está en marcha.",
    database_unavailable: "No hay conexión con PostgreSQL: el servidor no respondió o rechazó las credenciales.",
    sidecar: "El motor de análisis respondió con un fallo.",
    sidecar_unreachable: "El motor de análisis no está en marcha. Reinicia la aplicación.",
    sidecar_timeout: "El motor de análisis tardó demasiado en responder.",
    reddit_user_agent_invalid: "El User-Agent debe identificar a la app y a su autor: plataforma:app:versión (by /u/usuario). «tu_usuario» es un ejemplo, no un usuario.",
    python_not_found: "No hay entorno de Python para el motor. Ejecuta scripts/setup_env.ps1 en la carpeta del proyecto (o define RIR_PYTHON) y reinicia la aplicación.",
    sidecar_spawn_failed: "No se pudo lanzar el motor de análisis con el Python configurado.",
    sidecar_port_in_use: "El puerto del motor lo ocupa otro proceso. Ciérralo o define RIR_SIDECAR_PORT y reinicia la aplicación.",
    sidecar_version_mismatch:
      "El motor que contesta es de otra versión que esta ventana. Pulsa «Reintentar motor»; si sigue, recompila la aplicación.",
    sidecar_unpack_failed:
      "No se pudo preparar el motor de esta versión en la carpeta de datos de la aplicación (disco lleno o sin permisos). El detalle lo dice.",
    sidecar_unresponsive: "El motor de análisis se lanzó pero no llegó a responder. El detalle está en sidecar.log.",
    invalid_input: "Los datos enviados no son válidos.",
    file: "No se pudo guardar el archivo.",
    ui_crash: "Esta vista falló al pintarse.",
    persist_failed: "Cosecha completa, pero no se pudo guardar en la base de datos.",
    gemini_not_configured: "No hay clave de Gemini guardada. Se configura en Ajustes.",
    gemini_key_rejected: "Google rechaza la clave de Gemini. Revísala en Ajustes.",
    gemini_error: "Gemini rechazó la petición. Revisa la clave y el modelo en Ajustes.",
    llm_error: "El motor de IA falló.",
    llm_model_unavailable:
      "El modelo guardado ya no está disponible para tu clave. Elige otro en Ajustes.",
    llm_truncated:
      "La respuesta del modelo se cortó al llegar a su límite de salida.",
    llm_invalid_json: "El modelo devolvió una respuesta que no cumple el formato pedido, ni al reintentar.",
    llm_budget_exhausted:
      "Se agotó el presupuesto de tokens del escaneo. Súbelo en Ajustes o escanea menos evidencia.",
    gemini_unavailable: "Gemini no está disponible ahora mismo. Se reintentó varias veces; prueba dentro de un rato.",
    gemini_rate_limited: "Se agotó la cuota de Gemini. Espera un poco o revisa el plan de tu clave.",
    gemini_timeout: "Gemini tardó demasiado en responder. Prueba con gemini-2.5-flash si no necesitas el razonamiento profundo.",
    gemini_blocked: "Gemini bloqueó la respuesta por sus filtros de seguridad.",
    gemini_empty: "Gemini terminó sin escribir nada.",
    gemini_truncated: "El documento se cortó al llegar al límite de longitud del modelo.",
    gemini_incomplete: "El documento llegó sin todas las secciones exigidas.",
    internal_error: "Fallo interno del motor.",
  },

  database: {
    title: "Sin base de datos",
    hint: "Arranca PostgreSQL (o revisa RIR_PG_URL y pgpass.conf) y pulsa Reintentar. Los ajustes siguen disponibles en el menú.",
    retrying: "Conectando…",
  },

  sources: {
    title: "Fuentes",
    subtitle: "De dónde sale la evidencia. Solo APIs oficiales; verde solo con una respuesta real de la API.",
    loading: "Cargando fuentes…",
    unreachable: "No se pudo leer el estado de las fuentes.",
    empty: "No hay ninguna fuente disponible.",
    activeSummary: "{active} de {total} fuentes activas",
    summaryUnknown: "Fuentes: sin datos",
    status: {
      no_configurada: "Sin configurar",
      configurada_sin_verificar: "Sin verificar",
      verificada: "Verificada",
      error: "Error",
      deshabilitada_por_usuario: "Apagada",
    },
    personalOnly: "Solo uso personal",
    excludedByCommercial: "Excluida por el modo comercial",
    excludedUntilProbe: "No entra en el escaneo hasta que la pruebes con éxito.",
    public: "Pública, sin credenciales",
    publicOptional: "Pública; una clave opcional sube la cuota",
    optionalSaved: "Clave opcional guardada: cuota ampliada",
    lastVerified: "Última respuesta real: {when}",
    neverVerified: "Nunca verificada con una respuesta real",
    verifiedButUnconfigured:
      "Respondió en un escaneo con lo que indicaba el perfil, pero no tiene guardado lo que necesita: sin ello no entra en un escaneo automático.",
    terms: "Términos",
    cost: "Coste",
    costUnit: {
      request: "por petición",
      quota_unit: "unidades de cuota",
      usd: "USD",
    },
    probe: "Probar",
    probing: "Probando…",
    probeOk: "Respondió: {detail}",
    enable: "Encender",
    disable: "Apagar",
    credentials: "Credenciales",
    configured: "guardada",
    notConfigured: "falta",
    optional: "opcional",
    saveCredentials: "Guardar credenciales",
    saving: "Guardando…",
    secretHint: "El valor se envía una vez y no vuelve a mostrarse.",
    commercialMode: "Modo comercial",
    commercialModeHint: "Excluye del escaneo las fuentes cuyos términos solo permiten uso personal.",
    scanTitle: "Escanear por perfil",
    scanHint: "Busca en todas las fuentes activas a la vez. El fallo de una no detiene a las demás.",
    profileName: "Nombre del perfil",
    keywords: "Tema (palabras clave, separadas por comas)",
    discovery: "Modo descubrimiento: sin tema, solo frases de dolor",
    windowDays: "Ventana (días)",
    languages: "Idiomas",
    scan: "Escanear",
    scanning: "Escaneando…",
    profileInvalid: "Pon un tema o activa el modo descubrimiento (no los dos).",
    progressTitle: "Progreso por fuente",
    sourceRunning: "En curso · {items} ítems",
    sourceDone: "Terminada · {items} ítems",
    sourceStopped: "Parada por presupuesto · {items} ítems",
    sourceFailed: "Falló · {items} ítems conservados",
    sourceCancelled: "Cancelada · {items} ítems conservados",
    cancel: "Cancelar",
    cancelling: "Cancelando…",
    scanCancelled: "Escaneo cancelado: lo traído hasta ese momento se guarda.",
    requests: "{n} peticiones",
    summary: "{fetched} traídos · {canonical} únicos · {duplicates} duplicados entre fuentes",
    persisted: "Guardado en la ejecución {runId}.",
    notPersisted: "Sin guardar: este escaneo no se persiste.",
    persistFailed: "No se pudo guardar el escaneo en PostgreSQL.",
  },

  judge: {
    title: "Veredictos del juez",
    subtitle: "El LLM etiqueta la evidencia; el veredicto lo decide el código con ocho compuertas.",
    loading: "Cargando veredictos…",
    unreachable: "No se pudieron leer los veredictos.",
    empty: "Todavía no hay ningún escaneo juzgado. Escanea con un perfil y guarda el resultado.",
    verdict: {
      CONSTRUIR: "Construir",
      "INVESTIGAR MÁS": "Investigar más",
      DESCARTAR: "Descartar",
    },
    buildCount: "{count} de {target} nichos para construir",
    score: "Puntaje {score}/100",
    noCommonProblem: "Sin problema común",
    rule: "Regla {rule}",
    missing: "Falta: {gates}",
    corroboration: "Corroboración por fuente",
    gates: "Compuertas",
    gateNames: {
      G0: "Los problemas del grupo son el mismo",
      G1: "Al menos 2 fuentes distintas",
      G2: "Al menos {n} autores distintos",
      G3: "Al menos 1 parche casero",
      G4: "Al menos 1 señal de pago o de búsqueda de herramienta",
      G5: "Ningún hilo ni autor aporta más del 40 %",
      G6: "Al menos el 50 % de los últimos 180 días",
      G7: "Sin competidor gratuito que la mayoría da por bueno",
      G8: "Solo datos reales",
    },
    valueVsThreshold: "{value} · umbral {threshold}",
    notMeasured: "sin datos: no se midió",
    evidenceCount: "{n} evidencias",
    evidenceCountOne: "1 evidencia",
    trend: "{pct} frente al periodo anterior",
    dimensions: "Dimensiones",
    dimensionNames: {
      frecuencia: "Frecuencia",
      convergencia: "Convergencia entre fuentes",
      pago: "Disposición a pagar",
      parches: "Parches caseros",
      hueco: "Hueco de competencia",
      tendencia: "Tendencia",
      viabilidad: "Viabilidad para un desarrollador solo",
    },
    noData: "sin datos",
    noCompetitionData: "sin datos de competencia (valor neutro 0,5, no medido)",
    undetermined: "sin determinar",
    advocate: "Abogado del diablo",
    advocateDowngraded: "Bajó el veredicto: {reason}",
    advocateUnavailable: "No se pudo revisar: un Construir sin revisar baja a Investigar más.",
    advocateNoArguments: "Sin argumentos en contra.",
    advocateDiscarded: "{n} argumentos descartados por citar evidencia ajena al grupo.",
    severity: {
      bloqueante: "Bloqueante",
      importante: "Importante",
      menor: "Menor",
    },
    evidence: "Evidencia",
    oldVersions:
      "Veredicto de versiones antiguas ({versions}): vuelve a escanear para juzgarlo con las actuales.",
    unknownLabeler: "etiquetador desconocido",
    judging: "Juzgando la evidencia…",
    judgeFailed: "El juez falló tras el escaneo; el escaneo sí se guardó.",
    judgeSummary: "{kept} de {items} ítems pasan el filtro · {labeled} etiquetados · {clusters} grupos",
    noLlm: "Sin Gemini: las etiquetas quedan sin determinar y nada sale Construir.",
    summaryByVerdict: "{build} para construir · {research} para investigar más · {discard} descartados",
    seeInRadar: "Ver los veredictos en el Radar",
  },

  documents: {
    title: "Documentos",
    kind: {
      dossier: "Dossier",
      plan: "Plan de construcción",
    },
    format: {
      pdf: "PDF",
      md: "Markdown",
    },
    forcePlan:
      "Generar el plan aunque el juez dice «{verdict}»: llevará la advertencia en cada página.",
    generating: "Generando {kind} con el modelo de documentos; puede tardar unos minutos…",
    failed: "No se pudo generar el documento.",
    cancelled: "Exportación cancelada: no se guardó nada.",
    saved: "Guardado en {path}.",
    calls: "Llamadas al modelo: {n} (0 = se reutilizó lo ya generado).",
    callsUnknown: "El motor no dijo cuántas llamadas al modelo costó.",
  },

  common: {
    technicalDetails: "Detalles técnicos",
    close: "Cerrar",
    retry: "Reintentar",
    loading: "Cargando…",
    whatIsThis: "Qué significa esto",
  },
};

/**
 * Forma que debe cumplir cualquier idioma.
 *
 * Los valores se relajan a `string` a propósito: lo que obliga el tipo es
 * tener TODAS las claves, no repetir los textos en castellano.
 */
type Translated<T> = {
  [K in keyof T]: T[K] extends string ? string : Translated<T[K]>;
};

export type Dictionary = Translated<typeof es>;
