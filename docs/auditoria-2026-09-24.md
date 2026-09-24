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
