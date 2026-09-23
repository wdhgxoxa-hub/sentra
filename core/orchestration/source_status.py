"""
Estado real de la fuente de datos (AUD-004)
===========================================

El indicador de la interfaz no puede reflejar el modo elegido, sino la
capacidad real de leer. Por eso se lleva la cuenta de lo que ha pasado de
verdad contra Reddit:

    demo                     datos fabricados (corpus de demostración)
    reddit_sin_credenciales  modo Reddit sin client_id / client_secret
    reddit_sin_verificar     credenciales guardadas, sin acceso real todavía
    reddit_verificado        hubo una respuesta 200 real de la API OAuth
    reddit_error             el último acceso falló (con su código estable)

`reddit_verificado` solo se alcanza con `record_success`, que el sidecar
llama tras un escaneo en modo Reddit que no falló o una prueba de conexión
que obtuvo token. Guardar credenciales nuevas lo reinicia: lo verificado era
otra cosa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

SourceState = Literal[
    "demo",
    "reddit_sin_credenciales",
    "reddit_sin_verificar",
    "reddit_verificado",
    "reddit_error",
]


@dataclass
class SourceTracker:
    """Lo último que pasó de verdad al hablar con Reddit."""

    last_success_at: datetime | None = None
    last_error_code: str | None = None

    def reset(self) -> None:
        """Olvida lo verificado: las credenciales han cambiado."""
        self.last_success_at = None
        self.last_error_code = None

    def record_success(self, at: datetime | None = None) -> None:
        """Reddit respondió 200 a una petición autenticada."""
        self.last_success_at = at or datetime.now(UTC)
        self.last_error_code = None

    def record_failure(self, code: str) -> None:
        """El último acceso falló con el código estable `code`."""
        self.last_error_code = code

    def snapshot(self, mode: str, has_credentials: bool) -> dict[str, Any]:
        """Estado actual, con la evidencia que lo sostiene."""
        state: SourceState
        if mode != "reddit":
            state = "demo"
        elif not has_credentials:
            state = "reddit_sin_credenciales"
        elif self.last_error_code is not None:
            state = "reddit_error"
        elif self.last_success_at is not None:
            state = "reddit_verificado"
        else:
            state = "reddit_sin_verificar"

        return {
            "state": state,
            "lastSuccessAt": (
                self.last_success_at.isoformat() if self.last_success_at else None
            ),
            "errorCode": self.last_error_code if state == "reddit_error" else None,
        }
