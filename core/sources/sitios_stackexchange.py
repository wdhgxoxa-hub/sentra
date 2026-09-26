"""
Sitios de Stack Exchange que SENTRA sabe consultar (Fase 3, medida B)
=====================================================================

Catálogo cerrado: el perfil solo acepta estos sitios y la propuesta de
Gemini elige de aquí (no puede inventar uno). Antes se buscaba siempre en
Stack Overflow, que es de programación: en el escaneo 2, de contabilidad, sus
42 piezas eran fallos de código. Clave = el `site` de la API; valor = el
nombre que se ve.
"""

from __future__ import annotations

SITIOS: dict[str, str] = {
    # Software.
    "stackoverflow": "Stack Overflow",
    "es.stackoverflow": "Stack Overflow en español",
    "superuser": "Super User",
    "serverfault": "Server Fault",
    "askubuntu": "Ask Ubuntu",
    "softwareengineering": "Software Engineering",
    "webapps": "Web Applications",
    "softwarerecs": "Software Recommendations",
    "ux": "User Experience",
    # Negocio, trabajo y dinero.
    "money": "Personal Finance & Money",
    "freelancing": "Freelancing",
    "workplace": "The Workplace",
    "pm": "Project Management",
    "law": "Law",
}


def sitio_de(objetivo: str) -> str:
    """El sitio de un objetivo del perfil: 'freelancing:invoicing' → 'freelancing'."""
    return objetivo.strip().partition(":")[0]
