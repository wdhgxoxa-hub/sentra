# Plan: cerrar pendientes + Fase 4

Spec: `tasks/SPEC-cierre-y-documentos.md`. Commits `C-<fase>: …`; compuerta tras cada uno.

## Orden y dependencias

A (decisiones) → B (juez fiable; E depende de B) → C (interfaz; C1 depende de B4)
→ D (deuda) → E (documentos; depende de B y C) → F (cierre) → G (Product Hunt).

## Fase A — Decisiones
- [ ] A1 D-M8…D-M11 en SPEC-multifuente.md, con un test que fije cada una (UI de D-M9 con tsc).

## Fase B — Fiabilidad del juez
- [ ] B1.1 Truncado explícito: finish_reason de límite o JSON incompleto → error propio, nunca «sin etiqueta».
- [ ] B1.2 Presupuesto de razonamiento del etiquetado con la opción exacta del SDK instalado (verificada en su código).
- [ ] B1.3 Si aun así se trunca: dividir el lote a la mitad y reintentar solo esa mitad, recursivo, con tope.
- [ ] B2 Pooling de e5: verificar en fastembed instalado; fijarlo explícitamente; si difiere de lo guardado, recalcular evidence_e5 de forma idempotente.
- [ ] B3.1 Conjunto dorado de agrupación inventado y bilingüe (≥ 6 sub-problemas × 8–12 + ruido).
- [ ] B3.2 Pureza y ARI; barrido de umbrales; comparación con enlace promedio; elegir por métrica → clustering-v2 con test de regresión.
- [ ] B3.3 Re-juicio de 01a0d086 (etiquetando los 40 undetermined, dentro del tope de Gemini); si sale 1 grupo, un escaneo real con tema más amplio.
- [ ] B4 Veredictos con versiones (etiquetador, agrupación, pesos); los antiguos, marcados (migración 011 si hace falta, R12).

## Fase C — Una sola verdad (D-C2)
- [ ] C1 Radar en vivo: Top 6 del juez + veredictos + feed de evidencia, desde la misma fuente que el panel.
- [ ] C2 Inventario de la pipeline antigua; retirar lo que no tiene usuarios (commits propios, tests de «nadie lo usa»); documentar lo que queda.
- [ ] C3 Vite: división de código hasta que ningún chunk supere 500 kB.

## Fase D — Deuda residual
- [ ] D1 Prueba de clave de Gemini: fallo de red ≠ clave rechazada.
- [ ] D2 tearDown de entorno/logging → addCleanup, con test de guardia.
- [ ] D3 Una sola `postgres_available` compartida.
- [ ] D4 `check_untyped_defs` en tests/ a 0 errores (commit propio).
- [ ] D5 Rutas de generate_index.py y demo_ingestion.py; nada generado sin .gitignore.
- [ ] D6 Triaje AUD-032…AUD-071 y cierre de los abiertos.

## Fase E — Del nicho al MVP
- [ ] E1 Esquemas del dossier y del plan (JSON estricto) y validación de citas.
- [ ] E2 Viabilidad (dimensión 7) como estimación del modelo, sin tocar compuertas.
- [ ] E3 Generación con generate_json (modelo de documentos, presupuesto y truncado como B1).
- [ ] E4 Renderizado: PDF (ReportLab) de ambos y Markdown del plan para agente; franja, avisos y marca de agua por código.
- [ ] E5 Sidecar + Rust + diálogo nativo de guardado.
- [ ] E6 UI en el panel del juez (botones, estados, i18n).
- [ ] E7 Verificación real (tras elegir el usuario el modelo en Ajustes).

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
