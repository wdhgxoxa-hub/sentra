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
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional

logger = logging.getLogger(__name__)

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_DOMAIN = "https://oauth.reddit.com"

DEFAULT_USER_AGENT = "python:reddit-intelligence-radar:v0.5 (by /u/unknown)"

# Margen de seguridad para renovar antes de que el token expire de verdad.
EXPIRY_MARGIN_SECONDS = 60.0

TokenFetcher = Callable[[Dict[str, str], Dict[str, str]], Awaitable[Dict[str, Any]]]


class RedditAuthError(RuntimeError):
    """No se pudo obtener un token de acceso válido."""


def load_dotenv(
    path: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
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


class RedditOAuth:
    """
    Gestor de token OAuth2 con renovación perezosa.

    El token se pide la primera vez que hace falta y se reutiliza hasta que
    está a punto de expirar.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        user_agent: str = DEFAULT_USER_AGENT,
        token_fetcher: Optional[TokenFetcher] = None,
    ) -> None:
        self.client_id = client_id
        self._client_secret = client_secret
        self.username = username
        self._password = password
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self._token_fetcher = token_fetcher

        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0

    # -- Construcción ------------------------------------------------------

    @classmethod
    def from_env(
        cls,
        env: Optional[Mapping[str, str]] = None,
        token_fetcher: Optional[TokenFetcher] = None,
    ) -> Optional["RedditOAuth"]:
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

    def _grant_payload(self) -> Dict[str, str]:
        if self.username and self._password:
            return {
                "grant_type": "password",
                "username": self.username,
                "password": self._password,
            }
        return {"grant_type": "client_credentials"}

    def _auth_headers(self) -> Dict[str, str]:
        raw = f"{self.client_id}:{self._client_secret}".encode("utf-8")
        return {
            "Authorization": "Basic " + base64.b64encode(raw).decode("ascii"),
            "User-Agent": self.user_agent,
        }

    async def get_token(self) -> str:
        """
        Devuelve un token válido, pidiéndolo solo si hace falta.

        Raises:
            RedditAuthError: si faltan credenciales o Reddit no devuelve token.
        """
        if not self.is_configured:
            raise RedditAuthError(
                "Faltan credenciales de Reddit. Define RIR_REDDIT_CLIENT_ID y "
                "RIR_REDDIT_CLIENT_SECRET (ver .env.example) o usa el cliente "
                "en modo anonimo."
            )

        if self._access_token and time.monotonic() < self._expires_at:
            return self._access_token

        fetcher = self._token_fetcher or _fetch_token_over_https
        try:
            data = await fetcher(self._grant_payload(), self._auth_headers())
        except Exception as exc:
            raise RedditAuthError(f"Fallo pidiendo el token: {exc}") from exc

        token = (data or {}).get("access_token")
        if not token:
            # El cuerpo puede traer detalles del rechazo, pero nunca secretos.
            raise RedditAuthError(
                f"Reddit no devolvio access_token (respuesta: {sorted((data or {}).keys())})"
            )

        self._access_token = str(token)
        expires_in = float((data or {}).get("expires_in", 3600) or 0.0)
        self._expires_at = time.monotonic() + max(0.0, expires_in - EXPIRY_MARGIN_SECONDS)

        logger.info("Token de Reddit obtenido (expira en %.0fs)", expires_in)
        return self._access_token

    async def auth_headers(self) -> Dict[str, str]:
        """Cabeceras listas para una petición autenticada."""
        return {
            "Authorization": f"bearer {await self.get_token()}",
            "User-Agent": self.user_agent,
        }


async def _fetch_token_over_https(
    payload: Dict[str, str],
    headers: Dict[str, str],
) -> Dict[str, Any]:
    """Obtentor real de token. Se aísla aquí para poder inyectarlo en pruebas."""
    from curl_cffi.requests import AsyncSession

    async with AsyncSession() as session:
        response = await session.post(
            TOKEN_URL, data=payload, headers=headers, timeout=20
        )
        if response.status_code != 200:
            raise RedditAuthError(
                f"HTTP {response.status_code} al pedir el token de acceso"
            )
        return response.json()
