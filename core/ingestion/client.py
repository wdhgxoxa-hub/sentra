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
import logging
import time
from typing import TYPE_CHECKING, Any

from curl_cffi.requests import AsyncSession

if TYPE_CHECKING:
    from curl_cffi.requests.session import ProxySpec

from .auth import OAUTH_DOMAIN, RedditOAuth
from .bypass import RedditBypass, RedditBypassConfig
from .errors import RedditCredentialsMissing, RedditUnavailable, error_for_status
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
        proxy: str | None = None,
        timeout_seconds: float = 15.0,
        rate_limit_delay: float = 1.0,
        bypass_config: RedditBypassConfig | None = None,
        pain_filter: PainPointFilter | None = None,
        paginator: RedditPaginator | None = None,
        oauth: RedditOAuth | None = None,
    ) -> None:
        self.impersonate_browser = impersonate_browser
        self.proxy = proxy
        self.timeout_seconds = timeout_seconds
        self.rate_limit_delay = rate_limit_delay

        # Solo se habla con oauth.reddit.com: sin credenciales, cada listado
        # falla con RedditCredentialsMissing antes de salir a la red.
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
    ) -> tuple[str, dict[str, str] | None]:
        """
        Resuelve la URL de la API OAuth y sus cabeceras.

        Solo existe la vía autenticada: `oauth.reddit.com/r/<sub>/<listing>`
        con el token bearer. Sin credenciales se falla aquí, antes de hacer
        ninguna petición. Ya no hay caída al endpoint público `.json` con
        cabeceras de navegador: Reddit lo tiene cerrado, y fingir un
        navegador convertía esa negativa en un «0 resultados» silencioso.
        """
        if self.oauth is None or not self.oauth.is_configured:
            raise RedditCredentialsMissing(
                "Faltan credenciales de Reddit: guarda el Client ID y el Client "
                "Secret en Configuración."
            )
        url = f"{OAUTH_DOMAIN}/r/{clean_sub}/{listing.strip().lower()}"
        return url, await self.oauth.auth_headers()

    async def _execute_request(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retry_count: int = 3,
        context: str = "Reddit",
    ) -> Any:
        """
        Ejecuta un GET y devuelve el JSON, o lanza el error tipado que toque.

        Solo se reintenta lo que es un corte de red: un código HTTP es una
        respuesta de Reddit y se traduce tal cual (401, 403, 404, 429 con sus
        segundos de espera, 5xx). Un 200 que no es JSON tampoco es una página
        vacía: es Reddit sirviendo otra cosa, y se informa como no disponible.

        `headers` son las de la petición (el token OAuth). No se añaden
        cabeceras ni cookies de navegador.
        """
        proxies: ProxySpec | None = (
            {"http": self.proxy, "https": self.proxy} if self.proxy else None
        )

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
                        headers=dict(headers or {}),
                        timeout=self.timeout_seconds
                    )
            except OSError as exc:  # curl_cffi.RequestException hereda de OSError
                logger.warning("Sin respuesta de %s (intento %d): %s", url, attempt, exc)
                if attempt < retry_count:
                    await asyncio.sleep(1.5 * attempt)
                    continue
                raise RedditUnavailable(
                    f"Reddit no respondió tras {retry_count} intentos: {exc}"
                ) from exc

            if response.status_code != 200:
                raise error_for_status(
                    response.status_code, context, headers=response.headers
                )
            try:
                return response.json()
            except ValueError as exc:
                raise RedditUnavailable(
                    f"Reddit respondió 200 sin JSON en {context}"
                ) from exc

        raise RedditUnavailable(f"Reddit no respondió en {context}")

    # ─── Métodos de Extracción de Alto Nivel ─────────────────────────

    def _build_clean_post(
        self,
        raw_p: dict[str, Any],
        clean_sub: str,
        filter_pain_only: bool,
    ) -> CleanPost | None:
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
        after: str | None = None,
        timeframe: str = "month",
        max_age_days: int | None = None,
        filter_pain_only: bool = False,
    ) -> tuple[list[CleanPost], str | None]:
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

        data = await self._execute_request(
            url, params=params, headers=auth_headers, context=f"r/{clean_sub}"
        )
        if not isinstance(data, dict):
            raise RedditUnavailable(f"r/{clean_sub} devolvió un JSON que no es un listado")

        raw_children, next_cursor = self.paginator.extract_children_and_after(data)
        if not raw_children:
            return [], None

        # Filtro de antigüedad temporal (Bellingcat)
        valid_raw, reached_cutoff = self.paginator.filter_by_recency(
            raw_children, max_age_days=max_age_days
        )

        posts: list[CleanPost] = []
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
        max_age_days: int | None = None,
        filter_pain_only: bool = False,
        after: str | None = None,
    ) -> list[CleanPost]:
        """
        Recorre hasta `max_pages` páginas siguiendo la cadena de cursores y
        devuelve los posts deduplicados.

        `after` permite arrancar el recorrido desde un cursor conocido. Para
        obtener también el cursor final, usar `fetch_subreddit_page`.
        """
        cursor: str | None = after
        collected_posts: list[CleanPost] = []

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
    ) -> list[CleanComment]:
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
        collected_comments: list[CleanComment] = []

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
    ) -> CleanPost | None:
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

        comments: list[CleanComment] = []
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
    ) -> list[UnifiedTimelineItem]:
        """
        Aplica el algoritmo de snscrape para generar una cronología unificada e interfoliada
        de publicaciones y comentarios del subreddit en orden temporal descendente.
        """
        posts = await self.fetch_subreddit_posts(subreddit, listing="new", limit_per_page=post_limit, max_pages=1)
        all_comments: list[CleanComment] = []

        # Extraer comentarios de los primeros posts
        for p in posts[:5]:
            comments = await self.fetch_thread_comments(subreddit, p.id, limit=max_comments_per_post)
            all_comments.extend(comments)

        timeline = list(self.normalizer.interleave_chronological(posts, all_comments))
        return timeline
