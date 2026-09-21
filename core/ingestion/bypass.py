"""
Módulo de Evasión y Bypass de Restricciones para Reddit Ingestion
=================================================================
Extraído y adaptado de yt-dlp (yt_dlp/extractor/reddit.py).

Proporciona:
1. Inyección de cookies de bypass de edad ('over18=1').
2. Inyección de cookie '_options' con 'pref_gated_sr_optin=True' para acceder
   a subreddits 'gated' sin requerir credenciales autenticadas.
3. Gestión y establecimiento del cookie anónimo 'loid' simulando la inicialización
   de sesión nativa de Reddit (old.reddit.com / shreddit).
4. Generación de cabeceras HTTP realistas para evasión de detección de bots.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)

@dataclass
class RedditBypassConfig:
    """Configuración de parámetros para evasión y bypass de Reddit."""
    user_agent: str = DEFAULT_USER_AGENT
    enable_over18: bool = True
    enable_gated_optin: bool = True
    custom_loid: Optional[str] = None
    extra_headers: Dict[str, str] = field(default_factory=dict)


class RedditBypass:
    """
    Gestor de cabeceras y cookies para eludir restricciones de acceso público
    a endpoints .json de Reddit sin depender de API keys oficiales de pago.
    """

    def __init__(self, config: Optional[RedditBypassConfig] = None) -> None:
        self.config = config or RedditBypassConfig()

    def get_bypass_cookies(self) -> Dict[str, str]:
        """
        Retorna el diccionario de cookies esenciales para bypass.
        - over18=1: elude la pantalla de confirmación NSFW/18+.
        - _options={"pref_gated_sr_optin": true}: opt-in a subreddits restringidos/gated.
        - loid: identificador de sesión anónimo si está configurado.
        """
        cookies: Dict[str, str] = {}

        if self.config.enable_over18:
            cookies["over18"] = "1"

        if self.config.enable_gated_optin:
            options_dict = {"pref_gated_sr_optin": True}
            cookies["_options"] = urllib.parse.quote(json.dumps(options_dict))

        if self.config.custom_loid:
            cookies["loid"] = self.config.custom_loid

        return cookies

    def get_bypass_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        """
        Retorna las cabeceras HTTP de navegador necesarias para evitar bloqueos
        WAF/Cloudflare al realizar solicitudes directas a endpoints .json.
        """
        headers: Dict[str, str] = {
            "User-Agent": self.config.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
            "DNT": "1",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        if referer:
            headers["Referer"] = referer
        else:
            headers["Referer"] = "https://www.reddit.com/"

        headers.update(self.config.extra_headers)
        return headers

    def format_cookie_header(self) -> str:
        """Formatea las cookies como string para la cabecera 'Cookie' de HTTP."""
        cookies = self.get_bypass_cookies()
        return "; ".join(f"{k}={v}" for k, v in cookies.items())

    def build_endpoint_url(
        self,
        subreddit: str,
        listing: str = "hot",
        base_domain: str = "https://www.reddit.com"
    ) -> str:
        """
        Construye la URL al endpoint JSON público de un subreddit o recurso.
        Ej: https://www.reddit.com/r/technology/hot.json
        """
        clean_sub = subreddit.strip().removeprefix("r/").removeprefix("/")
        clean_listing = listing.strip().lower()
        return f"{base_domain.rstrip('/')}/r/{clean_sub}/{clean_listing}.json"

    def build_thread_endpoint_url(
        self,
        subreddit: str,
        post_id: str,
        base_domain: str = "https://www.reddit.com"
    ) -> str:
        """
        Construye la URL para obtener el JSON completo de un post y sus comentarios.
        Ej: https://www.reddit.com/r/technology/comments/1abc23.json
        """
        clean_sub = subreddit.strip().removeprefix("r/").removeprefix("/")
        clean_id = post_id.strip().removeprefix("t3_")
        return f"{base_domain.rstrip('/')}/r/{clean_sub}/comments/{clean_id}.json"
