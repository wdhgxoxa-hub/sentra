"""
Fuente 6: YouTube (Data API v3 oficial)
=======================================

Dobles con la forma documentada (developers.google.com/youtube/v3/docs):
- search.list (100 unidades): items[].id.videoId y snippet {publishedAt,
  channelId, title, description}.
- videos.list?part=statistics (1 unidad por hasta 50 ids): items[] {id,
  statistics {commentCount}}.
- commentThreads.list (1 unidad): items[].snippet.topLevelComment {id,
  snippet {textOriginal, authorChannelId.value, likeCount, publishedAt}} y
  snippet.totalReplyCount. Con los comentarios desactivados: 403
  commentsDisabled, que no para la fuente.
- Errores de Google: {"error": {"code", "message", "errors": [{"reason"}]}};
  quotaExceeded = cuota diaria agotada.

Reglas: solo comentarios; el vídeo (título y descripción, casi siempre
promoción: 103 de 115 piezas en el escaneo de facturación) no es evidencia,
su título va como contexto del comentario. Se leen los comentarios de los
vídeos con más comentarios. Cuota en unidades con el presupuesto de D-M4 (2.000 por escaneo);
la clave (RIR_YOUTUBE_API_KEY) va en la URL y el log la tapa; los datos se
refrescan o borran en 30 días (políticas de la API). D-M7: ni nombre de
canal ni de autor; URLs por id de vídeo y de comentario. Contenido e ids
inventados (R8).
"""

import unittest
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx

from core.evidence.model import SearchQuery
from core.sources.errors import SourceAuthFailed, SourceRateLimited
from core.sources.youtube import YouTubeSource

SAL = "c7" * 32
CLAVE = {"api_key": "AIza-clave-inventada"}
VIDEO = {"kind": "youtube#searchResult", "id": {"kind": "youtube#video", "videoId": "vidInvent01"},
         "snippet": {"publishedAt": "2026-05-10T09:00:00Z", "channelId": "UCcanalInventado",
                     "title": "Why is invoicing still so painful?",
                     "description": "I tried 5 tools and none exports properly.",
                     "channelTitle": "Canal Inventado"}}
HILO = {"kind": "youtube#commentThread", "id": "hiloInvent01", "snippet": {
    "videoId": "vidInvent01", "totalReplyCount": 3,
    "topLevelComment": {"id": "comInvent01", "snippet": {
        "textOriginal": "Same here, I would pay for a tool that just works.",
        "textDisplay": "Same here, I would pay for a tool that just works.",
        "authorDisplayName": "@autora-inventada",
        "authorChannelId": {"value": "UCautoraInventada"},
        "likeCount": 8, "publishedAt": "2026-05-11T10:00:00Z"}}}}


def error_google(estado, razon):
    return httpx.Response(estado, json={"error": {"code": estado, "message": "inventado",
                                                  "errors": [{"reason": razon}]}})


def api(busqueda=None, hilos=None, peticiones=None, estadisticas=None):
    def manejador(peticion):
        if peticiones is not None:
            peticiones.append(peticion)
        if peticion.url.path.endswith("/search"):
            return busqueda or httpx.Response(200, json={"items": [VIDEO]})
        if peticion.url.path.endswith("/commentThreads"):
            return hilos or httpx.Response(200, json={"items": [HILO]})
        if peticion.url.path.endswith("/videos") and "statistics" in str(peticion.url):
            return estadisticas or httpx.Response(200, json={"items": [
                {"id": "vidInvent01", "statistics": {"commentCount": "12"}}]})
        return httpx.Response(200, json={"items": [{"id": "x"}]})
    return manejador


def fuente(manejador, budget=None):
    return YouTubeSource(http=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
                         budget=budget or YouTubeSource.default_budget(), credentials=CLAVE,
                         author_salt=SAL)


async def todos(generador):
    return [x async for x in generador]


class TestDeclaracion(unittest.TestCase):
    def test_clave_unidades_y_retencion(self):
        self.assertEqual(YouTubeSource.id, "youtube")
        self.assertTrue(YouTubeSource.requires_credentials)
        [clave] = YouTubeSource.credential_fields
        self.assertEqual((clave.name, clave.env_var, clave.secret, clave.required),
                         ("api_key", "RIR_YOUTUBE_API_KEY", True, True))
        self.assertEqual(YouTubeSource.cost_model.unit, "quota_unit")
        self.assertEqual(YouTubeSource.default_budget().max_units, 2000)
        self.assertEqual(YouTubeSource.retention_days, 30)


