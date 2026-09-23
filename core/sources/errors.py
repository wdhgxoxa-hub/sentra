"""
Errores comunes de las fuentes (F2.1)
=====================================

Toda fuente falla con uno de estos tipos, con un `code` estable que la
interfaz traduce. Un fallo NUNCA se convierte en «0 resultados»: la lección
de AUD-003 es que un hueco silencioso se lee como «no hay dolor», que es
justo el falso negativo que el juez no puede distinguir.
"""

from __future__ import annotations


class SourceError(RuntimeError):
    """Fallo de una fuente. `transient` dice si merece la pena reintentar."""

    code = "source_error"
    transient = False

    def __init__(self, source: str, detail: str) -> None:
        super().__init__(f"{source}: {detail}")
        self.source = source
        self.detail = detail


class SourceCredentialsMissing(SourceError):
    code = "source_credentials_missing"


class SourceAuthFailed(SourceError):
    code = "source_auth_failed"


class SourceForbidden(SourceError):
    code = "source_forbidden"


class SourceNotFound(SourceError):
    code = "source_not_found"


class SourceUnavailable(SourceError):
    code = "source_unavailable"
    transient = True


class SourceRateLimited(SourceError):
    """Cuota agotada. `retry_after`: segundos hasta poder volver (None = no lo dice)."""

    code = "source_rate_limited"
    transient = True

    def __init__(self, source: str, detail: str, retry_after: float | None = None) -> None:
        super().__init__(source, detail)
        self.retry_after = retry_after


class SourceBudgetExhausted(SourceError):
    """Se agotó el presupuesto del escaneo para esta fuente: la petición no sale."""

    code = "source_budget_exhausted"


#: Todos, para exigir su traducción en la interfaz.
TODOS: tuple[type[SourceError], ...] = (
    SourceError, SourceCredentialsMissing, SourceAuthFailed, SourceForbidden,
    SourceNotFound, SourceUnavailable, SourceRateLimited, SourceBudgetExhausted,
)
