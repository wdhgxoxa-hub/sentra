# Auditoría integral de SENTRA — 2026-09-24

Auditor externo (PARTE 1, solo lectura). Rama `feat/cierre-y-documentos`, HEAD `b185ee8`,
release `target/release/sentra.exe` compilada desde ese HEAD a las 00:01 (la del acceso
`SENTRA.lnk`). Sin cambios de código, commits ni migraciones; base en solo lectura; cero
llamadas a Gemini y cero escaneos. Todo el material de prueba está en el scratchpad de la
sesión (`auditoria/`): fotogramas, capturas del arnés, informes JSON y consultas SQL.

**VERIFICADO** = reproducido sobre el ejecutable real, la base o el código.
**SOSPECHA** = inferido sin reproducir.

---

## 1. Resumen ejecutivo

1. La aplicación **funciona** como software: arranca en ~4 s, las cuatro vistas cargan sus datos, cada cifra visible cuadra con la base, sobrevive 10 min de uso sin errores y sin huérfanos, y degrada con mensaje claro sin base de datos o sin clave.
2. El **producto no cumple su promesa**: los 9 veredictos reales no describen problemas. Los grupos mezclan lanzamientos de productos ajenos («Show HN: …») sin relación entre sí, y el etiquetador cuenta esos lanzamientos como «parches caseros». Decidir qué construir con esto no es posible (AUD2-001, CRÍTICO).
3. «0 de 6 para construir» es honesto con los datos, pero sería casi inalcanzable aunque los grupos fueran buenos: G2 pide 8 autores en grupos de 3 a 14 piezas.
4. El 45 % de «Evidencia reciente» (18 de 40) son **fixtures de demostración** del 21/09 fechadas el 31/12/2099, con URLs inventadas `t3_demo*`. También salen en la búsqueda (AUD2-002).
5. La release **no es un producto instalable**: arranca el motor, lee el `.env` y el modelo desde la carpeta del repo y la rama del momento. Así nació la pantalla negra, y no se puede llevar a otra máquina (AUD2-003).
6. Ningún test abre el ejecutable. Por eso 660 tests en verde no vieron la pantalla negra ni las vistas vacías (AUD2-004).
7. Varios textos engañan: la «N» literal, «(Fase 4)», la jerga «la misión… (R7)» en pantalla, G7 en verde sin evidencia y ejemplos de búsqueda de facturas sobre un corpus de notificaciones.
8. Seguridad y privacidad aguantan: CSP mínima, token en tiempo constante, solo loopback, 0 secretos en 13 logs, R9 cumplido en todas las tablas y npm sin vulnerabilidades.
9. Proceso: 2 commits entraron con la compuerta en rojo, las ramas anteriores apenas dejan prueba de RED, y en esta sesión hubo 2 declaraciones de «arreglado» sin prueba real, más 2 fallos de mi arnés.
10. Veredicto del auditor: **no está listo para E8, F ni G**. Primero hay que arreglar el juez y la procedencia de la release; lo demás es deuda acotada.

## 2. Notas D01–D14

| Dim | Nota | Justificación (evidencia en §4) |
|---|---|---|
| D01 Experiencia de producto | 5 | Flujo navegable y es/en completo; pero Fuentes repite el Top entero (7 846 px), hay textos falsos o internos (AUD2-007), G7 aparece verde sin datos, los ejemplos de búsqueda no aplican y el error sin base sale dos veces. El teclado recorre la navegación con foco visible. |
| D02 Corrección de extremo a extremo | 6 | Top 6 + 3, feed 40, búsqueda 20 y estados de fuentes cuadran con SQL; pero se enseñan fixtures como evidencia y la búsqueda no tiene umbral de relevancia. |
| D03 Arquitectura | 4 | Interfaz y motor atados a la carpeta del repo, sin identidad de versión; dos variables para el mismo DSN; el esquema legacy sigue vivo. Límites de módulos y contratos Rust↔TS↔Py bien vigilados por tests. |
| D04 Validez del juez | 2 | Grupos incoherentes, lanzamientos contados como parches, palabras clave basura, G7 aprobado por ausencia, umbral G2 fuera de escala para ~100 piezas. |
| D05 Integridad y privacidad | 6 | R9: 100 % hash en las 4 tablas con autor y payload limpio; «@…» en textos = decoradores de código (verificado). Fixtures de 2099 con `data_source NULL`; 9 tablas o vistas legacy sin uso. |
| D06 Seguridad | 8 | Capacidades mínimas, CSP ajustada, token en tiempo constante, bind 127.0.0.1, 0 secretos en logs, `npm audit` 0. Python y Rust sin auditar (no hay herramienta instalada). |
| D07 Fiabilidad | 7 | Arranque, cierre normal y forzado, base caída y sin clave bien; log de 32 KB a nivel TRACE que pierde la historia en minutos; e5 en %TEMP%; fuente en error contada como activa. |
| D08 Rendimiento | 7 | Motor activo 4,2 s; datos 4,6 s; búsqueda densa 33–53 ms; carga e5 1,9 s en caliente; bundle 328 kB; 2,4 GB en uso (motor 1,7 GB). Juez con 300 ítems sin medir. |
| D09 Calidad de tests | 4 | 81 ficheros: 31 con dobles, 32 guardas que leen código como texto, 9 con PostgreSQL real, **0 que abran el exe o la UI**, 1 test TS. |
| D10 Proceso | 5 | 2 commits con la compuerta en rojo; TDD demostrable solo en 3/40 y 3/60 commits de ramas anteriores; ≥4 incidentes de heredoc; en esta sesión, 2 «arreglado» sin prueba real y 2 fallos de arnés. |
| D11 Construcción y release | 3 | Compilada desde rama de trabajo; dependiente del repo; versión 0.1.0 en todo; aviso del enlazador; carpeta de datos antigua huérfana; eventos de 6 instalaciones MSI pero ningún SENTRA instalado. |
| D12 Documentación | 4 | README correcto y vigilado; `SPECIFICATION.md` y `PLAN.md` describen otro proyecto; `docs/ARQUITECTURA…` dice que no hay UI y vectores de 384; `tasks/SPEC-blueprint.md` retirado; 1,6 GB de `repos/` ajenos. |
| D13 Costes y cuotas | 7 | Etiquetado ⌈n/20⌉ llamadas por escaneo (máx. 15), abogado solo en CONSTRUIR, documentos de 1 a 3 llamadas; `models.list` invisible al abrir Configuración (25 veces en 10 arranques, sin tokens). |
| D14 Cumplimiento | 6 | Insignia, sitio y URL en toda evidencia; marcas «solo uso personal»; Reddit y X bloqueadas. Stack Exchange (CC BY-SA) sin autor ni licencia visible, en tensión con R9. |

## 3. Línea de tiempo de la grabación

