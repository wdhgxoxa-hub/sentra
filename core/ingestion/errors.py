"""
Errores de acceso a Reddit
==========================

Cada forma en que Reddit puede negarse a dar datos tiene su tipo y un código
estable. El código es lo que viaja hasta la interfaz, que lo traduce: nunca
se enseña al usuario el texto crudo de una excepción.

Existen para que la ausencia de datos no se confunda con una página vacía.
Un escaneo sin acceso tiene que fallar diciendo por qué; «completado con 0
resultados» solo es verdad cuando Reddit respondió 200 con una lista vacía.

    RedditAccessError
    ├── RedditAuthError            credenciales o token
    │   ├── RedditCredentialsMissing   no hay client_id / client_secret
    │   └── RedditAuthFailed           401: Reddit rechaza las credenciales
    ├── RedditForbidden            403
    ├── RedditNotFound             404: subreddit inexistente o privado
    ├── RedditRateLimited          429, con los segundos de Retry-After
    └── RedditUnavailable          5xx, red caída o respuesta que no es JSON
"""

from __future__ import annotations

from collections.abc import Mapping


class RedditAccessError(RuntimeError):
    """Reddit no entregó los datos pedidos. `code` es estable y traducible."""

    code = "reddit_access_error"


class RedditAuthError(RedditAccessError):
    """No se pudo obtener un token de acceso válido."""

    code = "reddit_auth_failed"


class RedditCredentialsMissing(RedditAuthError):
    code = "reddit_credentials_missing"


class RedditAuthFailed(RedditAuthError):
    code = "reddit_auth_failed"


class RedditForbidden(RedditAccessError):
    code = "reddit_forbidden"


class RedditNotFound(RedditAccessError):
    code = "reddit_not_found"


class RedditRateLimited(RedditAccessError):
    code = "reddit_rate_limited"

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class RedditUnavailable(RedditAccessError):
    code = "reddit_unavailable"


def retry_after_seconds(headers: Mapping[str, str] | None) -> int | None:
    """Segundos de `Retry-After`, sin distinguir mayúsculas en el nombre."""
    for nombre, valor in (headers or {}).items():
        if nombre.lower() == "retry-after":
            try:
                return max(0, int(float(valor)))
            except ValueError:
                return None
    return None


def error_for_status(
    status: int,
    context: str,
    headers: Mapping[str, str] | None = None,
    forbidden_is_auth: bool = False,
) -> RedditAccessError:
    """
    Traduce un código HTTP distinto de 200 a su error tipado.

    `forbidden_is_auth` existe por el endpoint de token, donde un 403 no es
    un recurso vedado sino las credenciales rechazadas.
    """
    if status == 401 or (status == 403 and forbidden_is_auth):
        return RedditAuthFailed(f"Reddit rechazó las credenciales ({status}) en {context}")
    if status == 403:
        return RedditForbidden(f"Reddit denegó el acceso (403) a {context}")
    if status == 404:
        return RedditNotFound(f"{context} no existe o es privado (404)")
    if status == 429:
        segundos = retry_after_seconds(headers)
        return RedditRateLimited(
            f"Reddit limitó las peticiones (429) en {context}", segundos
        )
    if status >= 500:
        return RedditUnavailable(f"Reddit no está disponible ({status}) en {context}")
    return RedditUnavailable(f"Respuesta HTTP {status} inesperada de {context}")
