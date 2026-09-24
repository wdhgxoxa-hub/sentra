# Plan: cierre de la auditoría AUD2 (2026-09-24)

Origen: `docs/auditoria-2026-09-24.md`. Decisiones del usuario: DP1 B, DP2 A, DP3 A,
DP4 A, DP5 A, DP6 A, DP7 A, DP8 A, DP9 A, DP10 A, DP11 A (`repos/` → `F:\archivo_sentra\repos`).

Reglas: TDD con RED visible; commits «C-AUD2-XXX: …» solo con `commit_si_verde.sh`;
compuerta completa; respaldo en `F:\backups\` antes de cualquier migración, ensayo y
verificación de solo lectura; R9; Gemini ≤ 15 llamadas en total (re-juicio de DP2);
cero escaneos; E8, F y G fuera. Cada hallazgo se cierra con evidencia de antes y
después sobre la app real (prueba de humo / arnés), no solo con tests.

## Orden (por dependencias)

- [ ] T1 · AUD2-004 · Prueba de humo del ejecutable real en el repo (`scripts/humo.py`):
      arranque en frío, datos por vista contra SQL de solo lectura, cierre normal y
      forzado sin huérfanos, preferencias intactas (perfil de WebView aparte). Documentada
      en el README como paso previo a toda release; la compuerta la ejecuta si hay exe.
- [ ] T2 · AUD2-003 (DP1 B) · Motor fijado a la versión: la release copia el código del
      motor a una carpeta versionada fuera del repo y lo lanza desde allí; huella de
      compilación que interfaz y motor comparan (desfase → aviso con código).
- [ ] T3 · AUD2-002 + AUD2-016 (DP3 A, DP4 A) · Migración 012 con respaldo: borra las 18
      filas legacy de demostración y retira el esquema legacy sin uso.
- [ ] T4 · AUD2-006 · Palabras clave: URLs fuera, lista de vacías ampliada, términos cortos.
- [ ] T5 · AUD2-005 · G7 sin datos ≠ aprobada (estado neutral explicado).
- [ ] T6 · AUD2-001 (DP2 A) · Pertinencia por ítem, coherencia por grupo, prompt con
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
- [ ] T7 · AUD2-007, 008 (DP6 A), 009, 012 (DP10 A), 020, 023, 024 · Interfaz.
- [ ] T8 · AUD2-011, 013, 014, 010 (DP9 A), 015 (DP8 A) · Fiabilidad y build.
- [ ] T9 · AUD2-017 (DP11 A), 018 (DP5 A), 019, 021 (DP7 A) · Documentos, cumplimiento,
      auditoría de dependencias.
- [ ] T10 · AUD2-022 · Salvaguardas de proceso (pre-commit con la compuerta).
- [ ] T11 · AUD2-025, 026 · Sospechas: reproducir o cerrar con motivo.
- [ ] Cierre · compuerta verde, release recompilada con SENTRA cerrada, humo en verde,
      informe actualizado (CERRADO con commit / ABIERTO con motivo), push de la rama.