`C:\Users\david\Desktop\123456.mp4` (24/09 00:50, 78,5 s, 3838×2384, audio en silencio
total: −91 dB, sin voz). Fotogramas: 39 cada 2 s y 99 de cambio de escena (umbral 0,04 sobre 1600 px).

| t | Qué hace el usuario | Qué muestra la app | Qué esperaría un usuario | Anomalía → hallazgo |
|---|---|---|---|---|
| 0 s | Radar abierto | Top 6: «Investigar más · email · notifications · built», motor y base en verde, «7 de 10 fuentes activas» | Nichos con nombre de problema | Nombres con «built», «com», «don» → AUD2-006 · «Al menos N autores» → AUD2-007 · G7 y G8 en verde con «0 evidencias» → AUD2-005 |
| 0–6 s | Baja por las tarjetas | «Viabilidad… sin determinar (Fase 4)», «Tendencia: -1 (0 %)», «1 evidencias» | Textos finales | AUD2-007 |
| 8 s | Llega a «Evidencia reciente» | «legacy · r/smallbusiness · 31/12/2099 · Fuente desconocida», «Manual invoice export is broken» ×6 | Evidencia real reciente | Fixtures de 2099 arriba del feed → AUD2-002 |
| 10 s | Final del feed | Evidencia real de HN, Stack Exchange y Discourse con atribución | — | Correcto |
| 14–24 s | Vuelve al Top y lo recorre | Grupos «email · app · don», «email · job · send»… | — | AUD2-006 |
| 30–34 s | Abre «Evidencia (3)» de «email · app · don» | Tres comentarios de HN sin relación (modelos de IA, Bitwarden, leer el periódico) | Tres quejas del mismo problema | Grupo incoherente → AUD2-001 |
| 38 s | Pasa el cursor por «Markdown» (dossier) | Ningún «Generando…» | — | No se observa clic: no es hallazgo |
| 42–48 s | Abre Búsqueda | Ejemplos «Facturación rota», «Migración lenta»… | Ejemplos del corpus real | AUD2-007 (la búsqueda en sí funciona: ver AUD2-009) |
| 48–52 s | Abre Fuentes | Tarjetas; Reddit: «Pendiente de aprobación: la misión no permite llamadas reales a Reddit (R7)»; Product Hunt «Error» + «Revísalas en la sección Fuentes»; Discourse «Sin configurar» con «Última respuesta real» | Estado claro | AUD2-007, AUD2-023 |
| 54–66 s | Sigue en Fuentes | El Top 6 del juez entero otra vez | Solo fuentes y escaneo | AUD2-008 |
| 66–78 s | Abre Configuración y enfoca el idioma | «Configuradas · …ge2g», modelos automáticos gemini-3.1-pro-preview / gemini-3.8-flash; subtítulo «…y fuente de datos» | — | AUD2-007 |

Todas las anomalías de la tabla están reproducidas con el arnés CDP sobre el exe real
(`escenario_frio/informe.json`: `feed_fechas_futuras: 18`, `texto_N: true`, `fase4: true`,
`jerga_interna: true`, `veredictos_repetidos_aqui: 6`).

## 4. Hallazgos

Formato: severidad · dimensión · estado · evidencia · impacto · causa raíz · corrección · esfuerzo · ¿decisión?

### AUD2-001 · CRÍTICO · D04 · VERIFICADO — Los grupos del juez no son problemas y el etiquetador confunde lanzamientos con parches
- **Evidencia.**
  - SQL de miembros por veredicto (`sql_resultados2.json`, «grupos»):
    - «email-notifications-built» = 8 «Show HN» de productos sin relación (AI Slop journal, iKrypt, Bucket, Selva, AgentMailr, Dinopass…);
    - «email-notifications-com» = career pages, backends de formularios, analítica de hedge funds;
    - «email-app-don» = comentarios de HN sobre modelos de IA, Bitwarden y el periódico (grabación, 34 s).
  - G3 «parche casero» = 6 en el grupo de lanzamientos.
  - `compuerta_falla_frecuencia`: G2 falla 7/9 con umbral 8 (`gates.py:49`) en grupos de 3 a 14 piezas.
- **Impacto.** Los veredictos no sirven para decidir. «0 CONSTRUIR» es correcto por casualidad, no por criterio.
- **Causa raíz.**
  1. `quality.py` filtra spam y bots, pero no la pertinencia: un lanzamiento propio no es una queja.
  2. La agrupación no exige coherencia mínima dentro del grupo.
  3. El prompt del etiquetador no distingue «construí X» de «me apaño con X».
  4. G2 usa un umbral fijo que no escala con el tamaño del escaneo.
- **Corrección.**
  - Pertinencia por ítem (la etiqueta existente + regla dura para «Show HN/Launch/I built» sin queja).
  - Umbral de coherencia por grupo (similitud media e5 intragrupo; debajo del umbral, «grupo no coherente» y fuera del Top).
  - Ejemplos negativos en el prompt, y G2 relativo al tamaño con mínimo absoluto.
  - Verificación con fixtures inventadas (R8) y re-juicio real con presupuesto aprobado.
- **Esfuerzo.** L.
- **Decisión:** sí (DP2).

### AUD2-002 · ALTO · D02/D05 · VERIFICADO — Fixtures de demostración de 2099 presentadas como evidencia
- **Evidencia.**
  - `legacy_resumen`: 18 filas `source=legacy`, `data_source NULL`, todas del 2099-12-31, 6 con URL `…/comments/t3_*` y 12 sin URL.
  - IDs `legacy:t3_demo0…4` con el mismo título ×6; vienen de 21 `raw_posts` de ejecuciones «graph» y «sidecar» del 21/09 copiadas por la migración 009.
  - Arnés: 18 de 40 del feed (`feed_fechas_futuras: 18`); la búsqueda «invoice export» devuelve `legacy:t3_inv04` y `legacy:t3_1` (`busqueda_directa.py`).
  - Los tests usan bases desechables (`tests/_postgres.py`): no vienen de la suite.
- **Impacto.** Datos inventados arriba del feed «real» y en la búsqueda: la interfaz miente sobre la procedencia.
- **Causa raíz.** La 009 mapeó `data_source NULL` a `legacy` sin marcar `demo`, y ninguna vista filtra `legacy`.
- **Corrección.** Migración 012 con respaldo (borrar o marcar como `demo`, DP3), más una guarda de que el feed y la búsqueda solo muestran `real` salvo que se pida demo.
- **Esfuerzo.** S.
- **Decisión:** sí (DP3).

