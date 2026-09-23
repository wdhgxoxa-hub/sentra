"""
Atribución de la evidencia (R5 y términos de Stack Exchange)
============================================================

Toda pieza de evidencia que se enseña (interfaz, documento, PDF) lleva tres
cosas: la insignia de la plataforma, el sitio o comunidad y la URL del
original en texto plano. Los términos de la API de Stack Exchange lo
exigen («indicar visualmente que la red Stack Exchange es la fuente»; sin
navegador basta la URL en texto plano) y SENTRA lo aplica a todas.
"""

from __future__ import annotations

from core.evidence.model import EvidenceItem

from .catalog import by_id


def attribution(item: EvidenceItem) -> dict[str, str]:
    """Insignia, sitio y URL del original de una pieza de evidencia."""
    fuente = by_id(item.source)
    return {
        "badge": fuente.display_name if fuente else item.source,
        "site": item.community,
        "url": item.url,
    }


def attribution_line(item: EvidenceItem) -> str:
    """La atribución en una línea de texto plano (documentos y PDF)."""
    datos = attribution(item)
    return f"{datos['badge']} · {datos['site']} · {datos['url']}"