class TestBusqueda(unittest.IsolatedAsyncioTestCase):
    async def test_solo_trae_comentarios_cobrando_unidades(self):
        peticiones: list[httpx.Request] = []
        adaptador = fuente(api(peticiones=peticiones))
        consulta = SearchQuery(keywords=["invoice"], since=datetime(2026, 1, 1, tzinfo=UTC))
        items = await todos(adaptador.search(consulta))
        busqueda = parse_qs(urlparse(str(peticiones[0].url)).query)
        self.assertEqual(urlparse(str(peticiones[0].url)).path, "/youtube/v3/search")
        self.assertEqual((busqueda["part"], busqueda["type"]), (["snippet"], ["video"]))
        self.assertEqual(busqueda["publishedAfter"], ["2026-01-01T00:00:00Z"])
        self.assertEqual(busqueda["key"], ["AIza-clave-inventada"])
        estadisticas = parse_qs(urlparse(str(peticiones[1].url)).query)
        self.assertEqual((estadisticas["part"], estadisticas["id"]), (["statistics"], ["vidInvent01"]))
        hilos = parse_qs(urlparse(str(peticiones[2].url)).query)
        self.assertEqual(hilos["videoId"], ["vidInvent01"])
        self.assertEqual([i.kind for i in items], ["comment"], "el vídeo no es evidencia")
        self.assertEqual(adaptador.budget.spent_units, 102)

    async def test_lee_los_videos_con_mas_comentarios(self):
        from unittest import mock

        from core.sources import youtube

        videos = [{**VIDEO, "id": {"kind": "youtube#video", "videoId": v}} for v in ("vidPocos", "vidMuchos", "vidNada")]
        peticiones: list[httpx.Request] = []
        manejador = api(peticiones=peticiones, busqueda=httpx.Response(200, json={"items": videos}),
                        estadisticas=httpx.Response(200, json={"items": [
                            {"id": "vidPocos", "statistics": {"commentCount": "5"}},
                            {"id": "vidMuchos", "statistics": {"commentCount": "50"}},
                            {"id": "vidNada", "statistics": {"commentCount": "0"}}]}))
        with mock.patch.object(youtube, "VIDEOS_WITH_COMMENTS", 1):
            await todos(fuente(manejador).search(SearchQuery(keywords=["invoice"])))
        leidos = [parse_qs(urlparse(str(p.url)).query)["videoId"][0] for p in peticiones
                  if p.url.path.endswith("/commentThreads")]
        self.assertEqual(leidos, ["vidMuchos"])

    async def test_el_presupuesto_por_defecto_alcanza_para_las_peticiones_planeadas(self):
        from core.sources import youtube

        presupuesto = YouTubeSource.default_budget()
        assert presupuesto.max_units is not None
        por_busqueda = 2 + youtube.VIDEOS_WITH_COMMENTS
        busquedas = int(presupuesto.max_units // (youtube.SEARCH_UNITS + 1 + youtube.VIDEOS_WITH_COMMENTS))
        self.assertGreaterEqual(presupuesto.max_requests, busquedas * por_busqueda)

    async def test_comentario_sin_nombres_y_con_urls_por_id(self):
        [comentario] = await todos(fuente(api()).search(SearchQuery(keywords=["invoice"])))
        self.assertEqual(comentario.native_metrics["video_title"], "Why is invoicing still so painful?")
        self.assertIsNone(comentario.title, "el título del vídeo es contexto, no la pieza")
        self.assertEqual(comentario.id, "youtube:comInvent01")
        self.assertEqual(comentario.url, "https://www.youtube.com/watch?v=vidInvent01&lc=comInvent01")
        self.assertEqual(comentario.thread_id, "youtube:vidInvent01")
        self.assertEqual((comentario.engagement.reactions, comentario.engagement.replies), (8, 3))
        self.assertEqual(comentario.community, "YouTube")
        volcado = comentario.model_dump_json()
        for nombre in ("Canal Inventado", "autora-inventada", "UCautoraInventada"):
            self.assertNotIn(nombre, volcado, "D-M7/R9: ni canal ni autor en claro")

    async def test_comentarios_desactivados_no_paran_la_fuente(self):
        items = await todos(fuente(api(hilos=error_google(403, "commentsDisabled"))).search(
            SearchQuery(keywords=["invoice"])))
        self.assertEqual(items, [], "sin comentarios no hay evidencia")

    async def test_el_presupuesto_de_unidades_corta_antes_de_pasarse(self):
        from core.sources.budget import SourceBudget

        peticiones: list[httpx.Request] = []
        presupuesto = SourceBudget(source="youtube", max_units=150)
        # Planifica las búsquedas con las unidades que tiene: no llega a pasarse.
        await todos(fuente(api(peticiones=peticiones), presupuesto).search(
            SearchQuery(keywords=["a", "b"])))
        busquedas = [p for p in peticiones if p.url.path.endswith("/search")]
        self.assertEqual(len(busquedas), 1, "la segunda búsqueda costaría 100 más")
        self.assertLessEqual(presupuesto.spent_units, 150)

    async def test_cuota_diaria_agotada_para_sin_reintentar(self):
        peticiones: list[httpx.Request] = []
        with self.assertRaises(SourceRateLimited):
            await todos(fuente(api(busqueda=error_google(403, "quotaExceeded"),
                                   peticiones=peticiones)).search(SearchQuery(keywords=["x"])))
        self.assertEqual(len(peticiones), 1)

    async def test_clave_invalida(self):
        with self.assertRaises(SourceAuthFailed):
            await todos(fuente(api(busqueda=error_google(400, "keyInvalid"))).search(
                SearchQuery(keywords=["x"])))


class TestSonda(unittest.IsolatedAsyncioTestCase):
    async def test_la_sonda_cuesta_una_unidad(self):
        peticiones: list[httpx.Request] = []
        adaptador = fuente(api(peticiones=peticiones))
        resultado = await adaptador.probe()
        self.assertTrue(resultado.ok)
        self.assertEqual(urlparse(str(peticiones[0].url)).path, "/youtube/v3/videos")
        self.assertEqual(adaptador.budget.spent_units, 1)


if __name__ == "__main__":
    unittest.main()