### AUD2-003 · ALTO · D03/D11 · VERIFICADO — La release depende de la carpeta y la rama del repo, sin identidad de versión
- **Evidencia.**
  - `sidecar.rs`: `RIR_PROJECT_DIR`/proyecto → `.venv` y `-m core…` desde el repo.
  - `envfile.py:49`: `.env` de la raíz del repo.
  - Versión 0.1.0 en `Cargo.toml`, `tauri.conf.json` y `package.json`.
  - La pantalla negra del 23/09: exe de `main` + motor de la rama.
  - Escenario `sin_clave`: basta cambiar `RIR_PROJECT_DIR` para que el exe corra otro código.
- **Impacto.** Cambiar de rama cambia el producto instalado; no se puede instalar en otra máquina.
- **Causa raíz.** Diseño de desarrollo usado como distribución.
- **Corrección.** DP1: motor fijado a la versión (copia del motor en los recursos de la release, o carpeta versionada) y huella de compilación que interfaz y motor comparan al arrancar (si no coinciden: aviso con código, no pantalla negra).
- **Esfuerzo.** M–L.
- **Decisión:** sí (DP1).

### AUD2-004 · ALTO · D09 · VERIFICADO — Ningún test ejecuta la aplicación real
- **Evidencia.** 0 de 81 ficheros abren el exe o la UI; 1 test TS; los fallos del 23/09 (pantalla negra, vistas vacías, motor huérfano) solo se vieron con el arnés CDP.
- **Impacto.** La compuerta en verde no dice nada de la experiencia real.
- **Causa raíz.** Faltaba una prueba de extremo a extremo.
- **Corrección.** Prueba de humo en el repo, obligatoria en la misión: arranque en frío, datos por vista contra SQL, cierre forzado sin huérfanos. Si tarda más de ~60 s, paso explícito previo a toda release, documentado en el README.
- **Esfuerzo.** M.
- **Decisión:** no.

### AUD2-005 · ALTO · D04/D01 · VERIFICADO — G7 aprobado por ausencia se pinta como verificado
- **Evidencia.** `compuertas_pasan_sin_evidencia`: G7 9/9 y G8 9/9 con 0 evidencias; `gates.py:101-115` devuelve `passed=True` si nadie menciona un competidor gratuito; grabación a 0 s: ✓ verde «0 · umbral 0.50 · 0 evidencias».
- **Impacto.** Un ✓ que no midió nada, contra la regla «lo no verificable se marca».
- **Causa raíz.** `GateResult` no distingue «pasa» de «sin datos». G8 sí es legítimo: mide que no hay datos no reales.
- **Corrección.** Estado `sin_datos` para G7 (neutral y explicado en la UI), con tests.
- **Esfuerzo.** S.
- **Decisión:** no.

### AUD2-006 · MEDIO · D04/D01 · VERIFICADO — Palabras clave basura en el nombre de los nichos
- **Evidencia.**
  - `veredictos_run`: «built, time, where», «com, free, https», «want, approach», «app, don».
  - `STOPWORDS` (126, `clustering.py:43`) no contiene where/after/actually/don/com/https (comprobado uno a uno).
  - Nombres casi duplicados («email · notifications · built/com/after/actually»).
- **Causa raíz.** Lista incompleta; el tokenizador parte «don't» en «don»; las URL no se limpian antes de contar.
- **Corrección.** Quitar URLs antes de tokenizar, ampliar la lista (función inglesa + española + fragmentos web), descartar términos de < 3 letras y el término de la consulta, y guarda con casos reales.
- **Esfuerzo.** S.
- **Decisión:** no.

### AUD2-007 · MEDIO · D01 · VERIFICADO — Textos falsos, internos o sin terminar en pantalla
- **Evidencia.**
  - `es.ts:308` «Al menos N autores distintos» y `gates.py:150` «G2 por debajo de N/2»;
  - `es.ts:330` «sin determinar (Fase 4)»;
  - `reddit.py:59` y `x.py:49` «la misión… (R7)»;
  - `es.ts:65/78` ejemplos de facturas sobre un corpus de notificaciones;
  - `es.ts:89` «…y fuente de datos»;
  - `es.ts:167` «Revísalas en la sección Fuentes» mostrado dentro de Fuentes;
  - `es.ts:97` «Configuradas» (una clave);
  - `es.ts:317` «1 evidencias»;
  - «Tendencia: -1 (0 %)».
  - Arnés: `texto_N: true`, `fase4: true`, `jerga_interna: true`.
- **Corrección.** Interpolar N real, eliminar «Fase 4», mensajes de producto en lugar de reglas de la misión, ejemplos del corpus o genéricos, plurales, y una guarda (ampliar `test_textos_vigentes`).
- **Esfuerzo.** S–M.
- **Decisión:** no.

### AUD2-008 · MEDIO · D01 · VERIFICADO — Fuentes repite el Top entero del juez
- **Evidencia.** `JudgePanel` en `SourcesView`; arnés: `veredictos_repetidos_aqui: 6`, página de 7 846 px; grabación a 54–66 s.
- **Corrección.** El Top vive solo en Radar; Fuentes muestra el escaneo y un resumen del juez con enlace.
- **Esfuerzo.** S.
- **Decisión:** sí (DP6).

### AUD2-009 · MEDIO · D02 · VERIFICADO — La búsqueda no tiene umbral de relevancia
- **Evidencia.** `busqueda_directa.py`: «zzzz qqqq» → 20 resultados (distancia 0,41 frente a 0,30 de una consulta real); «Facturación rota» → 1 léxico y 19 densos irrelevantes.
- **Nota del auditor.** La sospecha inicial de «misma lista para todas las consultas» fue un **falso positivo de mi arnés** (esperaba filas ya presentes); corregido y descartado.
- **Corrección.** Distancia máxima densa calibrada con consultas de control, más un estado «sin resultados relevantes».
- **Esfuerzo.** S.
- **Decisión:** no.

### AUD2-010 · MEDIO · D07/D08 · VERIFICADO (ubicación) / SOSPECHA (impacto) — El modelo e5 (2,1 GB) vive en %TEMP%
- **Evidencia.** `%TEMP%\fastembed_cache\models--qdrant--multilingual-e5-large-onnx` = 2,1 GB (du).
- **Impacto.** Una limpieza de temporales deja sin búsqueda ni juez, o fuerza una descarga de 2,1 GB (no reproducido).
- **Corrección.** Caché del modelo en una carpeta persistente de la app, con comprobación al arrancar.
- **Esfuerzo.** S.
- **Decisión:** sí (DP9: mover 2,1 GB).

### AUD2-011 · MEDIO · D03 · VERIFICADO — Dos variables para el mismo DSN
- **Evidencia.** `db.rs:17` `RIR_PG_URL`, `postgres_store.py:60` `RIR_PG_DSN`; el aviso sin base solo nombra `RIR_PG_URL` (escenario `bd_caida`).
- **Corrección.** Una variable canónica, aceptando la otra con aviso durante una versión; guarda Rust == Python.
- **Esfuerzo.** S.
- **Decisión:** no.

