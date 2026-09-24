"""
Acceso a Reddit por OAuth (lo que reutiliza el adaptador de Reddit)
==================================================================

- `auth`: token OAuth de la app y lectura del `.env`.
- `errors`: fallos tipados del acceso a Reddit.
- `user_agent`: el User-Agent que exige Reddit, sin suplantar navegadores.

El cliente de ingesta, el filtro de dolor, el normalizador y el paginador
de la pipeline antigua se retiraron con las demostraciones (D-C7).
"""

from .auth import RedditAuthError, RedditOAuth, load_dotenv

__all__ = ["RedditAuthError", "RedditOAuth", "load_dotenv"]
