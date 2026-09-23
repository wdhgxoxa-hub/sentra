"""
Autenticación OAuth2 contra Reddit
==================================

Reddit cerró el acceso anónimo a los endpoints `.json`: devuelven 403, o
redirigen a `/login/?reason=lor2` sirviendo HTML. La vía soportada para leer
sin fricción es una aplicación de tipo *script* (gratuita) y un token OAuth2.

Dos modos de concesión, según lo que se configure:

- `client_credentials` (solo aplicación): basta con `client_id` y
  `client_secret`. Suficiente para leer subreddits públicos.
- `password` (en nombre de un usuario): añade `username` y `password` del
  dueño de la app. Amplía los límites de cuota.

Configuración por entorno (ver `.env.example`):

    RIR_REDDIT_CLIENT_ID=...
    RIR_REDDIT_CLIENT_SECRET=...
    RIR_REDDIT_USERNAME=...        # opcional
    RIR_REDDIT_PASSWORD=...        # opcional
    RIR_REDDIT_USER_AGENT=...      # recomendado por Reddit: que te identifique

Las credenciales nunca se escriben en logs ni en la representación del objeto.
"""

from __future__ import annotations

import base64
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from typing import Any

from .errors import (
    RedditAuthError,
    RedditAuthFailed,
    RedditCredentialsMissing,
    RedditUnavailable,
    error_for_status,
)

__all__ = [
    "RedditAuthError",
    "RedditOAuth",
    "load_dotenv",
    "load_reddit_oauth",
]

logger = logging.getLogger(__name__)

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_DOMAIN = "https://oauth.reddit.com"

DEFAULT_USER_AGENT = "python:reddit-intelligence-radar:v0.5 (by /u/unknown)"

# Margen de seguridad para renovar antes de que el token expire de verdad.
EXPIRY_MARGIN_SECONDS = 60.0

TokenFetcher = Callable[[dict[str, str], dict[str, str]], Awaitable[dict[str, Any]]]


def load_dotenv(
    path: str | None = None,
    env: MutableMapping[str, str] | None = None,
) -> MutableMapping[str, str]:
    """
    Carga variables desde un archivo `.env` sin depender de python-dotenv.

    Las variables ya presentes en el entorno mandan: el archivo es una
    comodidad para desarrollo, no una forma de pisar la configuración real.
    Un archivo ausente no es un error.

    Args:
        path: ruta del archivo. Por defecto, `.env` en la raíz del proyecto.
        env: diccionario destino. Por defecto, `os.environ`.
    """
    import os
    from pathlib import Path

    if env is None:
        env = os.environ
    if path is None:
        path = str(Path(__file__).resolve().parents[2] / ".env")

    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError, PermissionError):
        return env

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        if key and key not in env:
            env[key] = value

    return env


def load_reddit_oauth(env_path: str | None = None) -> RedditOAuth | None:
    """
    Única vía para obtener las credenciales de Reddit.

    Lee el `.env` tal como está AHORA, en un diccionario propio: ni consulta
    ni escribe `os.environ`. Si se volcase allí, la primera lectura fijaría
    los valores para siempre (`load_dotenv` no pisa lo ya presente) y lo que
    se guarde después desde la interfaz no llegaría a ningún escaneo. El
    escaneo y «Probar conexión» pasan los dos por aquí, así que ven siempre
    las mismas credenciales.
    """
    return RedditOAuth.from_env(env=load_dotenv(env_path, env={}))


