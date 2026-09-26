"""
Fuentes que encajan con el tema del escaneo (Fase 3, medida B de Walter)
========================================================================

Escaneo 2 («perseguir a los clientes para que manden sus documentos al
contable»): GitHub solo tiene issues de software y Stack Exchange buscaba en
Stack Overflow; 50 de las 53 quejas eran fallos de programación.

- GitHub solo entra en temas de software.
- Stack Exchange, solo con algún sitio adecuado al tema (catálogo cerrado,
  `sitios_stackexchange.py`).
- Lo que no encaja se omite en ese escaneo; el motivo queda como motivo de
  parada de la fuente (`run_source_outcomes.stop_reason`) y se dice en pantalla.
- Sin saber el tipo (sin Gemini, perfiles antiguos, descubrimiento) no se
  omite nada: no se decide a ciegas.
"""

from __future__ import annotations

from collections.abc import Iterable

from .profile import ScanProfile

#: Motivos de parada de una fuente omitida (texto libre en la base: sin migración).
NO_ES_SOFTWARE = "omitida:no_es_software"
SIN_SITIO = "omitida:sin_sitio"
PREFIJO = "omitida:"


def fuentes_omitidas(perfil: ScanProfile, fuentes: Iterable[str]) -> dict[str, str]:
    """{fuente: motivo} de las que no se consultan en este escaneo."""
    if perfil.discovery or perfil.topic_kind is None:
        return {}
    presentes = set(fuentes)
    omitidas: dict[str, str] = {}
    if "github" in presentes and perfil.topic_kind != "software":
        omitidas["github"] = NO_ES_SOFTWARE
    if "stackexchange" in presentes and not perfil.targets.get("stackexchange"):
        omitidas["stackexchange"] = SIN_SITIO
    return omitidas