### AUD2-012 · MEDIO · D07 · VERIFICADO — Una fuente en error cuenta como activa
- **Evidencia.** `registry.py:224` (`active` excluye solo `no_configurada` y `deshabilitada`); «7 de 10 fuentes activas» incluye Product Hunt en `error/source_auth_failed`.
- **Impacto.** Cada escaneo gasta una llamada que va a fallar, y el recuento engaña.
- **Corrección.** Recuento «activas y sanas» y política de escaneo para fuentes en error de credenciales (DP10).
- **Esfuerzo.** S.
- **Decisión:** sí (DP10).

### AUD2-013 · MEDIO · D07 · VERIFICADO — El log de la app pierde la historia en minutos
- **Evidencia.** `SENTRA.log` de 32 KB con hyper y reqwest a nivel TRACE; en el incidente del 23/09 el log empezaba a las 04:08:28 (solo el último minuto).
- **Corrección.** Nivel INFO en release (TRACE bajo variable), rotación por tamaño razonable con varias copias.
- **Esfuerzo.** S.
- **Decisión:** no.

### AUD2-014 · BAJO · D11 · VERIFICADO — Aviso del enlazador en `tauri build`
- **Evidencia.** `build_release2.log:26-28` «Creando biblioteca … sentra_lib.dll.lib» + `#[warn(linker_messages)]`.
- **Causa raíz.** `crate-type = ["staticlib","cdylib","rlib"]` (`Cargo.toml:10`), herencia de la plantilla móvil.
- **Corrección.** Solo `rlib` (la app es de escritorio), con build limpia como prueba.
- **Esfuerzo.** XS.
- **Decisión:** no.

### AUD2-015 · BAJO · D11 · VERIFICADO — Carpeta de datos antigua huérfana
- **Evidencia.** `%LOCALAPPDATA%\com.reddit-intelligence-radar.desktop` 75 MB (EBWebView + logs) tras el renombrado; las preferencias se reiniciaron.
- **Corrección.** Migrar las preferencias una vez y retirar la carpeta, o documentarla (DP8).
- **Esfuerzo.** S.

### AUD2-016 · BAJO · D05/D03 · VERIFICADO — Esquema legacy sin uso
- **Evidencia.** 0 referencias en código a raw_posts, raw_comments, jtbd_opportunities, opportunity_clusters, opportunity_cluster_signals, cluster_validations, v_radar_feed, v_opportunity_board y v_subreddit_health.
- **Corrección.** Migración con respaldo que las retire (DP4).
- **Esfuerzo.** S.

### AUD2-017 · BAJO · D12 · VERIFICADO — Documentación de otro proyecto y restos
- **Evidencia.**
  - `SPECIFICATION.md`/`PLAN.md` (biblioteca de repos clonados);
  - `docs/ARQUITECTURA_POSTGRES_Y_FRONTEND.md` («no hay código de UI», LanceDB de 384);
  - `tasks/SPEC-blueprint.md`;
  - `repos/` 1,6 GB (57 clones, ignorado por git).
- **Corrección.** Mover a `docs/historico/` con una nota, o retirar; decidir sobre `repos/` (DP11).
- **Esfuerzo.** S.

### AUD2-018 · MEDIO · D14 · SOSPECHA (interpretación legal) — Stack Exchange sin autor ni licencia
- **Evidencia.** `attribution.py`: insignia + sitio + URL; los autores son hash (R9); ninguna vista ni documento dice «CC BY-SA».
- **Impacto.** Los extractos citados (y exportados en el dossier) pueden no cumplir la atribución de CC BY-SA.
- **Corrección.** Opciones en DP5.
- **Esfuerzo.** S.

### AUD2-019 · BAJO · D13 · VERIFICADO — Llamada invisible a Google al abrir Configuración
- **Evidencia.** `sidecar.log`: 25 `GET /api/gemini/models` en 10 arranques; `gemini.py:404` `models.list`; caché de 10 min (`context.py:34`).
- **Impacto.** Sin coste en tokens, pero es una salida a la red con la clave que el usuario no ve.
- **Corrección.** Decirlo en la UI («lista pedida a Google hace X min») y no repetirla al abrir la vista si hay caché persistente.
- **Esfuerzo.** XS.

### AUD2-020 · BAJO · D01 · VERIFICADO — El aviso «Sin base de datos» sale dos veces
- **Evidencia.** Escenario `bd_caida`, Radar: dos `role=alert` con el mismo texto.
- **Esfuerzo.** XS.

### AUD2-021 · BAJO · D06 · VERIFICADO — Dependencias Python y Rust sin auditar
- **Evidencia.** `pip_audit`: módulo no instalado; `cargo audit`: comando inexistente; `npm audit` 0.
- **Corrección.** Instalar pip-audit y cargo-audit como herramientas de desarrollo (DP7) y sumarlas a la compuerta.

### AUD2-022 · MEDIO · D10 · VERIFICADO — Desviaciones de proceso
- **Commits con la compuerta en rojo:** 3f97120 (mypy) y 1e21a58 (ruff, mío en esta misión), arreglados en dcde19b y bf2eb9c.
- **Prueba de TDD en el mensaje:** 3/40 (fix/altos), 3/60 (feat/multifuente) y 36/50 (esta rama).
- **Tests escritos después:** 39e724e (README, admitido en su mensaje).
- **«Arreglado» sin prueba real (mío, 23/09):**
  - 23:20: di por verificada la pantalla negra comprobando solo que el DOM no estaba vacío, contra un motor huérfano;
  - el test Rust de vigilancia usó el puerto de otro test (lo cazó la suite).
- **Fallos del arnés en esta auditoría (míos):**
  - el falso positivo de búsqueda (AUD2-009);
  - dejé el tema del usuario en «Oscuro» al restaurar por texto tras cambiar el idioma (restaurado y verificado: `es`, Automático).
- **Heredoc:** ≥4 corrupciones de barras (anotado en memoria; 3 en esta sesión).
- **Salvaguardas propuestas:**
  - la prueba de humo (AUD2-004);
  - `commit_si_verde.sh` dentro del repo como hook de pre-commit;
  - regla «VERIFICADO solo con datos contra SQL»;
  - el arnés restaura las preferencias por estado, no por texto, y nunca escribe en el perfil real (perfil de WebView aparte);
  - ediciones solo con Edit o Write, nunca con heredoc.

### AUD2-023 · BAJO · D01 · VERIFICADO — Discourse: «Sin configurar» junto a «Última respuesta real» y «Escaneo: 2 ítems»
- **Causa.** Precedencia correcta (faltan foros guardados), pero la tarjeta no explica que la verificación vino de foros pasados en un escaneo.
- **Corrección.** Texto que lo diga.
- **Esfuerzo.** XS.