class RedditOAuth:
    """
    Gestor de token OAuth2 con renovación perezosa.

    El token se pide la primera vez que hace falta y se reutiliza hasta que
    está a punto de expirar.
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        username: str | None = None,
        password: str | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        token_fetcher: TokenFetcher | None = None,
    ) -> None:
        self.client_id = client_id
        self._client_secret = client_secret
        self.username = username
        self._password = password
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self._token_fetcher = token_fetcher

        self._access_token: str | None = None
        self._expires_at: float = 0.0

    # -- Construcción ------------------------------------------------------

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        token_fetcher: TokenFetcher | None = None,
    ) -> RedditOAuth | None:
        """
        Construye el gestor desde el entorno.

        Devuelve None si no hay credenciales, que es la señal para que el
        cliente siga operando en modo anónimo.
        """
        if env is None:
            import os

            env = os.environ

        client_id = env.get("RIR_REDDIT_CLIENT_ID")
        client_secret = env.get("RIR_REDDIT_CLIENT_SECRET")
        if not client_id or not client_secret:
            return None

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            username=env.get("RIR_REDDIT_USERNAME"),
            password=env.get("RIR_REDDIT_PASSWORD"),
            user_agent=env.get("RIR_REDDIT_USER_AGENT") or DEFAULT_USER_AGENT,
            token_fetcher=token_fetcher,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self._client_secret)

    def __repr__(self) -> str:
        """Representación deliberadamente sin secretos."""
        modo = "password" if self.username else "client_credentials"
        return (
            f"RedditOAuth(client_id={'***' if self.client_id else None}, "
            f"grant={modo}, configured={self.is_configured})"
        )

    # -- Token -------------------------------------------------------------

    def _grant_payload(self) -> dict[str, str]:
        if self.username and self._password:
            return {
                "grant_type": "password",
                "username": self.username,
                "password": self._password,
            }
        return {"grant_type": "client_credentials"}

    def _auth_headers(self) -> dict[str, str]:
        raw = f"{self.client_id}:{self._client_secret}".encode()
        return {
            "Authorization": "Basic " + base64.b64encode(raw).decode("ascii"),
            "User-Agent": self.user_agent,
        }

    async def get_token(self) -> str:
        """
        Devuelve un token válido, pidiéndolo solo si hace falta.

        Raises:
            RedditCredentialsMissing: si no hay client_id / client_secret.
            RedditAuthFailed: si Reddit rechaza las credenciales o no da token.
            RedditRateLimited, RedditUnavailable: si el endpoint de token no
                atiende (429, 5xx o red caída).
        """
        if not self.is_configured:
            raise RedditCredentialsMissing(
                "Faltan credenciales de Reddit: guarda el Client ID y el Client "
                "Secret en Configuración."
            )

        if self._access_token and time.monotonic() < self._expires_at:
            return self._access_token

        fetcher = self._token_fetcher or _fetch_token_over_https
        data = await fetcher(self._grant_payload(), self._auth_headers())

        token = (data or {}).get("access_token")
        if not token:
            # El cuerpo puede traer detalles del rechazo, pero nunca secretos.
            raise RedditAuthFailed(
                f"Reddit no devolvio access_token (respuesta: {sorted((data or {}).keys())})"
            )

        self._access_token = str(token)
        expires_in = float((data or {}).get("expires_in", 3600) or 0.0)
        self._expires_at = time.monotonic() + max(0.0, expires_in - EXPIRY_MARGIN_SECONDS)

        logger.info("Token de Reddit obtenido (expira en %.0fs)", expires_in)
        return self._access_token

    async def auth_headers(self) -> dict[str, str]:
        """Cabeceras listas para una petición autenticada."""
        return {
            "Authorization": f"bearer {await self.get_token()}",
            "User-Agent": self.user_agent,
        }


async def _fetch_token_over_https(
    payload: dict[str, str],
    headers: dict[str, str],
) -> dict[str, Any]:
    """Obtentor real de token. Se aísla aquí para poder inyectarlo en pruebas."""
    from curl_cffi.requests import AsyncSession

    try:
        async with AsyncSession() as session:
            response = await session.post(
                TOKEN_URL, data=payload, headers=headers, timeout=20
            )
    except OSError as exc:  # curl_cffi.RequestException hereda de OSError
        raise RedditUnavailable(f"Sin respuesta del endpoint de token: {exc}") from exc

    if response.status_code != 200:
        # En el endpoint de token, 401 y 403 significan lo mismo: Reddit
        # rechaza el client_id / client_secret.
        raise error_for_status(
            response.status_code,
            "el endpoint de token",
            headers=response.headers,
            forbidden_is_auth=True,
        )
    try:
        return dict(response.json())
    except ValueError as exc:
        raise RedditUnavailable("El endpoint de token no devolvió JSON") from exc
