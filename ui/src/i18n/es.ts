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
    pipeline: "Control del pipeline",
    settings: "Configuración",
    opportunity: "Oportunidad",
    sources: "Fuentes",
  },

  health: {
    checking: "comprobando…",
    database: "Base de datos",
    engine: "Motor",
    up: "activo",
    down: "sin respuesta",
    noBackend: "sin respuesta del backend",
    heuristicNli: "NLI heurístico",
    heuristicNliHint:
      "El clasificador funciona con reglas, no con un modelo de lenguaje. Las etiquetas de intención y severidad son orientativas.",
    sourceStates: {
      demo: "Demostración: datos fabricados",
      reddit_sin_credenciales: "Reddit: faltan credenciales",
      reddit_sin_verificar: "Reddit: credenciales guardadas, sin verificar",
      reddit_verificado: "Reddit: verificado",
      reddit_error: "Reddit: error",
    },
    sourceUnknown: "Fuente: sin información del motor",
    sourceVerifiedAt: "último acceso real a las {time}",
  },

  radar: {
    title: "Oportunidades detectadas",
    subtitle: "Problemas que se repiten en varias comunidades",
    empty: "Todavía no hay ningún problema que supere el corte.",
    emptyHint:
      "Un dolor necesita repetirse en varias comunidades para convertirse en oportunidad. Lanza un escaneo desde Control del pipeline.",
    loading: "Cargando…",
    error: "No se pudo cargar el tablero.",
    feedEmpty: "Todavía no hay señales que superen el corte. Lanza un escaneo desde Pipeline.",
    feedError: "No se pudo leer el feed de señales.",
    feedTitle: "Actividad reciente",
    feedSubtitle: "Quejas sueltas, aún sin consolidar",
    mentions: "menciones",
    communities: "comunidades",
    intensity: "Intensidad",
    validate: "Validar",
    points: "pts",
    filterAll: "Todas",
    filterPending: "Sin revisar",
  },

  detail: {
    selectPrompt: "Elige una oportunidad del radar para ver su ficha.",
    loading: "Cargando ficha…",
    gone: "Esa oportunidad ya no está en el almacén.",
    job: "Qué necesita la gente",
    breakdown: "De dónde sale la puntuación",
    solutions: "Herramientas que ya usan",
    evolution: "Cómo ha evolucionado",
    noEvolution:
      "Una sola lectura por ahora. La evolución aparece cuando el mismo problema se detecta en escaneos sucesivos.",
    validation: "Validación",
    notes: "Notas de análisis",
    notesPlaceholder: "Qué se construiría, para quién, y por qué ahora",
    saveNotes: "Guardar notas",
    decidedOn: "Decidido el",
    noDecision: "Sin decisión registrada todavía",
    saveError: "No se pudo guardar",
    total: "Total",
  },

  search: {
    title: "Búsqueda semántica",
    subtitle:
      "Busca por significado, no solo por palabras exactas. Compara ambas.",
    placeholder: "no puedo exportar mis facturas",
    error: "La búsqueda falló.",
    searching: "Buscando…",
    empty: "Sin resultados para esa consulta.",
    emptyHint: "Prueba con una de las sugerencias, o lanza un escaneo primero.",
    suggestions: "Prueba con",
    colText: "Texto",
    colSemantic: "Semántica",
    colExact: "Exacta",
    colCombined: "Combinada",
    onlySemantic: "Solo por significado",
    onlyExact: "Solo por palabras",
    both: "Por ambas vías",
    examples: {
      billing: "Facturación rota",
      migration: "Migración lenta",
      support: "Soporte repetitivo",
      pricing: "Precios confusos",
    },
  },

  pdf: {
    export: "Exportar PDF",
    exporting: "Generando PDF…",
    withPlan: "Incluirá el plan de arquitectura generado en esta sesión.",
    withoutPlan: "Sin plan de arquitectura en esta sesión: el PDF lo indicará como no generado.",
    saved: "PDF guardado en {path}",
    cancelled: "Exportación cancelada: no se guardó ningún archivo.",
    error: "No se pudo exportar el PDF. Comprueba que el motor está activo e inténtalo de nuevo.",
  },
  topSix: {
    title: "Top {target} oportunidades",
    titleGeneric: "Mejores oportunidades",
    loading: "Cargando las mejores oportunidades…",
    error: "No se pudo leer el resultado de la última ejecución.",
    noRuns: "Todavía no hay ninguna ejecución terminada. Lanza un escaneo desde Pipeline.",
    complete: "Completo ({found}/{target})",
    partial: "Incompleto ({found}/{target})",
    incomplete: "Solo {found} de {target} oportunidades superan el corte.",
    open: "Abrir ficha",
    reasons: {
      fuentes_agotadas: "Se revisó todo lo disponible y el resto de problemas no alcanza la puntuación mínima.",
      limite_ciclos: "Se alcanzó el límite de ciclos del escaneo con contenido todavía por revisar.",
      sin_acceso_reddit: "No se pudo leer la fuente de datos.",
      datos_insuficientes: "No hay datos suficientes: la fuente se agotó antes de reunir tantos problemas distintos.",
    },
  },
  scanErrors: {
    reddit_credentials_missing: "Faltan las credenciales de Reddit. Guárdalas en Configuración.",
    reddit_user_agent_invalid: "El User-Agent de Reddit no identifica a la app y a su autor. Usa plataforma:app:versión (by /u/tu-usuario-real) en Configuración.",
    reddit_auth_failed: "Reddit rechazó las credenciales. Revisa el Client ID y el Client Secret.",
    reddit_forbidden: "Reddit denegó el acceso a esta comunidad.",
    reddit_not_found: "La comunidad no existe o es privada.",
    reddit_rate_limited: "Reddit ha limitado las peticiones. Vuelve a intentarlo en {seconds} s.",
    reddit_rate_limited_unknown: "Reddit ha limitado las peticiones. Espera antes de reintentar.",
    reddit_unavailable: "Reddit no está disponible en este momento.",
    fetch_failed: "La fuente de datos falló y el escaneo no trajo nada.",
    internal_error: "El motor falló durante el escaneo.",
  },
  pipeline: {
    title: "Control del pipeline",
    subtitle: "Lanza escaneos y observa el motor trabajar",
    running: "Escaneos en curso",
    clearFinished: "Limpiar terminados",
    cancel: "Cancelar",
    cancelled: "Cancelado",
    watched: "Comunidades vigiladas",
    addPlaceholder: "r/SaaS",
    tagsPlaceholder: "vertical, prioritario",
    tagsLabel: "Etiquetas (separadas por comas)",
    order: "Orden",
    subreddit: "Comunidad",
    watch: "Vigilar",
    saving: "Guardando…",
    scan: "Escanear",
    pause: "Pausar",
    activate: "Activar",
    lastRun: "última ejecución",
    never: "nunca",
    noSubreddits: "Todavía no vigilas ninguna comunidad. Añade una arriba.",
    noRuns: "Todavía no hay ejecuciones.",
    subredditsError: "No se pudo leer la lista de comunidades.",
    runsError: "No se pudo leer el historial de ejecuciones.",
    saveFailed: "No se pudo guardar la comunidad.",
    scanFailed: "No se pudo lanzar el escaneo.",
    cancelFailed: "No se pudo cancelar el escaneo.",
    history: "Ejecuciones recientes",
    colSource: "Fuente",
    colStatus: "Estado",
    colRead: "Leídos",
    colQualified: "Cualificados",
    colErrors: "Errores",
    cycle: "ciclo",
    read: "leídos",
    analysed: "analizados",
    stored: "guardados",
    clusters: "problemas",
    qualified: "cualificados",
    discard: "descartar",
    nodes: {
      fetch: "Descarga",
      filter: "Filtrado",
      comments: "Comentarios",
      intelligence: "Análisis",
      storage: "Guardado",
      quality_gate: "Corte",
      aggregate: "Agrupado",
    },
    nodeHints: {
      fetch: "Trae publicaciones de la comunidad elegida.",
      filter: "Descarta el ruido: saludos, spam y publicidad encubierta.",
      comments: "Trae los comentarios más votados de las quejas que pasaron el filtro.",
      intelligence: "Lee cada queja y puntúa cuánto duele.",
      storage: "Guarda todo para poder buscarlo después.",
      quality_gate: "Aparta las quejas demasiado flojas.",
      aggregate: "Junta las quejas que hablan del mismo problema.",
    },
  },

  settings: {
    title: "Configuración",
    subtitle: "Credenciales, idioma y fuente de datos",
    appearance: "Apariencia",
    language: "Idioma",
    theme: "Tema",
    themeLight: "Claro",
    themeDark: "Oscuro",
    themeSystem: "Automático",
    source: "Fuente de datos",
    sourceHint:
      "El modo demostración usa un conjunto fijo de publicaciones fabricadas. Todo lo demás —el análisis, el agrupado, la búsqueda— funciona igual.",
    modeSynthetic: "Demostración",
    modeSyntheticDesc: "{count} publicaciones fabricadas, siempre las mismas",
    modeReddit: "Reddit real",
    modeRedditDesc: "Requiere credenciales de la API de Reddit",
    credentials: "Credenciales de Reddit",
    credentialsHint:
      "Se crean en reddit.com/prefs/apps eligiendo el tipo «script». Se guardan en el archivo .env del proyecto, nunca en la base de datos.",
    clientId: "Client ID",
    clientSecret: "Client Secret",
    userAgent: "User Agent",
    userAgentHint: "Reddit pide que identifique a la aplicación y a su autor, con la forma plataforma:app:versión (by /u/usuario) y tu usuario real de Reddit.",
    userAgentPlaceholder: "windows:sentra:0.1.0 (by /u/tu-usuario-de-reddit)",
    username: "Usuario (opcional)",
    password: "Contraseña (opcional)",
    userHint: "Si los rellenas, se usa el flujo en nombre del usuario, con más cuota.",
    save: "Guardar credenciales",
    saved: "Credenciales guardadas",
    test: "Probar conexión",
    testing: "Probando…",
    configured: "Configuradas",
    notConfigured: "Sin configurar",
    loading: "Consultando al motor…",
    unreachable:
      "No se pudo leer la configuración del motor. El idioma y el tema siguen funcionando; la fuente de datos y las credenciales necesitan que el motor esté en marcha.",
    aiEngine: "Motor de IA (Google Gemini)",
    aiHint:
      "La clave se pide en aistudio.google.com y se guarda en el mismo .env que las de Reddit. Sin ella, el botón de arquitectura de cada oportunidad queda inactivo.",
    apiKey: "Clave de API",
    showKey: "Mostrar",
    hideKey: "Ocultar",
    modelDocuments: "Modelo para documentos",
    modelDocumentsHint:
      "Escribe el plan de arquitectura. Automático: el Pro 3.x más reciente que admita tu clave.",
    modelGeneral: "Modelo general",
    modelGeneralHint:
      "Traduce citas y etiqueta evidencia. Automático: el Flash 3.x estable más reciente que admita tu clave.",
    automatic: "Automático",
    noCandidate: "sin candidato disponible",
    modelGone: "ya no está disponible",
    modelsNeedKey:
      "Guarda la clave para ver los modelos que puede usar. La lista se pide a Google, no está escrita en la aplicación.",
    modelsLoading: "Consultando los modelos de tu clave…",
    modelsFailed: "No se pudo obtener la lista de modelos.",
    saveModels: "Guardar modelos",
    modeFailed: "No se pudo cambiar la fuente de datos.",
    keySaved: "Clave guardada",
    probeFailed: "No se pudo probar la clave.",
    saveKey: "Guardar clave",
    testKey: "Probar clave",
    storedIn: "Se guardan en",
    secretNeverShown:
      "El secreto no se muestra nunca una vez guardado, ni siquiera a esta ventana.",
  },

  architect: {
    open: "Generar arquitectura con Gemini",
    regenerate: "Volver a generar",
    close: "Ocultar arquitectura",
    generating: "El modelo está escribiendo…",
    error: "No se pudo generar la arquitectura",
    copy: "Copiar en Markdown",
    copied: "Copiado al portapapeles",
    copyFailed: "No se pudo copiar",
    copyCode: "Copiar bloque",
    empty:
      "Púlsalo y Gemini redacta un plan de construcción en dos fases a partir de esta evidencia: un MVP para 24-48 h y el producto completo para cuando valide.",
    warning:
      "Esto lo escribe un modelo generativo, no el radar. Revisa el código y el esquema antes de ejecutarlos.",
    incomplete: "Documento incompleto: no se guarda para el PDF.",
    missing: "Secciones que faltan",
  },
  blueprint: {
    open: "Ver especificación del proyecto (PRD)",
    close: "Ocultar especificación",
    title: "Especificación del proyecto",
    loading: "Redactando el documento…",
    error: "No se pudo redactar la especificación",
    copy: "Copiar documento en Markdown",
    copied: "Copiado al portapapeles",
    copyFailed: "No se pudo copiar",
    value: "Propuesta de valor",
    derived:
      "Documento derivado de la evidencia guardada, sin inventar nada: donde no hay dato, lo dice.",
  },
  quotes: {
    anonymousAuthor: "autor anónimo",
    title: "Lo que dijeron",
    count: "citas",
    translate: "Traducir al español",
    showOriginal: "Ver original",
    translating: "Traduciendo…",
    error: "No se pudieron traducir las citas",
    approximate: "Traducción aproximada: solo se ha traducido lo reconocido.",
    approximateShort: "aproximada",
    offlineHint:
      "Sin clave de Gemini traduce el motor sin conexión, que solo reconoce expresiones frecuentes.",
  },
  validation: {
    new: "Sin revisar",
    triaged: "En estudio",
    validated: "Validada",
    rejected: "Descartada",
    shipped: "Construida",
  },

  urgency: {
    CRITICAL: "Crítica",
    HIGH: "Alta",
    MEDIUM: "Media",
    LOW: "Baja",
  },

  intent: {
    ready_to_buy: "Listo para comprar",
    seeking_recommendation: "Busca recomendación",
    seeking_alternative: "Busca alternativa",
    comparing_products: "Comparando productos",
    casual_discussion: "Conversación casual",
    undetermined: "Indeterminada: sin evidencia suficiente",
    none: "Sin intención",
  },

  pain: {
    severe_blocker: "Bloqueante grave",
    time_consuming_friction: "Fricción costosa",
    minor_inconvenience: "Molestia menor",
    no_problem: "Sin problema",
    undetermined: "Indeterminada: sin evidencia suficiente",
    none: "Sin clasificar",
  },

  /** Explicaciones didácticas de cada métrica. */
  explain: {
    jtbd: {
      title: "Jobs-To-Be-Done",
      body:
        "La tarea que alguien intenta terminar y no puede. En vez de «quiere una app de facturas», dice «necesita cobrar sin copiar datos a mano». Enfocarse en la tarea evita construir una copia de lo que ya existe.",
    },
    spread: {
      title: "Difusión",
      body:
        "En cuántas comunidades distintas aparece el problema. Diez quejas en un solo foro son un foro descontento; una queja en diez foros es un patrón de mercado.",
    },
    frequency: {
      title: "Frecuencia",
      body:
        "Cuántas veces se repite dentro de cada comunidad. Mide si es un problema recurrente o algo que alguien dijo una vez.",
    },
    severity: {
      title: "Severidad",
      body:
        "Cuánto duele. No es lo mismo «sería cómodo tenerlo» que «esto me bloquea el trabajo». Se deduce del lenguaje de cada mensaje.",
    },
    recency: {
      title: "Recencia",
      body:
        "Cuán reciente es la queja más nueva. Decae exponencialmente: un problema del que nadie habla desde hace un año probablemente ya se resolvió.",
    },
    paidSignal: {
      title: "Disposición a pagar",
      body:
        "Si alguien dijo explícitamente que pagaría, o mencionó lo que le cuesta el problema. Es la diferencia entre una molestia y un mercado.",
    },
    intensity: {
      title: "Intensidad",
      body:
        "La suma ponderada de los cinco factores, de 0 a 100. A partir de 60 se considera una oportunidad que merece atención.",
    },
    rrf: {
      title: "Fusión de resultados (RRF)",
      body:
        "Combina dos búsquedas: la que entiende el significado y la que busca palabras exactas. Un resultado que aparece alto en ambas sube al principio; uno que solo aparece en una, queda por debajo.",
    },
    semantic: {
      title: "Búsqueda por significado",
      body:
        "Encuentra textos parecidos aunque no compartan ni una palabra. «Facturación rota» encuentra «no puedo exportar mis recibos». Falla con nombres propios raros.",
    },
    exact: {
      title: "Búsqueda por palabras (BM25)",
      body:
        "Busca las palabras tal cual, dando más peso a las poco frecuentes. Es la que rescata nombres de herramientas como «pgpool» o «Stripe», donde el significado no ayuda.",
    },
    cluster: {
      title: "Agrupado de problemas",
      body:
        "Junta las quejas que hablan de lo mismo aunque estén en foros distintos. Sin esto, cada mensaje se vería suelto y ningún patrón alcanzaría el corte.",
    },
    signalVsCluster: {
      title: "Quejas y oportunidades",
      body:
        "Una queja suelta casi nunca justifica construir algo. Una oportunidad es un problema que se repite en varias comunidades. Por eso hay dos listas y dos umbrales distintos.",
    },
  },

  source: {
    demo: "Datos de demostración",
    reddit: "Datos de Reddit",
    unknown: "Fuente desconocida",
  },

  /**
   * Un texto por cada código de error que puede llegar a la interfaz (D-A).
   * Los de Rust los exige src-tauri/src/db.rs; los del motor Gemini,
   * tests/test_gemini_robustness.py.
   */
  errors: {
    source_error: "La fuente rechazó la petición.",
    source_credentials_missing: "Esta fuente necesita credenciales: configúralas en la sección Fuentes.",
    source_auth_failed: "La fuente rechazó las credenciales. Revísalas en la sección Fuentes.",
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
    sidecar_unresponsive: "El motor de análisis se lanzó pero no llegó a responder. El detalle está en sidecar.log.",
    invalid_input: "Los datos enviados no son válidos.",
    file: "No se pudo guardar el archivo.",
    ui_crash: "Esta vista falló al pintarse.",
    persist_failed: "Cosecha completa, pero no se pudo guardar en la base de datos.",
    gemini_not_configured: "No hay clave de Gemini guardada. Se configura en Ajustes.",
    gemini_error: "Gemini rechazó la petición. Revisa la clave y el modelo en Ajustes.",
    llm_error: "El motor de IA falló.",
    llm_model_unavailable:
      "El modelo guardado ya no está disponible para tu clave. Elige otro en Ajustes.",
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
    architect_protocol: "El motor devolvió una respuesta que la aplicación no entiende.",
    architect_interrupted: "La conexión con el motor se cortó antes de terminar el documento.",
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
    public: "Pública, sin credenciales",
    publicOptional: "Pública; una clave opcional sube la cuota",
    optionalSaved: "Clave opcional guardada: cuota ampliada",
    lastVerified: "Última respuesta real: {when}",
    neverVerified: "Nunca verificada con una respuesta real",
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
