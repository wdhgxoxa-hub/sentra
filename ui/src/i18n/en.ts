import type { Dictionary } from "@/i18n/es";

/**
 * English dictionary.
 *
 * Typed against the Spanish one, so a key added there without a translation
 * here is a compile error rather than a stray Spanish string in the middle
 * of the English UI.
 */
export const en: Dictionary = {
  app: {
    name: "SENTRA",
    tagline: "Hear the market before you build",
  },

  error: {
    title: "This view could not be rendered",
    hint: "The failure stops here: the rest of the app keeps working. Switch section in the left menu, or try again.",
    details: "Show technical detail",
    retry: "Try again",
  },
  nav: {
    radar: "Live radar",
    search: "Semantic search",
    pipeline: "Pipeline control",
    settings: "Settings",
    opportunity: "Opportunity",
  },

  health: {
    checking: "checking…",
    database: "Database",
    engine: "Engine",
    up: "up",
    down: "not responding",
    noBackend: "no response from the backend",
    heuristicNli: "heuristic NLI",
    heuristicNliHint:
      "The classifier runs on rules, not a language model. Intent and severity labels are indicative only.",
    sourceStates: {
      demo: "Demo: fabricated data",
      reddit_sin_credenciales: "Reddit: credentials missing",
      reddit_sin_verificar: "Reddit: credentials saved, not verified",
      reddit_verificado: "Reddit: verified",
      reddit_error: "Reddit: error",
    },
    sourceUnknown: "Source: no information from the engine",
    sourceVerifiedAt: "last real access at {time}",
  },

  radar: {
    title: "Detected opportunities",
    subtitle: "Problems that repeat across several communities",
    empty: "No problem clears the bar yet.",
    emptyHint:
      "A pain must repeat across several communities to become an opportunity. Start a scan from Pipeline control.",
    loading: "Loading…",
    error: "Could not load the board.",
    feedEmpty: "No signal clears the cut yet. Start a scan from Pipeline.",
    feedError: "The signal feed could not be read.",
    feedTitle: "Recent activity",
    feedSubtitle: "Individual complaints, not yet consolidated",
    mentions: "mentions",
    communities: "communities",
    intensity: "Intensity",
    validate: "Review",
    points: "pts",
    filterAll: "All",
    filterPending: "Unreviewed",
  },

  detail: {
    selectPrompt: "Pick an opportunity from the radar to see its card.",
    loading: "Loading card…",
    gone: "That opportunity is no longer in the store.",
    job: "What people need",
    breakdown: "Where the score comes from",
    solutions: "Tools they already use",
    evolution: "How it evolved",
    noEvolution:
      "Only one reading so far. Evolution shows up once the same problem is detected in later scans.",
    validation: "Review",
    notes: "Analysis notes",
    notesPlaceholder: "What you'd build, for whom, and why now",
    saveNotes: "Save notes",
    decidedOn: "Decided on",
    noDecision: "No decision recorded yet",
    saveError: "Could not save",
    total: "Total",
  },

  search: {
    title: "Semantic search",
    subtitle: "Search by meaning, not just exact words. Compare both.",
    placeholder: "I can't export my invoices",
    error: "The search failed.",
    searching: "Searching…",
    empty: "No results for that query.",
    emptyHint: "Try one of the suggestions, or run a scan first.",
    suggestions: "Try",
    colText: "Text",
    colSemantic: "Meaning",
    colExact: "Exact",
    colCombined: "Combined",
    onlySemantic: "By meaning only",
    onlyExact: "By words only",
    both: "By both routes",
    examples: {
      billing: "Broken billing",
      migration: "Slow migration",
      support: "Repetitive support",
      pricing: "Confusing pricing",
    },
  },

  pdf: {
    export: "Export PDF",
    exporting: "Generating PDF…",
    withPlan: "It will include the architecture plan generated in this session.",
    withoutPlan: "No architecture plan in this session: the PDF will state it was not generated.",
    saved: "PDF saved to {path}",
    cancelled: "Export cancelled: no file was saved.",
    error: "The PDF could not be exported. Check that the engine is running and try again.",
  },
  topSix: {
    title: "Top {target} opportunities",
    titleGeneric: "Top opportunities",
    loading: "Loading the top opportunities…",
    error: "Could not read the result of the last run.",
    noRuns: "No run has finished yet. Start a scan from Pipeline.",
    complete: "Complete ({found}/{target})",
    partial: "Incomplete ({found}/{target})",
    incomplete: "Only {found} of {target} opportunities pass the cut.",
    open: "Open details",
    reasons: {
      fuentes_agotadas: "Everything available was reviewed and the remaining problems do not reach the minimum score.",
      limite_ciclos: "The scan hit its cycle limit with content still left to review.",
      sin_acceso_reddit: "The data source could not be read.",
      datos_insuficientes: "Not enough data: the source ran out before gathering that many distinct problems.",
    },
  },
  scanErrors: {
    reddit_credentials_missing: "Reddit credentials are missing. Save them in Settings.",
    reddit_auth_failed: "Reddit rejected the credentials. Check the Client ID and Client Secret.",
    reddit_forbidden: "Reddit denied access to this community.",
    reddit_not_found: "The community does not exist or is private.",
    reddit_rate_limited: "Reddit is rate limiting requests. Try again in {seconds} s.",
    reddit_rate_limited_unknown: "Reddit is rate limiting requests. Wait before retrying.",
    reddit_unavailable: "Reddit is not available right now.",
    fetch_failed: "The data source failed and the scan brought nothing back.",
    internal_error: "The engine failed during the scan.",
  },
  pipeline: {
    title: "Pipeline control",
    subtitle: "Start scans and watch the engine work",
    running: "Scans in progress",
    clearFinished: "Clear finished",
    cancel: "Cancel",
    cancelled: "Cancelled",
    watched: "Watched communities",
    addPlaceholder: "r/SaaS",
    tagsPlaceholder: "vertical, priority",
    tagsLabel: "Tags (comma separated)",
    order: "Sort",
    subreddit: "Community",
    watch: "Watch",
    saving: "Saving…",
    scan: "Scan",
    pause: "Pause",
    activate: "Activate",
    lastRun: "last run",
    never: "never",
    noSubreddits: "You are not watching any community yet. Add one above.",
    noRuns: "No runs yet.",
    subredditsError: "The list of communities could not be read.",
    runsError: "The run history could not be read.",
    saveFailed: "The community could not be saved.",
    scanFailed: "The scan could not be started.",
    cancelFailed: "The scan could not be cancelled.",
    history: "Recent runs",
    colSource: "Source",
    colStatus: "Status",
    colRead: "Read",
    colQualified: "Qualified",
    colErrors: "Errors",
    cycle: "cycle",
    read: "read",
    analysed: "analysed",
    stored: "stored",
    clusters: "problems",
    qualified: "qualified",
    discard: "dismiss",
    nodes: {
      fetch: "Fetch",
      filter: "Filter",
      intelligence: "Analysis",
      storage: "Storage",
      quality_gate: "Gate",
      aggregate: "Cluster",
    },
    nodeHints: {
      fetch: "Pulls posts from the chosen community.",
      filter: "Drops the noise: greetings, spam and covert promotion.",
      intelligence: "Reads each complaint and scores how much it hurts.",
      storage: "Saves everything so it can be searched later.",
      quality_gate: "Sets aside complaints that are too weak.",
      aggregate: "Groups complaints that describe the same problem.",
    },
  },

  settings: {
    title: "Settings",
    subtitle: "Credentials, language and data source",
    appearance: "Appearance",
    language: "Language",
    theme: "Theme",
    themeLight: "Light",
    themeDark: "Dark",
    themeSystem: "System",
    source: "Data source",
    sourceHint:
      "Demo mode uses a fixed set of fabricated posts. Everything else — analysis, clustering, search — works exactly the same.",
    modeSynthetic: "Demo",
    modeSyntheticDesc: "{count} fabricated posts, always the same ones",
    modeReddit: "Live Reddit",
    modeRedditDesc: "Requires Reddit API credentials",
    credentials: "Reddit credentials",
    credentialsHint:
      "Create them at reddit.com/prefs/apps choosing the «script» type. They are stored in the project's .env file, never in the database.",
    clientId: "Client ID",
    clientSecret: "Client Secret",
    userAgent: "User Agent",
    userAgentHint: "Reddit asks that it identify the application and its author.",
    username: "Username (optional)",
    password: "Password (optional)",
    userHint: "If filled in, the user-based flow is used, with a higher quota.",
    save: "Save credentials",
    saved: "Credentials saved",
    test: "Test connection",
    testing: "Testing…",
    configured: "Configured",
    notConfigured: "Not configured",
    loading: "Asking the engine…",
    unreachable:
      "Could not read the engine settings. Language and theme still work; the data source and credentials need the engine running.",
    aiEngine: "Architecture engine (Google Gemini)",
    aiHint:
      "The key comes from aistudio.google.com and is stored in the same .env as the Reddit ones. Without it, the architecture button on each opportunity stays disabled.",
    apiKey: "API key",
    showKey: "Show",
    hideKey: "Hide",
    model: "Model",
    modelHint:
      "Pro reasons deeper and takes longer; Flash answers sooner and is fine for a first pass.",
    modeFailed: "The data source could not be changed.",
    keySaved: "Key saved",
    probeFailed: "The key could not be tested.",
    saveKey: "Save key",
    testKey: "Test key",
    storedIn: "Stored in",
    secretNeverShown:
      "The secret is never shown once saved, not even to this window.",
  },

  architect: {
    open: "Generate architecture with Gemini",
    regenerate: "Generate again",
    close: "Hide architecture",
    generating: "The model is writing…",
    error: "The architecture could not be generated",
    copy: "Copy as Markdown",
    copied: "Copied to clipboard",
    copyFailed: "Could not copy",
    copyCode: "Copy block",
    empty:
      "Press it and Gemini drafts a two-phase build plan from this evidence: an MVP for 24-48 h and the full product for when it validates.",
    warning:
      "This is written by a generative model, not by the radar. Review the code and the schema before running them.",
    incomplete: "Incomplete document: it is not kept for the PDF.",
    missing: "Missing sections",
  },
  blueprint: {
    open: "View project specification (PRD)",
    close: "Hide specification",
    title: "Project specification",
    loading: "Writing the document…",
    error: "The specification could not be written",
    copy: "Copy document as Markdown",
    copied: "Copied to clipboard",
    copyFailed: "Could not copy",
    value: "Value proposition",
    summary: "Executive summary",
    problem: "The actual problem",
    solution: "The software to build",
    mvp: "MVP scope",
    fail: "Why current workarounds fail",
    money: "Business model",
    evidence: "What people say, in their own words",
    quotes: "distinct quotes",
    derived:
      "Derived from the stored evidence, with nothing made up: where there is no data, it says so.",
  },
  quotes: {
    title: "What they said",
    count: "quotes",
    translate: "Translate to English",
    showOriginal: "Show original",
    translating: "Translating…",
    error: "The quotes could not be translated",
    approximate: "Approximate translation: only the recognised parts were translated.",
    approximateShort: "approximate",
    offlineHint:
      "Without a Gemini key the offline engine translates, and it only knows common phrases.",
  },
  validation: {
    new: "Unreviewed",
    triaged: "Investigating",
    validated: "Validated",
    rejected: "Rejected",
    shipped: "Built",
  },

  urgency: {
    CRITICAL: "Critical",
    HIGH: "High",
    MEDIUM: "Medium",
    LOW: "Low",
  },

  intent: {
    ready_to_buy: "Ready to buy",
    seeking_recommendation: "Seeking recommendation",
    seeking_alternative: "Seeking alternative",
    comparing_products: "Comparing products",
    casual_discussion: "Casual discussion",
    undetermined: "Undetermined: not enough evidence",
    none: "No intent",
  },

  pain: {
    severe_blocker: "Severe blocker",
    time_consuming_friction: "Costly friction",
    minor_inconvenience: "Minor inconvenience",
    no_problem: "No problem",
    undetermined: "Undetermined: not enough evidence",
    none: "Unclassified",
  },

  explain: {
    jtbd: {
      title: "Jobs-To-Be-Done",
      body:
        "The task someone is trying to finish and can't. Instead of «wants an invoicing app», it says «needs to get paid without retyping data». Framing it as the task avoids rebuilding what already exists.",
    },
    spread: {
      title: "Spread",
      body:
        "How many distinct communities the problem shows up in. Ten complaints in one forum are one unhappy forum; one complaint in ten forums is a market pattern.",
    },
    frequency: {
      title: "Frequency",
      body:
        "How often it repeats within each community. Tells a recurring problem apart from something someone said once.",
    },
    severity: {
      title: "Severity",
      body:
        "How much it hurts. «Would be nice to have» is not the same as «this blocks my work». Inferred from the wording of each message.",
    },
    recency: {
      title: "Recency",
      body:
        "How recent the newest complaint is. It decays exponentially: a problem nobody has mentioned in a year was probably solved already.",
    },
    paidSignal: {
      title: "Willingness to pay",
      body:
        "Whether someone explicitly said they would pay, or mentioned what the problem costs them. That's the difference between an annoyance and a market.",
    },
    intensity: {
      title: "Intensity",
      body:
        "The weighted sum of the five factors, from 0 to 100. From 60 up it counts as an opportunity worth attention.",
    },
    rrf: {
      title: "Result fusion (RRF)",
      body:
        "Combines two searches: the one that understands meaning and the one that matches exact words. A result ranking high in both rises to the top; one found by only a single route stays below.",
    },
    semantic: {
      title: "Meaning-based search",
      body:
        "Finds similar texts even when they share no words. «Broken billing» finds «I can't export my receipts». It struggles with unusual proper nouns.",
    },
    exact: {
      title: "Word-based search (BM25)",
      body:
        "Matches the words as written, weighting rare ones higher. It's what rescues tool names like «pgpool» or «Stripe», where meaning doesn't help.",
    },
    cluster: {
      title: "Problem clustering",
      body:
        "Groups complaints about the same thing even across different forums. Without it every message would stand alone and no pattern would clear the bar.",
    },
    signalVsCluster: {
      title: "Complaints and opportunities",
      body:
        "A single complaint rarely justifies building anything. An opportunity is a problem that repeats across communities. That's why there are two lists and two different bars.",
    },
  },

  source: {
    demo: "Demo data",
    reddit: "Reddit data",
    unknown: "Unknown source",
  },

  errors: {
    unknown: "An unexpected error occurred.",
    database: "The database could not be read or written. Check that PostgreSQL is running.",
    database_unavailable: "No connection to PostgreSQL: the server did not answer or rejected the credentials.",
    sidecar: "The analysis engine answered with a failure.",
    sidecar_unreachable: "The analysis engine is not running. Restart the application.",
    sidecar_timeout: "The analysis engine took too long to answer.",
    invalid_input: "The data sent is not valid.",
    file: "The file could not be saved.",
    ui_crash: "This view failed to render.",
    persist_failed: "Harvest complete, but it could not be saved to the database.",
    gemini_not_configured: "No Gemini key is saved. Set it up in Settings.",
    gemini_error: "Gemini rejected the request. Check the key and the model in Settings.",
    gemini_unavailable: "Gemini is not available right now. It was retried several times; try again in a while.",
    gemini_rate_limited: "The Gemini quota ran out. Wait a little or check your key's plan.",
    gemini_timeout: "Gemini took too long to answer. Try gemini-2.5-flash if you do not need deep reasoning.",
    gemini_blocked: "Gemini blocked the answer with its safety filters.",
    gemini_empty: "Gemini finished without writing anything.",
    gemini_truncated: "The document was cut off at the model's length limit.",
    gemini_incomplete: "The document arrived without all the required sections.",
    internal_error: "Internal engine failure.",
    architect_protocol: "The engine returned an answer the app does not understand.",
    architect_interrupted: "The connection to the engine dropped before the document was finished.",
  },

  database: {
    title: "No database",
    hint: "Start PostgreSQL (or check RIR_PG_URL and pgpass.conf) and press Retry. Settings are still available in the menu.",
    retrying: "Connecting…",
  },

  common: {
    technicalDetails: "Technical details",
    close: "Close",
    retry: "Retry",
    loading: "Loading…",
    whatIsThis: "What this means",
  },
};
