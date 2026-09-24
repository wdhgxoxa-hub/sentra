# Plan: cerrar pendientes + Fase 4

Spec: `tasks/SPEC-cierre-y-documentos.md`. Commits `C-<fase>: …`; compuerta tras cada uno.

## Orden y dependencias

A (decisiones) → B (juez fiable; E depende de B) → C (interfaz; C1 depende de B4)
→ D (deuda) → E (documentos; depende de B y C) → F (cierre) → G (Product Hunt).

## Fase A — Decisiones
- [x] A1 D-M8…D-M11 en SPEC-multifuente.md, con un test que fije cada una (UI de D-M9 con tsc).

## Fase B — Fiabilidad del juez
- [x] B1.1 Truncado explícito: finish_reason de límite o JSON incompleto → error propio, nunca «sin etiqueta».
- [x] B1.2 Presupuesto de razonamiento del etiquetado con la opción exacta del SDK instalado (verificada en su código).
- [x] B1.3 Si aun así se trunca: dividir el lote a la mitad y reintentar solo esa mitad, recursivo, con tope.
- [x] B2 Pooling de e5: verificar en fastembed instalado; fijarlo explícitamente; si difiere de lo guardado, recalcular evidence_e5 de forma idempotente.
- [x] B3.1 Conjunto dorado de agrupación inventado y bilingüe (≥ 6 sub-problemas × 8–12 + ruido).
- [x] B3.2 Pureza y ARI; barrido de umbrales; comparación con enlace promedio; elegir por métrica → clustering-v2 con test de regresión.
- [x] B3.3 Re-juicio de 01a0d086 (etiquetando los 40 undetermined, dentro del tope de Gemini); si sale 1 grupo, un escaneo real con tema más amplio.
- [x] B4 Veredictos con versiones (etiquetador, agrupación, pesos); los antiguos, marcados (migración 011 si hace falta, R12).

## Fase C — Una sola verdad (D-C2)
- [x] C1 Radar en vivo: Top 6 del juez + veredictos + feed de evidencia, desde la misma fuente que el panel.
- [x] C2 Inventario de la pipeline antigua; retirar lo que no tiene usuarios (commits propios, tests de «nadie lo usa»); documentar lo que queda.
- [x] C3 Vite: división de código hasta que ningún chunk supere 500 kB.

## Fase D — Deuda residual
- [x] D1 Prueba de clave de Gemini: fallo de red ≠ clave rechazada.
- [x] D2 tearDown de entorno/logging → addCleanup, con test de guardia.
- [x] D3 Una sola `postgres_available` compartida.
- [x] D4 `check_untyped_defs` en tests/ a 0 errores (commit propio).
- [x] D5 Rutas de generate_index.py y demo_ingestion.py; nada generado sin .gitignore.
- [x] D6 Triaje AUD-032…AUD-071 y cierre de los abiertos.

## Fase E — Del nicho al MVP
- [ ] E1 Modelo de documento genérico (sin el documento por cluster ni blueprint) y PDF con franja y marca de agua; tests con pypdf.
- [ ] E2 Carga del veredicto con toda su evidencia (store) para los documentos.
- [ ] E3 Esquemas estrictos (Claim, dossier, plan, viabilidad) y validación de citas: una cita inválida retira la afirmación.
- [ ] E4 Generación con generate_json (modelo de documentos, presupuesto, división por truncado, tope 3 llamadas) con dobles.
- [ ] E5 Composición del dossier y del plan (secciones fijas, avisos, franja, viabilidad «estimación del modelo») y Markdown para agente.
- [ ] E6 Sidecar (caché en memoria) + Rust (diálogo nativo) + contratos.
- [ ] E7 UI en el panel del juez: botones, estados, forzar el plan, i18n.
- [ ] E8 Verificación real (tras elegir el usuario el modelo en Ajustes): llamadas, tokens y secciones.

## Fase F — Cierre
- [ ] F1 Compuerta; instalación limpia temporal.
- [ ] F2 Migraciones (R12).
- [ ] F3 Release con SENTRA cerrada; grep -c -a; SENTRA.lnk.
- [ ] F4 Push, fast-forward, push de main.

## Fase G — Credenciales
- [ ] G1 Product Hunt: pedir el token en su tarjeta, esperar y probar.

## Calibración de la agrupación (B3.2, 2026-09-23)

Conjunto dorado: tests/fixtures/golden_clusters.json (6 subproblemas de «notificaciones» × 10, es/en, + 8 de ruido).
Vectores: tests/fixtures/golden_clusters_e5.npz (e5, mean pooling). Barrido: scripts/calibrar_agrupacion.py.
Criterio fijado antes de mirar: ARI máximo; a igualdad, más pureza; a igualdad, umbral más alto.