### AUD2-024 · BAJO · D01 · VERIFICADO — «Guardar modelos» activo sin clave ni modelos
- **Evidencia.** Captura `escenario_sin_clave/04_configuracion.png`.
- **Esfuerzo.** XS.

### AUD2-025 · BAJO · D07 · SOSPECHA — Un escaneo de más de 600 s se corta en la interfaz
- **Evidencia.** `SCAN_TIMEOUT` 600 s en Rust frente a 20 s por petición en el motor; sin reproducir (necesitaría un escaneo real).

### AUD2-026 · BAJO · D08 · SOSPECHA — WebView2 crece un 26 % en 10 min
- **Evidencia.** `escenario_prolongado`: 506 → 636 MB con el heap JS estable en 5 MB y 1 673 nodos. Vigilar en la prueba de humo larga.

## 5. Plan de cierre (por dependencias) y decisiones

**Orden propuesto.**
1. AUD2-004: arnés al repo; primero, porque es la prueba de antes y después de todo lo demás.
2. AUD2-003: huella de versión + motor fijado.
3. AUD2-002 y AUD2-016: migración 012 con respaldo.
4. AUD2-001, 005 y 006: juez, verificado con fixtures y, si lo apruebas, re-juicio real.
5. AUD2-007, 008, 009, 012, 020, 023 y 024: interfaz.
6. AUD2-011, 013, 014, 010 y 015: fiabilidad y build.
7. AUD2-017, 018, 019 y 021: documentos, cumplimiento y auditoría de dependencias.
8. AUD2-022: salvaguardas de proceso (hook y reglas).
9. Release, humo en verde, informe actualizado y push.

**Decisiones pendientes.**
- **DP1 · Motor de la release (AUD2-003).**
  - (A) Copiar el motor Python y su `.venv` a los recursos de la release.
  - (B) Copiar solo el código del motor a una carpeta versionada fuera del repo, con huella de compilación que ambos comparan; el `.venv` y el modelo siguen compartidos.
  - (C) Solo la huella: detecta el desfase y lo dice, sin fijar nada.
  - **Recomendación: B** (sin dependencias nuevas y con desfase imposible).
- **DP2 · Juez (AUD2-001).**
  - (A) Pertinencia + coherencia + prompt + G2 relativo, verificado con fixtures, y re-juicio real con hasta 15 llamadas a Gemini.
  - (B) Lo mismo sin re-juicio: los veredictos actuales se marcan «de un juez anterior».
  - (C) No tocar y rotular los veredictos como experimentales.
  - **Recomendación: A.**
- **DP3 · Fixtures legacy (AUD2-002).**
  - (A) Borrarlas con respaldo.
  - (B) Marcarlas `demo`.
  - (C) Solo ocultar `legacy`.
  - **Recomendación: A.**
- **DP4 · Esquema legacy (AUD2-016).** (A) Retirarlo con respaldo. (B) Conservarlo. **Recomendación: A.**
- **DP5 · Atribución de Stack Exchange (AUD2-018).**
  - (A) Añadir licencia CC BY-SA 4.0 y enlace al original (el autor se ve siguiendo el enlace), manteniendo R9.
  - (B) Guardar y mostrar el nombre público del autor solo para Stack Exchange (excepción a R9).
  - (C) Dejarlo.
  - **Recomendación: A.**
- **DP6 · Dónde viven los veredictos (AUD2-008).**
  - (A) Solo en Radar; Fuentes muestra un resumen.
  - (B) Solo en Fuentes.
  - (C) En los dos.
  - **Recomendación: A.**
- **DP7 · Herramientas de auditoría (AUD2-021).** (A) Instalar pip-audit y cargo-audit como herramientas de desarrollo. (B) No. **Recomendación: A.**
- **DP8 · Carpeta antigua (AUD2-015).** (A) Migrar preferencias y borrarla. (B) Dejarla y documentarla. **Recomendación: A**, borrando solo tras tu confirmación.
- **DP9 · Caché del modelo (AUD2-010).** (A) Mover a `%LOCALAPPDATA%\SENTRA\models` (copia de 2,1 GB). (B) Dejarla. **Recomendación: A.**
- **DP10 · Fuente en error (AUD2-012).** (A) No se escanea hasta volver a probarla con éxito. (B) Se escanea igual y se cuenta aparte. **Recomendación: A.**
- **DP11 · `repos/` y documentos antiguos (AUD2-017).** (A) Sacar `repos/` del proyecto (a otra carpeta que elijas) y archivar los documentos. (B) Dejarlos. **Recomendación: A.**

## 6. Qué no se pudo auditar y por qué

- **Juez con 300 ítems (D08) y re-juicio.** Necesita Gemini o escribir en la base (R3 y R4).
- **Generación de dossier y plan de extremo a extremo.** Gasta Gemini (E8); solo se auditó el código y que el botón del plan exige forzar.
- **Escaneo real y lentitud de una fuente (D07).** R3; solo timeouts por código.
- **Dependencias Python y Rust (D06).** pip-audit y cargo-audit no están instalados.
- **Instalación en otra máquina (D11).** No hay segunda máquina; el análisis es estático.
- **Contraste WCAG (D01).** No hay herramienta de medición instalada; se revisó foco y teclado.
- **Historial de compuerta de cada commit anterior (D10).** No se re-ejecutó commit a commit; se usaron los mensajes y la memoria verificada contra git.
- **Transcripción.** El audio es silencio total.

---

## 7. Estado tras la PARTE 2 (cierre de la deuda)

Rama `feat/cierre-y-documentos`, commits `ef1522b`…`95a578b` (código) y el commit de este informe. Decisiones del
usuario: DP1 B, DP2–DP11 A. Cada commit pasó la compuerta; desde `0ac08f6` la
exige el hook de pre-commit del repositorio. La evidencia de antes y después
sobre la app real está en el scratchpad de la sesión (`evidencia/`: capturas
CDP, JSON y consultas de solo lectura).

**Compuerta de release** (`CLIPPY=1 AUDIT=1 HUMO=1 bash scripts/compuerta.sh`, release compilada con `npm run tauri build` desde el código de `95a578b`, SENTRA cerrada): ruff, mypy, Python (731 tests), tsc, node (9), cargo (81), clippy, pip-audit, cargo-audit y humo en OK; `COMPUERTA OK`, código de salida 0.

### 7.1 Hallazgos

