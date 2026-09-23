"""
Fuente 1: Hacker News (API oficial de búsqueda de Algolia)
=========================================================

Dobles fieles a la respuesta real de https://hn.algolia.com/api/v1
(campos comprobados con 2 peticiones reales el 2026-09-23): los hits traen
objectID, author, created_at_i, _tags y, según el tipo, title/story_text/
points/num_comments (historias) o comment_text/story_id/story_title
(comentarios). Los textos vienen en HTML. Contenido y autores inventados (R8).
"""

import unittest
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx

from core.evidence.model import SearchQuery
from core.sources.budget import SourceBudget
from core.sources.hackernews import HackerNewsSource

SAL = "7a" * 32
DESDE = datetime(2026, 1, 1, tzinfo=UTC)

HISTORIA = {
    "objectID": "40000001", "author": "inventado_uno", "created_at_i": 1780000000,
    "created_at": "2026-05-28T20:26:40Z", "title": "Ask HN: Is there a tool to reconcile invoices?",
    "story_text": "<p>I spend hours every week matching invoices &amp; payments by hand.<p>Any ideas?",
    "points": 42, "num_comments": 17, "story_id": 40000001,
    "_tags": ["story", "author_inventado_uno", "story_40000001", "ask_hn"],
}
COMENTARIO = {
    "objectID": "40000055", "author": "inventada_dos", "created_at_i": 1780003600,
    "created_at": "2026-05-28T21:26:40Z",
    "comment_text": "I wrote a script for this, it breaks every month. I&#x27;d pay for a real tool.",
    "story_id": 40000001, "parent_id": 40000001,
    "story_title": "Ask HN: Is there a tool to reconcile invoices?", "story_url": None,
    "_tags": ["comment", "author_inventada_dos", "story_40000001"],
}


def respuesta(*hits, nb_pages=1):
    return {"hits": list(hits), "page": 0, "nbPages": nb_pages, "hitsPerPage": 50,
            "nbHits": len(hits), "exhaustiveNbHits": True, "query": "", "params": ""}


def fuente(manejador, **presupuesto):
    return HackerNewsSource(
        http=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
        budget=SourceBudget(**presupuesto), credentials={}, author_salt=SAL,
    )


async def todos(generador):
    return [x async for x in generador]


class TestDeclaracion(unittest.TestCase):
    def test_es_publica_y_declara_sus_terminos(self):
        self.assertEqual(HackerNewsSource.id, "hackernews")
        self.assertFalse(HackerNewsSource.requires_credentials)
        self.assertTrue(HackerNewsSource.terms_url.startswith("https://"))


class TestBusqueda(unittest.IsolatedAsyncioTestCase):
    async def test_pide_historias_y_comentarios_dentro_de_la_ventana(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=respuesta())

        consulta = SearchQuery(keywords=["invoice"], phrases=["is there a tool"], since=DESDE)
        await todos(fuente(manejador).search(consulta))
        url = urlparse(str(peticiones[0].url))
        params = parse_qs(url.query)
        self.assertEqual(url.netloc, "hn.algolia.com")
        self.assertEqual(url.path, "/api/v1/search")
        self.assertEqual(params["query"], ["invoice is there a tool"])
        self.assertEqual(params["tags"], ["(story,comment)"])
        self.assertEqual(params["numericFilters"], [f"created_at_i>{int(DESDE.timestamp())}"])

    async def test_una_historia_ask_hn_con_su_texto_limpio(self):
        items = await todos(fuente(lambda _r: httpx.Response(200, json=respuesta(HISTORIA))).search(
            SearchQuery(keywords=["invoice"])))
        [historia] = items
        self.assertEqual(historia.id, "hackernews:40000001")
        self.assertEqual((historia.kind, historia.community), ("post", "Ask HN"))
        self.assertEqual(historia.title, "Ask HN: Is there a tool to reconcile invoices?")
        self.assertEqual(historia.text, "I spend hours every week matching invoices & payments by hand.\n\nAny ideas?")
        self.assertEqual(historia.url, "https://news.ycombinator.com/item?id=40000001")
        self.assertEqual((historia.engagement.score, historia.engagement.replies), (42, 17))
        self.assertEqual(historia.created_at, datetime.fromtimestamp(1780000000, UTC))

    async def test_un_comentario_va_en_el_hilo_de_su_historia(self):
        [comentario] = await todos(fuente(lambda _r: httpx.Response(
            200, json=respuesta(COMENTARIO))).search(SearchQuery(keywords=["invoice"])))
        self.assertEqual((comentario.id, comentario.kind), ("hackernews:40000055", "comment"))
        self.assertEqual(comentario.thread_id, "hackernews:40000001")
        self.assertEqual(comentario.text, "I wrote a script for this, it breaks every month. I'd pay for a real tool.")
        self.assertEqual(comentario.community, "Hacker News")
        self.assertNotIn("inventada_dos", comentario.model_dump_json(), "autor solo como hash (R9)")

    async def test_el_mismo_hit_en_dos_busquedas_sale_una_vez(self):
        consulta = SearchQuery(keywords=["invoice", "billing"])
        items = await todos(fuente(lambda _r: httpx.Response(200, json=respuesta(HISTORIA))).search(consulta))
        self.assertEqual([i.id for i in items], ["hackernews:40000001"])

    async def test_un_enlace_sin_texto_usa_el_titulo(self):
        enlace = dict(HISTORIA, objectID="40000002", story_text=None, _tags=["story"])
        [item] = await todos(fuente(lambda _r: httpx.Response(200, json=respuesta(enlace))).search(
            SearchQuery(keywords=["x"])))
        self.assertEqual(item.text, HISTORIA["title"])

    async def test_no_pide_mas_busquedas_que_su_presupuesto(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=respuesta())

        consulta = SearchQuery(keywords=["a", "b", "c"], phrases=["x", "y"])
        await todos(fuente(manejador, max_requests=4).search(consulta))
        self.assertEqual(len(peticiones), 4)


class TestSonda(unittest.IsolatedAsyncioTestCase):
    async def test_una_respuesta_real_la_verifica(self):
        resultado = await fuente(lambda _r: httpx.Response(200, json=respuesta(HISTORIA))).probe()
        self.assertTrue(resultado.ok)

    async def test_un_fallo_se_informa_con_codigo_sin_lanzar(self):
        resultado = await fuente(lambda _r: httpx.Response(429, headers={"Retry-After": "600"})).probe()
        self.assertFalse(resultado.ok)
        self.assertEqual(resultado.code, "source_rate_limited")


if __name__ == "__main__":
    unittest.main()
