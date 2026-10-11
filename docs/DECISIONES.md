# Decisiones de SENTRA (registro corto)

Las decisiones de producto y del juez siguen en `tasks/SPEC-*.md` (D-M*, D-C*) y en
`CLAUDE.md`. Aquí van las de infraestructura de la máquina, más nuevas.

## 2026-10-11 · Fase 2 de David: la base pasa a un contenedor (`sentra-pg`)

- **Qué.** La base `reddit_intelligence_radar` se copia a un Postgres 18.6 propio en
  Podman sin administrador: contenedor `sentra-pg`, `127.0.0.1:5438`, volumen
  `sentra-pg-datos`, red interna `sentra`. Los Quadlets viven en `deploy/contenedores/`
  y en `~/.config/containers/systemd/` solo hay enlaces (plantilla del agente A,
  `~/Proyectos/contenedores`). Imagen oficial por digest; clave del superusuario en
  el secreto de podman `sentra-pg-postgres` (nace en el llavero, nunca en git).
- **Por qué.** Hoy SENTRA comparte el Postgres nativo con D&S Factory y tiene que
  turnarse con sus tests (CLAUDE.md, «D&S Factory comparte PostgreSQL»). Con su propio
  contenedor cada uno va por su lado.
- **Solo la base.** La ventana (Tauri), el motor (hijo de la ventana, con token por
  arranque) y el MCP (lo lanza Claude Desktop) se quedan nativos.
- **Collation.** `C.UTF-8` con libc, como la base nativa (medido en solo lectura:
  `datcollate = datctype = C.UTF-8`, `datlocprovider = c`, UTF8).
- **Rol lector nuevo.** `sentra_lector` (NOLOGIN, sin contraseña) con SELECT en todo y
  `ALTER DEFAULT PRIVILEGES` de `sentra_owner`: para respaldos y, más adelante, el MCP.
- **Roles con la clave de hoy.** `sentra_owner` y `sentra_pruebas` los copia David con
  `copiar-roles-nativos` (viaja el hash scram, nadie ve la clave). Hasta entonces
  `sentra_owner` está NOLOGIN en el contenedor y la app sigue en el nativo.
- **Rama.** CLAUDE.md dice que la migración a Linux está en `fase-linux/migracion`,
  pero la rama activa y al día es `main`; por decisión de David estos commits van a
  `main`.
- **Vuelta atrás.** La base nativa queda intacta 7 días. Mientras la configuración no
  apunte al 5438, todo va al 5432 como antes; `systemctl --user stop sentra-pg` para el contenedor sin perder datos.
