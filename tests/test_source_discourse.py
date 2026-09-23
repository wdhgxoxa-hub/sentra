"""
Fuente 8: Discourse (API pública de cada foro)
==============================================

Dobles con la forma documentada (docs.discourse.org):
- GET /search.json?q=... -> {posts: [{id, username, created_at, blurb,
  post_number, topic_id, like_count}], topics: [{id, title, slug,
  posts_count, reply_count}]}. La ventana va dentro de q como after:AAAA-MM-DD.
- GET /t/{topic_id}/posts.json?post_ids[]=... -> {post_stream: {posts:
  [{id, username, created_at, cooked (HTML), post_number, topic_id,
  topic_slug, reply_count}]}}: el texto completo, una petición por tema.

Pública y sin credenciales, pero hay que decirle qué foros: el campo
`forums` de la tarjeta (RIR_DISCOURSE_FORUMS) es obligatorio; el perfil
puede añadir más. Enlace sin usuario (D-M7). Licencia de cada foro no
verificada: solo uso personal. Datos inventados (R8).

Forma contrastada el 2026-09-23 con 4 peticiones reales a meta.discourse.org
(about.json, search.json y 2 lecturas de tema): 2 posts con todos los campos.
"""

import unittest
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx

from core.evidence.model import SearchQuery
from core.sources.budget import SourceBudget
from core.sources.discourse import DiscourseSource
from core.sources.errors import SourceCredentialsMissing
from core.sources.registry import source_status

SAL = "d5" * 32
FORO = "https://foro.example.org"
BUSQUEDA = {
    "posts": [{"id": 501, "username": "autor_inventado", "created_at": "2026-04-02T10:00:00.000Z",
               "blurb": "I export every invoice by hand...", "post_number": 1, "topic_id": 77,
               "like_count": 6}],
    "topics": [{"id": 77, "title": "Invoice export is painful", "slug": "invoice-export-is-painful",
                "posts_count": 9, "reply_count": 8}],
    "users": [], "categories": [],
}
POSTS = {"post_stream": {"posts": [{
    "id": 501, "username": "autor_inventado", "created_at": "2026-04-02T10:00:00.000Z",
    "cooked": "<p>I export every invoice by hand.</p><p>Is there a plugin?</p>",
    "post_number": 1, "topic_id": 77, "topic_slug": "invoice-export-is-painful",
    "reply_count": 3}]}, "id": 77}


class Reloj:
    def __init__(self):
        self.esperas = []

    async def sleep(self, segundos):
        self.esperas.append(segundos)


def servidor(peticiones, busqueda=BUSQUEDA):
    def manejador(peticion):
        peticiones.append(peticion)
        if peticion.url.path == "/search.json":
            return httpx.Response(200, json=busqueda)
        return httpx.Response(200, json=POSTS)
    return manejador


def fuente(manejador, foros=FORO, reloj=None):
    return DiscourseSource(http=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
                           budget=SourceBudget(), credentials={"forums": foros} if foros else {},
                           author_salt=SAL, sleep=(reloj or Reloj()).sleep)


async def todos(generador):
    return [x async for x in generador]


class TestDeclaracion(unittest.TestCase):
    def test_sin_foros_queda_sin_configurar(self):
        self.assertEqual(DiscourseSource.id, "discourse")
        self.assertFalse(DiscourseSource.commercial_use_allowed)
        [foros] = DiscourseSource.credential_fields
        self.assertEqual((foros.name, foros.env_var, foros.secret, foros.required),
                         ("forums", "RIR_DISCOURSE_FORUMS", False, True))
        self.assertEqual(source_status(DiscourseSource, {}, None, False).status, "no_configurada")
        con = source_status(DiscourseSource, {"RIR_DISCOURSE_FORUMS": FORO}, None, False)
        self.assertEqual(con.status, "configurada_sin_verificar")


class TestBusqueda(unittest.IsolatedAsyncioTestCase):
    async def test_busca_en_el_foro_y_lee_el_texto_completo_por_tema(self):
        peticiones = []
        consulta = SearchQuery(keywords=["invoice"], phrases=["is there a"],
                               since=datetime(2026, 1, 1, tzinfo=UTC))
        [item] = await todos(fuente(servidor(peticiones)).search(consulta))
        busqueda, tema = peticiones
        self.assertEqual(urlparse(str(busqueda.url)).netloc, "foro.example.org")
        self.assertEqual(parse_qs(urlparse(str(busqueda.url)).query)["q"],
                         ['invoice "is there a" after:2026-01-01'])
        self.assertEqual(urlparse(str(tema.url)).path, "/t/77/posts.json")
        self.assertEqual(parse_qs(urlparse(str(tema.url)).query)["post_ids[]"], ["501"])
        self.assertEqual(item.id, "discourse:foro.example.org:501")
        self.assertEqual(item.text, "I export every invoice by hand.\n\nIs there a plugin?")
        self.assertEqual(item.title, "Invoice export is painful")
        self.assertEqual(item.url, "https://foro.example.org/t/invoice-export-is-painful/77/1")
        self.assertEqual((item.community, item.kind), ("foro.example.org", "post"))
        self.assertEqual(item.thread_id, "discourse:foro.example.org:t77")
        self.assertEqual((item.engagement.reactions, item.engagement.replies), (6, 3))
        self.assertNotIn("autor_inventado", item.model_dump_json(), "R9")

    async def test_los_objetivos_del_perfil_se_suman_a_los_de_la_tarjeta(self):
        peticiones = []
        await todos(fuente(servidor(peticiones, busqueda={"posts": [], "topics": []})).search(
            SearchQuery(keywords=["x"], targets={"discourse": ["https://otro.example.net/"]})))
        self.assertEqual({urlparse(str(p.url)).netloc for p in peticiones},
                         {"foro.example.org", "otro.example.net"})

    async def test_un_foro_que_no_es_https_o_no_es_un_dominio_se_rechaza(self):
        for malo in ("http://foro.example.org", "https://foro.example.org/../x", "ftp://a.b",
                     "https://localhost:3000"):
            with self.subTest(foro=malo), self.assertRaises(SourceCredentialsMissing):
                await todos(fuente(servidor([]), foros=malo).search(SearchQuery(keywords=["x"])))

    async def test_espacia_las_peticiones(self):
        reloj = Reloj()
        await todos(fuente(servidor([]), reloj=reloj).search(SearchQuery(keywords=["a", "b"])))
        self.assertTrue(reloj.esperas and all(e >= 1.0 for e in reloj.esperas))


class TestSonda(unittest.IsolatedAsyncioTestCase):
    async def test_la_sonda_consulta_about_json_del_primer_foro(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json={"about": {"title": "Foro inventado"}})

        resultado = await fuente(manejador).probe()
        self.assertTrue(resultado.ok)
        self.assertEqual(urlparse(str(peticiones[0].url)).path, "/about.json")


if __name__ == "__main__":
    unittest.main()
