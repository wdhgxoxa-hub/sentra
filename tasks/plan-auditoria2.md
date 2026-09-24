# Plan: cierre de la auditoría AUD2 (2026-09-24)

Origen: `docs/auditoria-2026-09-24.md`. Decisiones del usuario: DP1 B, DP2 A, DP3 A,
DP4 A, DP5 A, DP6 A, DP7 A, DP8 A, DP9 A, DP10 A, DP11 A (`repos/` → `F:\archivo_sentra\repos`).

Reglas: TDD con RED visible; commits «C-AUD2-XXX: …» solo con `commit_si_verde.sh`;
compuerta completa; respaldo en `F:\backups\` antes de cualquier migración, ensayo y
verificación de solo lectura; R9; Gemini ≤ 15 llamadas en total (re-juicio de DP2);
cero escaneos; E8, F y G fuera. Cada hallazgo se cierra con evidencia de antes y
después sobre la app real (prueba de humo / arnés), no solo con tests.

## Orden (por dependencias)

- [x] T1 · AUD2-004 · Prueba de humo del ejecutable real en el repo (`scripts/humo.py`):
      arranque en frío, datos por vista contra SQL de solo lectura, cierre normal y
      forzado sin huérfanos, preferencias intactas (perfil de WebView aparte). Documentada
      en el README como paso previo a toda release; la compuerta la ejecuta si hay exe.
      Hecho: `tests/humo_exe.py` (no `scripts/humo.py`) y `HUMO=1`. **No hecho:** el perfil de
      WebView aparte; en su lugar la prueba falla si cambian las preferencias del usuario.
- [x] T2 · AUD2-003 (DP1 B) · Motor fijado a la versión: la release copia el código del
      motor a una carpeta versionada fuera del repo y lo lanza desde allí; huella de
      compilación que interfaz y motor comparan (desfase → aviso con código).
- [x] T3 · AUD2-002 + AUD2-016 (DP3 A, DP4 A) · Migración 012 con respaldo: borra las 18
      filas legacy de demostración y retira el esquema legacy sin uso.
- [x] T4 · AUD2-006 · Palabras clave: URLs fuera, lista de vacías ampliada, términos cortos.
      Reabierto por la evidencia: la causa era frecuencia sin distinción y desempate
      alfabético; cerrado en 8c41c91 (soporte ≥ 2, c-TF-IDF, singular = plural; clustering-v4).
- [x] T5 · AUD2-005 · G7 sin datos ≠ aprobada (estado neutral explicado).
      Reabierto por la evidencia: la dimensión «hueco» no veía el contexto de G7; 16d9d25.
- [x] T6 · AUD2-001 (DP2 A) · Pertinencia por ítem, coherencia por grupo, prompt con
      negativos, G2 relativo al tamaño; fixtures; re-juicio real con presupuesto.
      Causa raíz (pipeline.py:52): se agrupaba TODO lo que pasa el filtro de calidad, así
      que los grupos salían por tema («email») y mezclaban lanzamientos y comentarios
      sueltos; el etiquetador contaba «Show HN: I built X» como parche casero.
      Diseño:
      6.1 Pertinencia (código): un lanzamiento propio («Show HN/Launch HN») no cuenta como
          dolor, parche ni señal de pago aunque la etiqueta lo diga.
      6.2 Etiquetador: ejemplos negativos en el prompt (anunciar lo que uno construyó no
          es dolor ni parche; parche = cómo se apaña hoy el autor); LABELER_VERSION v3.
      6.3 Juez: se agrupa solo la evidencia con dolor pertinente; lo demás cercano al
          centroide del grupo solo sirve de contexto para G7 (competidores). G2 relativo:
          N = min(8, max(3, ⌈10 % del dolor pertinente del escaneo⌉)). Los términos del
          tema del escaneo no nombran nichos. CLUSTERING_VERSION v3 y pesos/reglas v2.
      6.4 scripts/rejuzgar.py: re-juicio reproducible de un escaneo guardado (nueva
          ejecución «rejuicio»), sin escaneo nuevo.
      6.5 Re-juicio real del escaneo 01a0d086 con respaldo previo; llamadas a Gemini
          contadas (quedan 13 de 15).
- [x] T7 · AUD2-007, 008 (DP6 A), 009, 012 (DP10 A), 020, 023, 024 · Interfaz.
- [x] T8 · AUD2-011, 013, 014, 010 (DP9 A), 015 (DP8 A) · Fiabilidad y build.
      AUD2-015: carpeta antigua borrada con el sí del usuario (1 042 ficheros, 76 170 451 B).
      Hecho todo salvo el borrado de la carpeta antigua de AUD2-015 (preferencias ya
      migradas): espera la confirmación del usuario.
- [x] T9 · AUD2-017 (DP11 A), 018 (DP5 A), 019, 021 (DP7 A) · Documentos, cumplimiento,
      auditoría de dependencias.
- [x] T10 · AUD2-022 · Salvaguardas de proceso (pre-commit con la compuerta).
- [x] T11 · AUD2-025, 026 · Sospechas: reproducir o cerrar con motivo.
- [x] Cierre · compuerta verde, release recompilada con SENTRA cerrada, humo en verde,
      informe actualizado (CERRADO con commit / ABIERTO con motivo), push de la rama.
      Hecho salvo lo que espera al usuario: compuerta de release en verde (731 Python, 9 node,
      81 Rust, clippy, pip-audit, cargo-audit, humo), release desde el código de 95a578b,
      informe §7. Nuevo: AUD2-027 (cierre por la ventana interna de tao), cerrado en 95a578b.

## Ampliación antes de E8 (pedida por el usuario, 2026-09-24)

Orden: primero lo que no gasta Gemini (A–C); luego el etiquetador (D, único gasto) y
los nombres (E, sobre las etiquetas nuevas); al final, cierre.

- [x] A · Retirar los 9 scripts de la biblioteca de clones (clone_manager, clone_batch2,
      generate_index, repo_analyzer, verify_integrity, test_radar, update_results,
      print_report, test_candidates) y logs/repo_catalog.json; copia en
      F:\archivo_sentra\scripts. Acepta: test_sin_restos los prohíbe; test_scripts_rutas
      sin lo que vigilaba de ellos; nota de docs/historico al día.
- [x] B · Migración 013: fuera `subreddits` y `pipeline_runs.subreddit_id` (R12: respaldo
      en F:\backups, ensayo sobre copia restaurada, dry-run, aplicación y verificación en
      solo lectura). start_run sin subreddit_id. Acepta: test_migracion_013 en rojo y luego
      en verde; 0 tablas ni columnas; ejecuciones intactas (13 filas).
- [x] C · Prueba de humo con perfil de WebView aislado (WEBVIEW2_USER_DATA_FOLDER temporal).
      Primero una prueba de concepto: comprobar que la variable manda sobre la carpeta de
      Tauri. Acepta: el perfil real (Local Storage) no cambia byte a byte; el humo falla si
      la app usara el perfil real.
- [x] D · Residuo de AUD2-001: el etiquetado no distingue quién sufre el problema.
      Campo nuevo `affected` (author/others/none) con su fragmento literal; is_pain solo
      cuenta con affected=author verificado. labels-v4. Re-etiquetado real del escaneo
      01a0d086 con respaldo: ~4 llamadas de generación (total ≤ 12/15). Acepta: los 3
      comentarios de opinión del grupo DESCARTAR dejan de ser dolor; los 4 grupos buenos
      siguen.
- [x] E · Residuo de AUD2-006: el fondo del c-TF-IDF pasa a ser todo el escaneo (79 piezas),
      no solo el dolor (37). Medido antes sobre datos reales sin Gemini. clustering-v5.
      Acepta: sin verbos genéricos en los nombres del re-juicio, o se dice cuáles quedan.
- [x] Cierre · release con `npm run tauri build`, compuerta de release (CLIPPY/AUDIT/HUMO),
      informe §8, push de la rama (sin fusionar).

| Riesgo | Mitigación |
|---|---|
| WEBVIEW2_USER_DATA_FOLDER no manda sobre Tauri | prueba de concepto antes de tocar el humo |
| La migración rompe datos | respaldo + ensayo en copia restaurada + dry-run |
| El re-etiquetado gasta más de lo previsto | lotes contados; si faltan llamadas, se para y se dice |

Resultado de D y E (con cambio de diseño decidido por el usuario: G0 y agrupar por la frase
del problema): ver docs/auditoria-2026-09-24.md §8.
