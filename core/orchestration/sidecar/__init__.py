"""
Routers del sidecar (R-D)
=========================

Cada módulo expone `router(ctx)` con las rutas de una responsabilidad; el
servidor (`core.orchestration.sidecar_server`) los monta con el token por
delante de todos:

- `health`: estado del servicio y de la fuente.
- `scan`: escaneo normal, en streaming (SSE) y cancelación, con persistencia.
- `config`: configuración y credenciales de Reddit.
- `gemini`: clave, arquitecto y traducción.
- `documents`: PRD y exportación a PDF.
- `search`: búsqueda híbrida sobre LanceDB.

`context` guarda el estado compartido entre routers y `schemas` los modelos
de petición y respuesta.
"""
