# Reglas de proceso

Salvaguardas de AUD2-022 (auditoría del 2026-09-24). Las que se pueden
automatizar ya lo están; el resto se cumple a mano y se revisa en cada informe.

## Automatizadas

- **Compuerta en cada commit.** `scripts/compuerta.sh` falla si falla
  cualquier paso; el hook `.githooks/pre-commit` la ejecuta
  (`git config core.hooksPath .githooks`). No se usa `--no-verify`.
  Límite conocido: la compuerta corre sobre el árbol de trabajo, no solo sobre
  lo preparado; antes de un commit no debe haber cambios sin preparar que
  hagan pasar la compuerta (`git status` limpio salvo lo que se commitea).
- **Prueba de humo antes de cada release** (`HUMO=1`). Detecta un exe sin la
  interfaz embebida, un motor que no es el de esa interfaz, vistas vacías con
  datos en la base, motores huérfanos y preferencias del usuario cambiadas.
- **Dependencias auditadas antes de cada release** (`AUDIT=1`).

## A mano

- **«Verificado» solo con datos.** Un hallazgo o un arreglo se da por
  verificado con su antes y después sobre la app real, contrastado con SQL
  de solo lectura; un DOM no vacío o un test en verde no bastan.
- **TDD visible.** El mensaje de cada commit dice qué test falló primero
  (RED) y cómo quedó (GREEN).
- **La release se compila con `npm run tauri build`.** Un `cargo build
  --release` suelto sobrescribe el exe del acceso directo con uno sin
  interfaz.
- **Los arneses sobre la app real no pulsan botones** que llamen a servicios
  externos (un botón del Radar genera documentos con Gemini) y restauran las
  preferencias por estado, nunca por el texto de un menú.
- **Ediciones con herramientas de edición**, no con heredoc ni `sed`: las
  barras invertidas se corrompen.
- **Llamadas a Gemini contadas.** Cada llamada real (generación o listado de
  modelos) se anota con su motivo y sus tokens.
