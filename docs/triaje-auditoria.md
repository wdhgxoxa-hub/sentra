# Triaje AUD-032…AUD-071 (D6)

Los hallazgos de la auditoría forense original se revisaron contra el código
de la rama `feat/cierre-y-documentos`.

- **CERRADO**: arreglado en su causa, con test o guardia.
- **OBSOLETO**: el código afectado ya no existe; en esta misión se retiró
  todo lo que no tenía usuarios (C2, D-C7).
- **PENDIENTE DE E**: afecta a `core/intelligence/blueprint.py` y
  `core/documents/`, que la Fase E reutiliza o retira.

AUD-030 y AUD-031 (ALTOS) se cerraron en la misión anterior.

| AUD | Sev. | Hallazgo | Estado | Evidencia |
|---|---|---|---|---|
| 032 | MEDIO | `EvidenceQuote.signalId` inexistente | OBSOLETO | EvidenceQuotes y la agregación retiradas (daa91b6, 3459f75) |
| 033 | MEDIO | 9 campos fantasma en `RadarFeedEntry` | OBSOLETO | Feed y comando `get_radar_feed` retirados (daa91b6) |
| 034 | MEDIO | `urgencyTiers` enviado e ignorado | OBSOLETO | Tablero, feed y filtros de uiStore retirados (daa91b6) |
| 035 | MEDIO | JSON sin comprobar el estado HTTP | CERRADO | Un solo `engine::como_json` para todos los comandos; tests con servidor en loopback (e142628) |
| 036 | MEDIO | `.env` no atómico ni escapado | CERRADO | Atómico desde F2; control y claves rechazados, comillas preservadas, 400 con código (f3d79a7) |
| 037 | MEDIO | Validación débil y UA de relleno | CERRADO | Ajustes de Reddit retirados (daa91b6, D-C5); modelo validado al usarse (`llm_model_unavailable`); control de caracteres (f3d79a7) |
| 038 | MEDIO | Límites de tasa del cliente de Reddit | OBSOLETO | Cliente de ingesta retirado con las demos (e0b0be5, D-C7) |
| 039 | MEDIO | Enlace de evidencia externo | OBSOLETO | Grafo retirado (3459f75); el adaptador actual usa `permalink` (core/sources/reddit.py) |
| 040 | MEDIO | `classifier_engine` fijo | OBSOLETO | Escritura de señales retirada (3459f75) |
| 041 | MEDIO | Traducción sin conexión siempre en español | OBSOLETO | Traductor retirado (3459f75) |
| 042 | MEDIO | La salud oculta degradaciones | CERRADO | La salud ya no afirma NLI ni embedder (e84eb74); motor verde solo si dice ser SENTRA (63fba19); cada fuente, con su estado verificado en Fuentes |
| 043 | MEDIO | Reglas léxicas que fabrican señales | OBSOLETO | NLI y JTBD heurísticos retirados (e0b0be5, D-C7) |
| 044 | MEDIO | Sobrefusión de clusters | OBSOLETO | Agregación retirada (3459f75); la agrupación del juez está calibrada con pureza/ARI (11ec483) |
| 045 | MEDIO | Evidencia sin fecha ni enlace | CERRADO | Veredicto y feed con fecha y URL (a3521a4, b358845) |
| 046 | MEDIO | Duplicados en LanceDB y BM25 volátil | OBSOLETO | Escritura de señales y BM25 retirados (3459f75); `evidence_e5` hace upsert por id |
| 047 | MEDIO | Prompt con idiomas mezclados | OBSOLETO | Arquitecto retirado (3459f75) |
| 048 | MEDIO | Plan de arquitectura no persistido | OBSOLETO | ArchitectPanel retirado (daa91b6) |
| 049 | MEDIO | PRD con idioma mezclado | PENDIENTE DE E | JTBD retirado (e0b0be5); `blueprint.py` se decide en la Fase E |
| 050 | MEDIO | Documento no trazable | PENDIENTE DE E | Los documentos de la Fase E citan ids de evidencia, ejecución y fecha |
| 051 | MEDIO | Excepciones genéricas y tragadas | CERRADO | Quedan 5, todas en fronteras: re-lanzan tipado, registran o devuelven el motivo; el juez sin Gemini ya no calla (e140355) |
| 052 | MEDIO | Sin README, linters ni CI | CERRADO | README y guardia (39e724e); ruff/mypy/clippy configurados; sin CI por decisión (D-C8) |
| 053 | MEDIO | Textos sin i18n | OBSOLETO | PipelineControl y progressStore retirados (daa91b6); paridad es/en tipada |
| 054 | MEDIO | Búsqueda sin retardo de pulsación | CERRADO | 350 ms sin teclear antes de buscar (a3521a4) |
| 055 | MEDIO | Tarjeta sin cualificación ni fuente | OBSOLETO | OpportunityCard retirada (daa91b6); el veredicto enseña fuente y procedencia |
| 056 | MEDIO | `Unresponsive` definitivo | CERRADO | `retry_sidecar` y «Reintentar motor»; nunca dos motores (63fba19) |
| 057 | MEDIO | Tests que ocultan fallos | CERRADO | REACHABLE_CUT retirado con el grafo (3459f75); los tests de PostgreSQL corren en la compuerta (0 saltados); base de pruebas Rust compartida retirada (daa91b6) |
| 058 | BAJO | `trigger_source` fuera de la unión TS | OBSOLETO | Unión y escaneo antiguo retirados (e84eb74) |
| 059 | BAJO | Evento `radar:sidecar` sin oyente | CERRADO | La app lo escucha y relee la salud; tipado contra el enum de Rust (63fba19) |
| 060 | BAJO | Plugin shell sin uso | CERRADO | Retirado; guardia de dependencias de la UI (795352c) |
| 061 | BAJO | `/api/scan` sin consumidor | OBSOLETO | Rutas del escaneo antiguo retiradas (e84eb74) |
| 062 | BAJO | Máscaras amplias | CERRADO | Solo los 4 últimos de la clave de Gemini (7411f55) |
| 063 | BAJO | `half_life_days` mal nombrado | OBSOLETO | Puntuación temporal retirada (e0b0be5) |
| 064 | BAJO | Ruta fija y `prompts.toml` sin uso | OBSOLETO | Motor NLI y `config/prompts.toml` retirados (e0b0be5); rutas de los scripts relativas (c5ebd7a) |
| 065 | BAJO | Mensajes técnicos al usuario | CERRADO | Sin comandos de terminal en la salud (63fba19); los rechazos del motor llegan con código |
| 066 | BAJO | Restos del renombrado | CERRADO | Todo a SENTRA, identificador incluido; excepciones documentadas (fd36387, D-C6) |
| 067 | BAJO | Duplicación | CERRADO | Duplicados retirados en C2; tenant local vigilado en los tres sitios (70c3eb9) |
| 068 | BAJO | Código muerto | CERRADO | Filtros, tipos y cliente retirados (daa91b6, e84eb74, e0b0be5); guardias de superficie IPC y dependencias |
| 069 | BAJO | Referencia a `schema.sql` inexistente | CERRADO | Comentario y documentación corregidos, con guardia (70c3eb9) |
| 070 | BAJO | Cualquier `/api/health` se acepta | CERRADO | Se exige `service` = sentra-sidecar; guardia Python/Rust (63fba19) |
| 071 | BAJO | `run:finished.clusters` engañoso | OBSOLETO | Eventos del escaneo antiguo retirados (e84eb74) |

Recuento: 19 CERRADO, 19 OBSOLETO, 2 PENDIENTE DE E (se resuelven en la Fase E), 0 ABIERTO.