| Hallazgo | Estado | Commits | Evidencia de después sobre la app real |
|---|---|---|---|
| AUD2-001 CRÍTICO juez | **CERRADO en sus causas estructurales · residuo ABIERTO** | d77128d 3ff8ab4 4841c40 c68cbbc 7cccbce 0d92081 | Re-juicio del escaneo 01a0d086: 22 lanzamientos excluidos, 37 dolores pertinentes, G2 = 4 (relativo), 5 grupos. **Abierto:** el LLM aún etiqueta opiniones genéricas como dolor y deja 1 grupo DESCARTAR incoherente; 0 CONSTRUIR. Es calidad del etiquetado, no se arregla sin más llamadas ni un conjunto dorado mayor. |
| AUD2-002 ALTO fixtures 2099 | CERRADO | 6254260 | Migración 012 aplicada tras respaldo y ensayo: 0 filas sin procedencia, URL `https://` obligatoria; humo: 0 evidencias con fecha futura o fuente desconocida. |
| AUD2-003 ALTO release atada al repo | CERRADO | 0d20c9c c04488b 22901f9 | Humo: el motor corre desde `%LOCALAPPDATA%\com.sentra.desktop\motor\<huella>` con la huella compilada; un motor de otra versión se rechaza. |
| AUD2-004 ALTO sin tests del exe | CERRADO | ef1522b 3f517b0 a2062e0 | `python -m tests.humo_exe` (y `HUMO=1` en la compuerta): `HUMO OK` sobre la release final. Detecta además un exe sin interfaz embebida. |
| AUD2-005 ALTO G7 verde sin datos | CERRADO (reabierto y cerrado) | 3d50e97 16d9d25 | 1.ª evidencia: G7 medida y la dimensión «hueco» decía «no medido» en el mismo veredicto (la dimensión no veía el contexto de G7). Tras 16d9d25: G7 medida y «Hueco de competencia: 12 (100 %)». |
| AUD2-006 MEDIO palabras basura | **CERRADO en la causa raíz · residuo** (reabierto) | 7308843 8c41c91 | 7308843 solo amplió la lista de vacías (síntoma); la release seguía nombrando «already · between». Causa: frecuencia sin distinción y desempate alfabético. Tras 8c41c91 (soporte ≥ 2, c-TF-IDF sobre el escaneo, singular = plural): «domain…», «feedback · outlook · sent…», «duplicate · job…», «templates…». **Residuo:** verbos genéricos en las posiciones 3–5 de grupos de 3–5 piezas. |
| AUD2-007 MEDIO textos | CERRADO | a6616b9 | Captura: regla G2 con su umbral, marcador sin demo, ejemplos de búsqueda de los nichos actuales. |
| AUD2-008 MEDIO Top repetido en Fuentes | CERRADO | 81cb5d9 | Fuentes: «0 para construir · 4 para investigar más · 1 descartados» + «Ver los veredictos en el Radar»; 0 listas de veredictos. |
| AUD2-009 MEDIO búsqueda sin umbral | CERRADO | 1441ba8 | «zzzz», «Facturación», «precios»: 20 → 0 resultados; «email notifications»: 20. |
| AUD2-010 MEDIO e5 en %TEMP% | CERRADO | 60b66c3 | 9 ficheros y 2 252 997 322 B copiados a `%LOCALAPPDATA%\SENTRA\models`; carga sin red con el mismo vector (huella b12659f45b22e881); copia de %TEMP% borrada; búsqueda 20 filas en la release. |
| AUD2-011 MEDIO dos DSN | CERRADO | f58dffd | `migrate.py status` real: 12 aplicadas con `RIR_PG_URL`. |
| AUD2-012 MEDIO fuente en error activa | CERRADO | 16103a5 | La tarjeta en error dice que no entra en el escaneo hasta probarla. |
| AUD2-013 MEDIO log de un minuto | CERRADO | 02b6a86 | 2 MB × 5 copias, INFO. |
| AUD2-014 BAJO aviso del enlazador | CERRADO | cebecc8 | `npm run tauri build`: 0 avisos (las tres builds de hoy). |
| AUD2-015 BAJO carpeta antigua | **ABIERTO: falta tu confirmación para borrar** | — | Preferencias migradas sobre la app real: antes `es`/`system` (sin elegir), después `es`/`dark` (tu última elección en la app antigua), tema aplicado. Queda `%LOCALAPPDATA%\com.reddit-intelligence-radar.desktop` (EBWebView 76 MB + logs 42 KB). |
| AUD2-016 BAJO esquema legacy | CERRADO · `subreddits` ABIERTO | fcc4f6f 6254260 | 7 tablas y 2 columnas legacy fuera; `subreddits` sigue: la referencia `pipeline_runs.subreddit_id` y DP4 no la incluía. |
| AUD2-017 BAJO restos de otro proyecto | CERRADO · scripts de la biblioteca ABIERTOS | c2abc36 | `repos/` → `F:\archivo_sentra\repos` (29 639 ficheros, 1 624 306 693 B, 57 clones); 5 documentos en `docs/historico/` con nota. Los 6 scripts de clonado y `logs/repo_catalog.json` siguen: DP11 no decidió sobre ellos. |
| AUD2-018 MEDIO licencia de Stack Exchange | CERRADO | 260940a | Búsqueda: 13 de 13 filas de Stack Exchange con «CC BY-SA 4.0» y su URL; dossier y plan también. Las 30 piezas guardadas son de 2025-09-25 o después (4.0); Stack Exchange usa 3.0/2.5 antes de 2018-05-02. |
| AUD2-019 BAJO llamada invisible | CERRADO | adf85bd 14d67af | «Lista de modelos pedida a Google hace 2 minutos»; arranque nuevo: 0 peticiones; el re-juicio tampoco lista. |
| AUD2-020 BAJO aviso doble | CERRADO | 22b2da1 | 0 alertas anidadas en la release. |
| AUD2-021 BAJO dependencias sin auditar | CERRADO | 314687c | pip-audit: 0; cargo audit: 0 con RUSTSEC-2023-0071 ignorado con motivo (rsa no entra en el grafo; un test lo vigila). |
| AUD2-022 MEDIO proceso | CERRADO · ver 7.3 | 3f517b0 0ac08f6 | La compuerta vive en el repo; el hook rechazó un commit con un paso en rojo (HEAD sin cambios). `docs/proceso.md`. |
| AUD2-023 BAJO Discourse | CERRADO | 88f84d8 | Tarjeta explicada. |
| AUD2-024 BAJO «Guardar modelos» sin clave | FALSO POSITIVO | — | El botón está deshabilitado sin clave (comprobado en la app). |
| AUD2-025 BAJO escaneo > 600 s | CERRADO (confirmado por código) | 00a0b43 | El timeout de reqwest era total: cortaba un escaneo vivo mientras el motor lo terminaba. Ahora keepalive cada 15 s y corte solo tras 60 s de silencio; tests con flujos reales de bytes. Sin escaneo real (R3). |
| AUD2-026 BAJO memoria de WebView2 | CERRADO: no se reproduce | a2062e0 | 12 min reales en el Radar sobre la release (lector CDP corregido en a2062e0): WebView2 486 → 462 MB (privada 289 → 260 MB), heap JS 3,2–3,9 MB, nodos 2 508–2 604, 0 excepciones. No hay crecimiento. La medida de la PARTE 1 era de otra release y de otro arnés. |
| **AUD2-027 MEDIO (nuevo)** · un cierre a la ventana interna de tao deja SENTRA colgada | CERRADO | 95a578b | Hallado al medir AUD2-026: tras 12 min, un cierre normal no cerraba la app (reproducido sin CDP). Causa verificada en tao 0.35.3: «Tao Thread Event Target» es visible a propósito; un WM_CLOSE que le llega (taskkill, el Restart Manager, un gestor de ventanas) la destruía, y al cerrar después el proceso quedaba vivo sin ventana. Tras 95a578b: WM_CLOSE a esa ventana → proceso terminado y 0 motores; la prueba de humo lo comprueba en cada release. **Hipótesis sin probar:** con GlazeWM, que gestiona ventanas visibles de nivel superior, esto pudo intervenir en la «pantalla negra tras un rato» del principio. |

