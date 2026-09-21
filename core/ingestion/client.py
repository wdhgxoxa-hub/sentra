"""
Cliente Central de Ingesta Asíncrona (Reddit Ingestion Client)
=============================================================
Construido sobre:
1. Arquitectura base de crawlee-python (SessionPool y CurlImpersonateHttpClient).
2. Bypass de cookies y headers de yt-dlp (bypass.py).
3. Paginación directa cursor-based de Bellingcat (pagination.py).
4. Middleware de filtrado léxico rápido de reddit-painpointer (filters.py).
5. Normalización, saneamiento y Markdown estructurado de reddit-find (normalizer.py).
6. Interfoliado cronológico inverso unificado de snscrape (normalizer.py).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from curl_cffi.requests import AsyncSession

from .auth import OAUTH_DOMAIN, RedditOAuth
from .bypass import RedditBypass, RedditBypassConfig
from .filters import FilterResult, PainPointFilter
from .normalizer import CleanComment, CleanPost, RedditNormalizer, UnifiedTimelineItem
from .pagination import RedditPaginator

logger = logging.getLogger(__name__)


class RedditIngestionClient:
    """
    Cliente industrial unificado para la extracción masiva, normalización y filtrado
    de señales de Reddit sin requerir credenciales de API de pago.
    """

    def __init__(
        self,
        impersonate_browser: str = "chrome124",
        proxy: Optional[str] = None,
        timeout_seconds: float = 15.0,
        rate_limit_delay: float = 1.0,
        bypass_config: Optional[RedditBypassConfig] = None,
        pain_filter: Optional[PainPointFilter] = None,
        paginator: Optional[RedditPaginator] = None,
        oauth: Optional[RedditOAuth] = None,
    ) -> None:
        self.impersonate_browser = impersonate_browser
        self.proxy = proxy
        self.timeout_seconds = timeout_seconds
        self.rate_limit_delay = rate_limit_delay

        # Con credenciales se habla con oauth.reddit.com; sin ellas se
        # intenta el endpoint publico .json, que Reddit ya restringe.
        self.oauth = oauth

        # Componentes modulares
        self.bypass = RedditBypass(bypass_config)
        self.filter = pain_filter or PainPointFilter()
        self.paginator = paginator or RedditPaginator()
        self.normalizer = RedditNormalizer()

        self._last_request_time = 0.0

    async def _throttle(self) -> None:
        """Aplica una pausa de cortesía para evitar ráfagas excesivas contra el servidor."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.monotonic()

    @property
    def is_authenticated(self) -> bool:
        """True si hay credenciales OAuth utilizables."""
        return bool(self.oauth and self.oauth.is_configured)

    async def _endpoint_and_headers(
        self,
        clean_sub: str,
        listing: str,
    ) -> Tuple[str, Optional[Dict[str, str]]]:
        """
        Resuelve a qué dominio hay que pedir y con qué cabeceras.

        Autenticado: `oauth.reddit.com/r/<sub>/<listing>`, sin sufijo `.json`,
        con el token bearer. Anónimo: el endpoint público `.json`.
        """
        if self.is_authenticated:
            url = f"{OAUTH_DOMAIN}/r/{clean_sub}/{listing.strip().lower()}"
            return url, await self.oauth.auth_headers()

        return self.bypass.build_endpoint_url(clean_sub, listing), None

    async def _execute_request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        retry_count: int = 3
    ) -> Optional[Any]:
        """
        Ejecuta una solicitud HTTP GET asíncrona utilizando curl_cffi con TLS impersonation,
        inyección de cookies de bypass (over18, pref_gated_sr_optin) y reintentos ante 429.

        `headers` permite añadir cabeceras propias de la petición (por ejemplo,
        el token OAuth), que prevalecen sobre las del bypass.
        """
        request_headers = self.bypass.get_bypass_headers()
        if headers:
            request_headers.update(headers)
        headers = request_headers
        cookies = self.bypass.get_bypass_cookies()
        proxies = {"http": self.proxy, "https": self.proxy} if self.proxy else None

        for attempt in range(1, retry_count + 1):
            await self._throttle()
            try:
                async with AsyncSession(
                    impersonate=self.impersonate_browser,
                    proxies=proxies
                ) as session:
                    response = await session.get(
                        url,
                        params=params,
                        headers=headers,
                        cookies=cookies,
                        timeout=self.timeout_seconds
                    )

                    if response.status_code == 200:
                        try:
                            return response.json()
                        except Exception as e:
                            logger.error(f"Error parseando JSON de {url}: {e}")
                            return None

                    elif response.status_code == 429:
                        wait_time = self.paginator.backoff_base_seconds * (2 ** (attempt - 1))
                        logger.warning(
                            f"HTTP 429 (Rate Limit) en {url}. Reintento {attempt}/{retry_count} "
                            f"esperando {wait_time:.1f}s..."
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    elif response.status_code in (403, 404):
                        logger.warning(f"Respuesta HTTP {response.status_code} para {url}")
                        return None
                    else:
                        logger.warning(f"HTTP {response.status_code} inesperado en {url}")

            except Exception as exc:
                logger.error(f"Excepción en petición a {url} (intento {attempt}): {exc}")
                if attempt < retry_count:
                    await asyncio.sleep(1.5 * attempt)
                else:
                    return None

        return None

    # ─── Métodos de Extracción de Alto Nivel ─────────────────────────

    def _build_clean_post(
        self,
        raw_p: Dict[str, Any],
        clean_sub: str,
        filter_pain_only: bool,
    ) -> Optional[CleanPost]:
        """
        Normaliza un registro crudo de Reddit en un `CleanPost`.

        Devuelve None si se pidió filtrar por dolor y el ítem no lo supera.
        """
        post_id = self.normalizer.normalize_id(raw_p.get("id", ""))
        title = (raw_p.get("title") or "").strip()
        selftext = self.normalizer.clean_text_body(raw_p.get("selftext"))
        author = raw_p.get("author", "[deleted]")

        combined_text = f"{title} {selftext}"
        filter_res: FilterResult = self.filter.evaluate(
            combined_text, author=author, require_pain_match=filter_pain_only
        )

        if filter_pain_only and not filter_res.passed:
            return None

        return CleanPost(
            id=post_id,
            subreddit=raw_p.get("subreddit", clean_sub),
            title=title,
            selftext=selftext,
            author=author if author else "[deleted]",
            score=raw_p.get("score", 0),
            upvote_ratio=raw_p.get("upvote_ratio", 0.0),
            num_comments=raw_p.get("num_comments", 0),
            created_utc=float(raw_p.get("created_utc", 0.0)),
            url=raw_p.get("url", ""),
            permalink=f"https://reddit.com{raw_p.get('permalink', '')}" if raw_p.get("permalink") else "",
            flair=raw_p.get("link_flair_text") or "",
            is_pain_signal=filter_res.is_pain_signal,
            matched_keywords=filter_res.matched_keywords
        )

    async def fetch_subreddit_page(
        self,
        subreddit: str,
        listing: str = "hot",
        limit: int = 25,
        after: Optional[str] = None,
        timeframe: str = "month",
        max_age_days: Optional[int] = None,
        filter_pain_only: bool = False,
    ) -> Tuple[List[CleanPost], Optional[str]]:
        """
        Extrae UNA página y devuelve explícitamente el cursor de la siguiente.

        Es la primitiva de paginación: acepta el cursor `after` entrante y
        propaga hacia fuera el que devuelve Reddit, de modo que un consumidor
        externo (por ejemplo el grafo de orquestación) pueda reanudar donde
        lo dejó en lugar de volver a empezar.

        Devuelve `(posts, next_cursor)`. Un `next_cursor` a None significa
        que no hay más que recorrer, ya sea porque Reddit no dio cursor,
        porque la respuesta vino vacía o porque se alcanzó el corte temporal.
        """
        clean_sub = subreddit.strip().removeprefix("r/").removeprefix("/")
        url, auth_headers = await self._endpoint_and_headers(clean_sub, listing)

        params = self.paginator.build_page_params(
            listing=listing,
            limit=limit,
            after=after,
            timeframe=timeframe
        )

        data = await self._execute_request(url, params=params, headers=auth_headers)
        if not data or not isinstance(data, dict):
            return [], None

        raw_children, next_cursor = self.paginator.extract_children_and_after(data)
        if not raw_children:
            return [], None

        # Filtro de antigüedad temporal (Bellingcat)
        valid_raw, reached_cutoff = self.paginator.filter_by_recency(
            raw_children, max_age_days=max_age_days
        )

        posts: List[CleanPost] = []
        for raw_p in valid_raw:
            clean_post = self._build_clean_post(raw_p, clean_sub, filter_pain_only)
            if clean_post is not None:
                posts.append(clean_post)

        # En un listado ordenado por fecha, pasado el corte no queda nada útil
        # por delante: se corta la cadena de cursores.
        if reached_cutoff:
            next_cursor = None

        return posts, next_cursor

    async def fetch_subreddit_posts(
        self,
        subreddit: str,
        listing: str = "hot",
        limit_per_page: int = 25,
        max_pages: int = 1,
        timeframe: str = "month",
        max_age_days: Optional[int] = None,
        filter_pain_only: bool = False,
        after: Optional[str] = None,
    ) -> List[CleanPost]:
        """
        Recorre hasta `max_pages` páginas siguiendo la cadena de cursores y
        devuelve los posts deduplicados.

        `after` permite arrancar el recorrido desde un cursor conocido. Para
        obtener también el cursor final, usar `fetch_subreddit_page`.
        """
        cursor: Optional[str] = after
        collected_posts: List[CleanPost] = []

        for _ in range(max_pages):
            posts, cursor = await self.fetch_subreddit_page(
                subreddit=subreddit,
                listing=listing,
                limit=limit_per_page,
                after=cursor,
                timeframe=timeframe,
                max_age_days=max_age_days,
                filter_pain_only=filter_pain_only,
            )
            collected_posts.extend(posts)

            if not cursor:
                break

        return self.normalizer.deduplicate_posts(collected_posts)

    async def fetch_thread_comments(
        self,
        subreddit: str,
        post_id: str,
        limit: int = 50,
        filter_pain_only: bool = False
    ) -> List[CleanComment]:
        """
        Extrae comentarios de un hilo específico ordenados por puntuación ('top').
        """
        clean_sub = subreddit.strip().removeprefix("r/").removeprefix("/")
        clean_id = self.normalizer.normalize_id(post_id)
        url = self.bypass.build_thread_endpoint_url(clean_sub, clean_id)
        params = {"limit": limit, "sort": "top"}

        data = await self._execute_request(url, params=params)
        if not data or not isinstance(data, list) or len(data) < 2:
            return []

        # data[0] es el post, data[1] es el árbol de comentarios
        comments_data = data[1].get("data", {}).get("children", [])
        collected_comments: List[CleanComment] = []

        for child in comments_data:
            if child.get("kind") != "t1":
                continue
            c_data = child.get("data", {})
            body = self.normalizer.clean_text_body(c_data.get("body"))
            if not body:
                continue

            author = c_data.get("author", "[deleted]")
            filter_res: FilterResult = self.filter.evaluate(
                body, author=author, require_pain_match=filter_pain_only
            )

            if filter_pain_only and not filter_res.passed:
                continue

            comm_id = self.normalizer.normalize_id(c_data.get("id", ""))
            clean_comment = CleanComment(
                id=comm_id,
                post_id=clean_id,
                author=author if author else "[deleted]",
                body=body,
                score=c_data.get("score", 0),
                created_utc=float(c_data.get("created_utc", 0.0)),
                permalink=f"https://reddit.com{c_data.get('permalink', '')}" if c_data.get("permalink") else "",
                parent_id=c_data.get("parent_id"),
                is_pain_signal=filter_res.is_pain_signal,
                matched_keywords=filter_res.matched_keywords
            )
            collected_comments.append(clean_comment)

        return sorted(collected_comments, key=lambda c: c.score, reverse=True)

    async def fetch_full_thread(
        self,
        subreddit: str,
        post_id: str,
        comment_limit: int = 50,
        filter_comments_pain_only: bool = False
    ) -> Optional[CleanPost]:
        """
        Extrae un post completo junto con sus comentarios en una única estructura `CleanPost`.
        """
        clean_sub = subreddit.strip().removeprefix("r/").removeprefix("/")
        clean_id = self.normalizer.normalize_id(post_id)
        url = self.bypass.build_thread_endpoint_url(clean_sub, clean_id)
        params = {"limit": comment_limit, "sort": "top"}

        data = await self._execute_request(url, params=params)
        if not data or not isinstance(data, list) or len(data) < 1:
            return None

        # Post data
        post_listing = data[0].get("data", {}).get("children", [])
        if not post_listing:
            return None

        p_data = post_listing[0].get("data", {})
        title = (p_data.get("title") or "").strip()
        selftext = self.normalizer.clean_text_body(p_data.get("selftext"))
        author = p_data.get("author", "[deleted]")

        filter_res = self.filter.evaluate(f"{title} {selftext}", author=author, require_pain_match=False)

        comments: List[CleanComment] = []
        if len(data) >= 2:
            comments_data = data[1].get("data", {}).get("children", [])
            for child in comments_data:
                if child.get("kind") != "t1":
                    continue
                c_data = child.get("data", {})
                body = self.normalizer.clean_text_body(c_data.get("body"))
                if not body:
                    continue
                c_author = c_data.get("author", "[deleted]")
                c_filter = self.filter.evaluate(body, author=c_author, require_pain_match=filter_comments_pain_only)
                if filter_comments_pain_only and not c_filter.passed:
                    continue

                comments.append(
                    CleanComment(
                        id=self.normalizer.normalize_id(c_data.get("id", "")),
                        post_id=clean_id,
                        author=c_author if c_author else "[deleted]",
                        body=body,
                        score=c_data.get("score", 0),
                        created_utc=float(c_data.get("created_utc", 0.0)),
                        permalink=f"https://reddit.com{c_data.get('permalink', '')}" if c_data.get("permalink") else "",
                        parent_id=c_data.get("parent_id"),
                        is_pain_signal=c_filter.is_pain_signal,
                        matched_keywords=c_filter.matched_keywords
                    )
                )

        clean_post = CleanPost(
            id=clean_id,
            subreddit=p_data.get("subreddit", clean_sub),
            title=title,
            selftext=selftext,
            author=author if author else "[deleted]",
            score=p_data.get("score", 0),
            upvote_ratio=p_data.get("upvote_ratio", 0.0),
            num_comments=p_data.get("num_comments", 0),
            created_utc=float(p_data.get("created_utc", 0.0)),
            url=p_data.get("url", ""),
            permalink=f"https://reddit.com{p_data.get('permalink', '')}" if p_data.get("permalink") else "",
            flair=p_data.get("link_flair_text") or "",
            comments=sorted(comments, key=lambda c: c.score, reverse=True),
            is_pain_signal=filter_res.is_pain_signal,
            matched_keywords=filter_res.matched_keywords
        )

        return clean_post

    async def get_unified_timeline(
        self,
        subreddit: str,
        post_limit: int = 25,
        max_comments_per_post: int = 5
    ) -> List[UnifiedTimelineItem]:
        """
        Aplica el algoritmo de snscrape para generar una cronología unificada e interfoliada
        de publicaciones y comentarios del subreddit en orden temporal descendente.
        """
        posts = await self.fetch_subreddit_posts(subreddit, listing="new", limit_per_page=post_limit, max_pages=1)
        all_comments: List[CleanComment] = []

        # Extraer comentarios de los primeros posts
        for p in posts[:5]:
            comments = await self.fetch_thread_comments(subreddit, p.id, limit=max_comments_per_post)
            all_comments.extend(comments)

        timeline = list(self.normalizer.interleave_chronological(posts, all_comments))
        return timeline