| método | umbral | grupos (>= 3) | pureza | ARI |
|---|---|---|---|---|
| lider | 0.78 | 1 | 0.147 | 0.000 |
| lider | 0.79 | 1 | 0.147 | 0.000 |
| lider | 0.80 | 1 | 0.147 | 0.000 |
| lider | 0.81 | 1 | 0.147 | 0.000 |
| lider | 0.82 | 1 | 0.162 | 0.008 |
| lider | 0.83 | 1 | 0.162 | 0.008 |
| lider | 0.84 | 1 | 0.191 | 0.025 |
| lider | 0.85 | 2 | 0.324 | 0.071 |
| lider | 0.86 | 3 | 0.426 | 0.206 |
| lider | 0.87 | 4 | 0.559 | 0.225 |
| lider | 0.88 | 5 | 0.971 | 0.153 |
| lider | 0.89 | 0 | 1.000 | 0.000 |
| lider | 0.90 | 0 | 1.000 | 0.000 |
| lider | 0.91 | 0 | 1.000 | 0.000 |
| lider | 0.92 | 0 | 1.000 | 0.000 |
| lider | 0.93 | 0 | 1.000 | 0.000 |
| lider | 0.94 | 0 | 1.000 | 0.000 |
| enlace_promedio | 0.78 | 2 | 0.221 | 0.073 |
| enlace_promedio | 0.79 | 2 | 0.221 | 0.073 |
| enlace_promedio | 0.80 | 2 | 0.250 | 0.073 |
| enlace_promedio | 0.81 | 5 | 0.544 | 0.323 |
| enlace_promedio | 0.82 | 6 | 0.735 | 0.487 |
| enlace_promedio | 0.83 | 8 | 0.824 | 0.351 |
| enlace_promedio | 0.84 | 7 | 0.868 | 0.276 |
| enlace_promedio | 0.85 | 5 | 0.897 | 0.152 |
| enlace_promedio | 0.86 | 5 | 0.956 | 0.132 |
| enlace_promedio | 0.87 | 2 | 0.971 | 0.057 |
| enlace_promedio | 0.88 | 1 | 0.985 | 0.005 |
| enlace_promedio | 0.89 | 1 | 0.985 | 0.005 |
| enlace_promedio | 0.90 | 0 | 1.000 | 0.000 |
| enlace_promedio | 0.91 | 0 | 1.000 | 0.000 |
| enlace_promedio | 0.92 | 0 | 1.000 | 0.000 |
| enlace_promedio | 0.93 | 0 | 1.000 | 0.000 |
| enlace_promedio | 0.94 | 0 | 1.000 | 0.000 |

Elegido: enlace_promedio con umbral 0.82 (pureza 0.735, ARI 0.487)

Variante exploratoria evaluada después (vectores centrados por la media del corpus): enlace promedio centrado,
mejor ARI 0,335 (peor); líder centrado, pico aislado de ARI 0,649 en 0,00 con vecinos 0,230 y 0,062 y pureza 0,603.
No se adopta: sin meseta es suerte sobre 68 ítems, no una mejora demostrada.

Elegido clustering-v2 = enlace promedio con 0,82 (pureza 0,735, ARI 0,487, 6 grupos). Test de regresión:
tests/test_judge_cluster_calibration.py.

## Re-juicio de 01a0d086 (B3.3, 2026-09-23)

Ejecución de re-juicio `01a0d0b6-2b16-751e-893d-b6807a9a2700` (trigger `rejuicio`), con las
versiones labels-v2/gemini-3.8-flash, clustering-v2 y judge-weights-v1. Entrada: 79 ítems canónicos
de 01a0d086 con su vector e5 ya guardado (B2: el pooling no cambió, no hubo que recalcular).
Gemini: 2 llamadas reales (7 258 → 4 488 y 21 694 → 5 019 tokens), sin truncado. La caché
labels-v2 cubrió el resto. Resultado: 75 pasan, 4 descartes por spam, 0 sin etiqueta, 9 grupos
(antes 1).

| veredicto | palabras clave | miembros | fuentes | puntaje | faltan |
|---|---|---|---|---|---|
| INVESTIGAR MÁS | email · notifications · com · free | 14 | HN 14 | 27.8 | G1 G4 G6 |
| INVESTIGAR MÁS | email · notifications · built · time | 12 | HN 12 | 28.3 | G1 G4 G6 |
| DESCARTAR | email · code · notification · send | 7 | SE 7 | 13.2 | G1 G2 |
| INVESTIGAR MÁS | email · user · users · want | 5 | Discourse 1, SE 4 | 26.1 | G2 G6 |
| DESCARTAR | email · notifications · after · call | 4 | SE 4 | 12.7 | G1 G2 G6 |
| DESCARTAR | notifications · email · notification · point | 4 | HN 2, SE 2 | 20.0 | G2 G6 |
| DESCARTAR | email · app · don · log | 3 | HN 3 | 24.3 | G1 G2 G4 |
| DESCARTAR | email · job · send · use | 3 | HN 1, SE 2 | 14.3 | G2 G4 G5 G6 |
| DESCARTAR | email · notifications · actually · comment | 3 | HN 3 | 3.8 | G1 … G6 |

Al salir más de un grupo, no se lanza el escaneo real nuevo (la misión lo reserva para el caso de
un solo grupo). No hay ningún CONSTRUIR: el abogado del diablo no llegó a actuar.