### 7.2 Notas D01–D14, antes y después

| Dimensión | Antes | Después | Por qué |
|---|---|---|---|
| D01 Producto | 5 | 7 | Fuentes con resumen, textos corregidos, G7 coherente, un solo aviso, licencia y hora del listado visibles. Nombres de nicho aún con verbos genéricos; los motivos del motor solo en español. |
| D02 Corrección | 6 | 8 | Sin fixtures, búsqueda con umbral, humo contra SQL en cada release. |
| D03 Arquitectura | 4 | 7 | Motor versionado con huella, un solo DSN, esquema legacy retirado (salvo `subreddits`). |
| D04 Juez | 2 | 5 | Lanzamientos fuera, solo dolor pertinente, G2 relativo, G7 y hueco coherentes, nombres por distinción. El etiquetado del LLM sigue mezclando opiniones; sin validar con 300 ítems. |
| D05 Integridad | 6 | 8 | Procedencia obligatoria, URL válida, tablas legacy fuera. |
| D06 Seguridad | 8 | 9 | pip-audit y cargo audit en 0 y en la compuerta de release. |
| D07 Fiabilidad | 7 | 8 | Log útil, e5 fuera de %TEMP%, fuentes en error excluidas, escaneos largos sin corte, el cierre por la ventana interna de tao ya no deja el proceso colgado (AUD2-027). |
| D08 Rendimiento | 7 | 8 | Motor activo en 3,2–3,7 s, WebView2 estable en 12 min, búsqueda 20 filas con e5 fuera de %TEMP%. El juez con 300 ítems sigue sin medir. |
| D09 Tests | 4 | 7 | Humo del exe real en la compuerta; lógica de la interfaz con node --test; contratos Py↔Rust↔TS. Sigue habiendo muchas guardas que leen código como texto. |
| D10 Proceso | 5 | 6 | Compuerta y hook en el repo. Pero en esta PARTE 2 cometí errores nuevos (7.3). |
| D11 Build y release | 3 | 7 | Release autocontenida sin avisos; el humo detecta un exe de desarrollo. Falta borrar la carpeta antigua (AUD2-015), la versión sigue 0.1.0 y la release sale de la rama de trabajo (F). |
| D12 Documentación | 4 | 8 | Históricos archivados con nota, README con compuerta, humo y auditorías, `docs/proceso.md`. |
| D13 Costes | 7 | 8 | Listado de modelos guardado un día y visible; re-juicio con 0 llamadas. |
| D14 Cumplimiento | 6 | 8 | CC BY-SA 4.0 y enlace en toda cita de Stack Exchange, R9 intacta. |

### 7.3 Errores míos en la PARTE 2 (R6)

- **Rompí el acceso del escritorio de 03:18 a ~03:32.** Para evidenciar AUD2-014 compilé con `cargo build --release`, que dejó en `target/release/sentra.exe` un exe sin interfaz (abría `localhost:5173`). Lo detecté al migrar las preferencias; recompilé con `npm run tauri build` y la prueba de humo ahora lo detecta (3f517b0).
- **Mi script de evidencias disparó 2 generaciones de dossier.** Pulsaba el primer botón de la tarjeta del Radar, que en esa disposición era «Dossier». Las 2 llegaron a `generate_content`; se cerró la app antes de ninguna respuesta, pero no puedo asegurar que Google no las procesara: las cuento como 2 llamadas posibles. El script ya no pulsa nada y `docs/proceso.md` lo prohíbe.
- **Di por cerrados AUD2-005 y AUD2-006 antes de tiempo.** La evidencia sobre la release los reabrió; ambos se cerraron después en su causa (16d9d25, 8c41c91).
- **El mensaje de 3f517b0 dice «GREEN: 13/13»; eran 11 tests.**
- **La prueba de humo cerraba con `taskkill` sin /F**, cuyo destino cambia entre las dos ventanas de SENTRA: su «cierre normal» dependía del azar. Ahora cierra por la ventana de la app, como la X (95a578b).
- **La primera medida larga de AUD2-026 no vale.** El lector CDP moría en reposo (a2062e0) y cada «minuto» duraba ~100 s; la paré y repetí la medida.
- **Llamadas de listado de modelos.** Mis pruebas de humo y capturas abrieron Configuración y listaron modelos en Google (12 listados en el log de la app) hasta que adf85bd los guardó.

### 7.4 Gemini en la PARTE 2

| Momento | Generación | Listado de modelos |
|---|---|---|
| Re-juicio v3 (DP2 A, run 01a0d264) | 4 (9 732→3 963, 19 474→3 589, 10 168→3 741, 3 803→2 771 tokens) | 1 |
| Mi script de evidencias (no permitido) | 2 posibles, sin respuesta recibida | — |
| Re-juicio de AUD2-005 (run 01a0d295) | 0 | 1 |
| Re-juicio de AUD2-006 (run 01a0d2c3) | 0 | 0 |
| Pruebas de humo y capturas | 0 | 12 hasta adf85bd; 1 después |

Total de generación en la misión: 6 contadas antes de este cierre + 2 posibles = **hasta 8 de 15**. Reddit y X: 0. Escaneos: 0.

### 7.5 Pendiente

- **AUD2-015:** borrar `%LOCALAPPDATA%\com.reddit-intelligence-radar.desktop` cuando lo confirmes.
- **AUD2-001 (residuo):** calidad del etiquetado del LLM; se ve en E8/F con un escaneo real y más datos dorados.
- **AUD2-006 (residuo):** verbos genéricos en nombres de grupos pequeños.
- **AUD2-016:** la tabla `subreddits` (decisión aparte).
- **AUD2-017:** los scripts de la biblioteca de clones (decisión aparte).
- **AUD2-022 (salvaguarda no hecha):** la prueba de humo sigue usando el perfil de WebView real. No tiene uno aparte: en su lugar falla si cambian tus preferencias.
- **E8:** verificar dossier y plan con Gemini real (llamadas, tokens y secciones).
- **F:** F1 instalación limpia; F2 migraciones; F3 release desde `main`; F4 fusión (esta rama no se ha fusionado).
- **G:** G1 Product Hunt.

