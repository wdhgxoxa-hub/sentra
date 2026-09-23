"""
Fuente: YouTube (Data API v3 oficial)
=====================================

search.list (100 unidades) encuentra vídeos del tema en la ventana; de los
primeros, commentThreads.list (1 unidad) trae los comentarios, que es donde
está la queja. La cuota se cuenta en unidades con el presupuesto de D-M4
(2.000 por escaneo); una cuota diaria agotada (quotaExceeded) para la
fuente sin reintentar.

- La clave (RIR_YOUTUBE_API_KEY) va en la URL como `key=`; el filtro de
  core/sources/http.py la tapa en el log.
- Políticas de la API: los datos se refrescan o se borran en 30 días
  (`retention_days`; la purga corre al guardar cada escaneo).
- D-M7/R9: ni el nombre del canal ni el del autor; el autor, solo como hash
  de su id de canal. URLs por id de vídeo y de comentario.
"""

from __future__ import annotations

import html
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx

from core.evidence.model import Engagement, EvidenceItem, SearchQuery

from .base import CostModel, CredentialField, ProbeResult, SourceAdapter
from .budget import SourceBudget
from .errors import (
    SourceAuthFailed,
    SourceError,
    SourceForbidden,
    SourceNotFound,
    SourceRateLimited,
)
from .profile import term_pairs

API = "https://www.googleapis.com/youtube/v3"
WATCH = "https://www.youtube.com/watch?v={video}"

SEARCH_UNITS = 100
LIST_UNITS = 1
#: D-M4: unidades de cuota por escaneo.
SCAN_MAX_UNITS = 2000
#: Vídeos por búsqueda y vídeos de los que se leen comentarios.
MAX_RESULTS = 25
VIDEOS_WITH_COMMENTS = 5
COMMENTS_PER_VIDEO = 50
#: La cuota diaria se repone a medianoche (hora del Pacífico): no se reintenta.
QUOTA_RESET_S = 3600.0

_CUOTA = frozenset({"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded",
                    "userRateLimitExceeded"})
_CLAVE = frozenset({"keyInvalid", "keyExpired", "accessNotConfigured", "forbidden"})


class YouTubeSource(SourceAdapter):
    id = "youtube"
    display_name = "YouTube"
    terms_url = "https://developers.google.com/youtube/terms/api-services-terms-of-service"
    commercial_use_allowed = True
    requires_credentials = True
    credential_fields = (CredentialField(name="api_key", env_var="RIR_YOUTUBE_API_KEY"),)
    cost_model = CostModel(
        unit="quota_unit", per_request=LIST_UNITS,
        note="10.000 unidades/día; búsqueda 100, comentarios 1; datos borrados a los 30 días",
    )
    retention_days = 30

    @classmethod
    def default_budget(cls) -> SourceBudget:
        return SourceBudget(source=cls.id, max_units=SCAN_MAX_UNITS)

    async def _api(self, metodo: str, params: dict[str, Any], unidades: int) -> Any:
        return await self._get(f"{API}/{metodo}", units=unidades,
                               params={**params, "key": self.credentials.get("api_key", "")})

    def _error_de(self, respuesta: httpx.Response) -> SourceError:
        try:
            cuerpo = (respuesta.json() or {}).get("error") or {}
        except ValueError:
            return super()._error_de(respuesta)
        razones = {str(e.get("reason")) for e in cuerpo.get("errors") or [] if isinstance(e, dict)}
        detalle = f"HTTP {respuesta.status_code}: {', '.join(sorted(razones)) or 'sin motivo'}"
        if razones & _CUOTA:
            return SourceRateLimited(self.id, detalle, retry_after=QUOTA_RESET_S)
        if razones & _CLAVE or respuesta.status_code == 400 and "keyInvalid" in razones:
            return SourceAuthFailed(self.id, detalle)
        if "commentsDisabled" in razones:
            return SourceForbidden(self.id, detalle)
        if razones & {"videoNotFound", "notFound"}:
            return SourceNotFound(self.id, detalle)
        return super()._error_de(respuesta)

    async def probe(self) -> ProbeResult:
        try:
            await self._api("videos", {"part": "id", "chart": "mostPopular", "maxResults": 1},
                            LIST_UNITS)
        except SourceError as exc:
            return self._probe_error(exc)
        return self._probe_ok("YouTube Data API respondió (1 unidad)")

    async def search(self, query: SearchQuery) -> AsyncIterator[EvidenceItem]:
        vistos: set[str] = set()
        unidades = self.budget.max_units or SCAN_MAX_UNITS
        busquedas = max(1, int(unidades // (SEARCH_UNITS + VIDEOS_WITH_COMMENTS)))
        for palabra, frase in term_pairs(query, limit=busquedas):
            params: dict[str, Any] = {
                "part": "snippet", "type": "video", "maxResults": MAX_RESULTS,
                "order": "relevance", "q": " ".join(t for t in (palabra, frase) if t),
            }
            if query.since is not None:
                params["publishedAfter"] = query.since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            datos = await self._api("search", params, SEARCH_UNITS)
            videos = [v for v in datos.get("items") or [] if (v.get("id") or {}).get("videoId")]
            for n, video in enumerate(videos):
                item = self._video(video)
                if item is None or item.id in vistos:
                    continue
                vistos.add(item.id)
                yield item
                if n < VIDEOS_WITH_COMMENTS:
                    async for comentario in self._comentarios(video["id"]["videoId"]):
                        if comentario.id not in vistos:
                            vistos.add(comentario.id)
                            yield comentario

    async def _comentarios(self, video_id: str) -> AsyncIterator[EvidenceItem]:
        try:
            datos = await self._api("commentThreads", {
                "part": "snippet", "videoId": video_id, "maxResults": COMMENTS_PER_VIDEO,
                "order": "relevance", "textFormat": "plainText"}, LIST_UNITS)
        except (SourceForbidden, SourceNotFound):
            return  # comentarios desactivados o vídeo retirado: se sigue con el resto
        for hilo in datos.get("items") or []:
            item = self._comentario(hilo, video_id)
            if item is not None:
                yield item

    def _video(self, video: dict[str, Any]) -> EvidenceItem | None:
        video_id = video["id"]["videoId"]
        snippet = video.get("snippet") or {}
        titulo = html.unescape(str(snippet.get("title") or "")).strip()
        descripcion = html.unescape(str(snippet.get("description") or "")).strip()
        publicado = snippet.get("publishedAt")
        if not publicado or not (titulo or descripcion):
            return None
        return self._item(
            nativo=video_id, community="YouTube", kind="post", title=titulo or None,
            text=descripcion or titulo, url=WATCH.format(video=video_id),
            author=snippet.get("channelId"), created_at=datetime.fromisoformat(str(publicado)),
        )

    def _comentario(self, hilo: dict[str, Any], video_id: str) -> EvidenceItem | None:
        snippet = hilo.get("snippet") or {}
        raiz = snippet.get("topLevelComment") or {}
        datos = raiz.get("snippet") or {}
        texto = str(datos.get("textOriginal") or "").strip()
        publicado = datos.get("publishedAt")
        if not raiz.get("id") or not texto or not publicado:
            return None
        return self._item(
            nativo=str(raiz["id"]), community="YouTube", kind="comment", text=texto,
            url=f"{WATCH.format(video=video_id)}&lc={raiz['id']}",
            author=(datos.get("authorChannelId") or {}).get("value"),
            created_at=datetime.fromisoformat(str(publicado)), thread=video_id,
            engagement=Engagement(reactions=datos.get("likeCount"),
                                  replies=snippet.get("totalReplyCount")),
        )