---

## 8. Ampliación antes de E8 (2026-09-24, pedida por el usuario)

Commits `3e67efd`…`2d36cad`. Release compilada con `npm run tauri build` desde
`2d36cad`; compuerta de release (`CLIPPY=1 AUDIT=1 HUMO=1`) con todos los pasos
en OK y código de salida 0.

| Pedido | Estado | Commits | Evidencia |
|---|---|---|---|
| Borrar la carpeta antigua (AUD2-015) | CERRADO | — | 1 042 ficheros y 76 170 451 B borrados; ningún proceso la usaba. |
| Retirar los scripts de clonado (AUD2-017) | CERRADO | 3e67efd | 9 scripts y `logs/repo_catalog.json` fuera del repo; copia idéntica (hash, 10/10) en `F:\archivo_sentra\scripts`. |
| Retirar `subreddits` con respaldo (AUD2-016) | CERRADO | dac9208 | Migración 013 (R12: respaldo `*_pre013.dump`, ensayo sobre copia, dry-run, aplicación y verificación en solo lectura). Fuera la tabla, `pipeline_runs.subreddit_id` y 10 enums sin uso. Datos intactos: 13 ejecuciones, 82 evidencias, 25 veredictos y 150 etiquetas. |
| Prueba de humo con perfil aislado (AUD2-022) | CERRADO | 79474a5 | Primero una prueba de concepto: `WEBVIEW2_USER_DATA_FOLDER` manda sobre la carpeta de Tauri. Humo real: perfil real `1a7e2ce38b0c46d3` antes y después, perfil aislado usado y borrado. |
| Residuo de AUD2-001 (opiniones como dolor) | CERRADO en su causa | 88302ea 53e6ce2 eff1dde 218d395 e73c2fe | Ver 8.1. |
| Residuo de AUD2-006 (nombres genéricos) | CERRADO en su causa | 2d36cad | Ver 8.2. |

### 8.1 Residuo de AUD2-001: lo que se encontró y lo que se hizo

1. **labels-v4 (`88302ea`).** Campo obligatorio `affected` (author/others/none) con su fragmento literal; solo cuenta el dolor del autor. Re-etiquetado real: 5 llamadas.
   - De los 3 comentarios del grupo incoherente, uno era opinión y deja de ser dolor.
   - Los otros dos son dolores reales del autor (passkeys en Kiwi Browser; un sistema de notificaciones sobredimensionado). **Mi diagnóstico previo («3 opiniones») era erróneo:** leí solo sus primeros 120 caracteres.
2. **La causa real era la agrupación.** Tras v4, un grupo de 5 pasó todas las compuertas (CONSTRUIR) y solo lo bajó el abogado del diablo: «no existe un nicho coherente». Los vectores e5 del post entero agrupan por tema, no por problema.
3. **Medido sin Gemini:**
   - la similitud e5 no separa grupos verdaderos de mezclas en el conjunto dorado (mezclas hasta 0,869; verdaderos 0,830–0,844);
   - centrada, sigue solapándose y el ARI empeora (0,487 → 0,335);
   - hay grupos verdaderos con 0 términos compartidos.
   - **Además, reconozco que DP2 A aprobó «coherencia por grupo» y en la PARTE 2 no la implementé.**
4. **Decisión del usuario:** comprobación LLM por escaneo, y agrupar por la frase del problema midiendo antes en el dorado.
   - **Agrupar por la frase (`53e6ce2`).** Dorado de publicaciones (cada frase con el contexto común del tema): post entero ARI 0,025 (mejor umbral); frase ARI 0,487 y pureza 0,735 frente a 0,618. Criterio fijado antes de medir: cumplido.
   - **G0 (`eff1dde`).** Una llamada por escaneo con las frases de todos los grupos. Medida y distinta → DESCARTAR; sin comprobar → nunca CONSTRUIR. Migración 014 (8 o 9 compuertas), aplicada con R12.
   - **Tope de llamadas en el re-juicio (`218d395`).** R7 no puede pasarse.
5. **Error mío en el paso de la frase:** prefería el fragmento de `affected` (quién), que con datos reales era la presentación del autor. Juntó 20 autores en un grupo; G0 lo rechazó. Corregido en `e73c2fe`: se usa el de `is_pain` (clustering-v6).
6. **Resultado real (re-juicio `01a0d32b`, 1 llamada):** 2 grupos, los 2 DESCARTAR por G0 con razones correctas («WooCommerce, Trac y Keycloak… sin un problema común»). **Este escaneo no tiene ningún nicho coherente:**
   - lo confirman todas las representaciones medidas sin Gemini;
   - con `is_pain`: 4 grupos, todos mezclados;
   - e5 junta frases cortas por estilo («This is…», «This causes…»).
   No se re-juzgó con v6/v7: costaría la llamada 15 de 15 para enseñar otra vez «0 nichos». El próximo escaneo aplicará la versión actual; por eso la interfaz avisa «Veredicto de versiones antiguas (clustering-v5)».

### 8.2 Residuo de AUD2-006

- **Causa:** los nombres genéricos eran el nombre de una mezcla (ahora G0 la descarta) y el contexto común de los posts contaminaba el nombre.
- **Fondo del c-TF-IDF:** ampliarlo no bastaba («clear · increasing · rather» seguía).
- **Nombres desde las frases del problema (`2d36cad`, clustering-v7).** Medido en el dorado:
  - preferencias: «context · handle · infrastructure · team · three» pasa a «users · usuario · avisos · baja · preference»;
  - push: «push · android · apns · cloud · firebase».
- **Test de regresión:** cada grupo verdadero del dorado se nombra por su término.
- **Límite:** sobre datos reales no se puede enseñar porque no hay grupos coherentes; los grupos descartados siguen con nombres de mezcla.

### 8.3 Observación

El puntaje de un grupo descartado por G0 sigue saliendo de las dimensiones (61,7/100 en el grupo mezclado). El veredicto es DESCARTAR, pero la cifra puede confundir. Se propone para E8/F: no puntuar, o marcar, los grupos que fallan G0.

### 8.4 Gemini y errores

- **Generación en esta ampliación:** 5 del re-etiquetado v4 y 1 de coherencia. Total de la misión: **hasta 14 de 15** (dos de ellas «posibles», de mi script). Listados de modelos: 0. Reddit, X y escaneos: 0.
- **Errores míos:**
  - el diagnóstico de las «3 opiniones»;
  - no haber implementado la coherencia de DP2 A;
  - preferir el fragmento de `affected`;
  - una corrupción de barras por heredoc en el plan, detectada y corregida antes del commit.
