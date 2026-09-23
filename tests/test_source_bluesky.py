"""
Fuente 5: Bluesky (API oficial del AT Protocol)
===============================================

Dobles con la forma documentada (docs.bsky.app):
- POST /xrpc/com.atproto.server.createSession {identifier, password} ->
  {accessJwt, refreshJwt, did, handle}. La contraseña es una contraseña
  de app, nunca la de la cuenta.
- GET /xrpc/app.bsky.feed.searchPosts?q&sort&since&limit&cursor ->
  {cursor, hitsTotal, posts: [PostView]}; PostView trae uri
  (at://<did>/app.bsky.feed.post/<rkey>), author {did, handle},
  record {text, createdAt, langs}, replyCount, repostCount, likeCount,
  quoteCount.
- Cuota en las cabeceras ratelimit-limit/-remaining/-reset (sin X-).

D-M7 (R5 frente a R9): la URL del original lleva el DID, nunca el @handle:
https://bsky.app/profile/<did>/post/<rkey>. El autor, solo como hash.
createSession tiene un límite bajo (30 cada 5 min por cuenta): la sesión se
reutiliza. Contenido, DIDs y handles inventados (R8).
"""

import unittest
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx

from core.evidence.model import SearchQuery
from core.sources.bluesky import BlueskySource
from core.sources.budget import SourceBudget
from core.sources.errors import SourceAuthFailed, SourceRateLimited

SAL = "b1" * 32
CREDENCIALES = {"identifier": "sentra-inventada.bsky.social", "app_password": "abcd-efgh-ijkl-mnop"}
DID = "did:plc:inventado0000000000000a"
SESION = {"accessJwt": "jwt-acceso", "refreshJwt": "jwt-refresco", "did": "did:plc:yo",
          "handle": "sentra-inventada.bsky.social"}
POST = {
    "uri": f"at://{DID}/app.bsky.feed.post/3kinventado2x",
    "cid": "bafyinventado",
    "author": {"did": DID, "handle": "autora-inventada.bsky.social", "displayName": "Autora"},
    "record": {"$type": "app.bsky.feed.post",
               "text": "Every month I rebuild invoices by hand. Is there a tool for this?",
               "createdAt": "2026-06-01T12:00:00.000Z", "langs": ["en"]},
    "replyCount": 4, "repostCount": 2, "likeCount": 19, "quoteCount": 1,
    "indexedAt": "2026-06-01T12:00:01.000Z",
}


def resultados(*posts, cursor=None):
    datos = {"posts": list(posts), "hitsTotal": len(posts)}
    if cursor:
        datos["cursor"] = cursor
    return datos


def servidor(peticiones, busqueda=None):
    def manejador(peticion):
        peticiones.append(peticion)
        if peticion.url.path.endswith("com.atproto.server.createSession"):
            return httpx.Response(200, json=SESION)
        return httpx.Response(200, json=busqueda if busqueda is not None else resultados(POST))
    return manejador


def fuente(manejador, credenciales=None, **presupuesto):
    return BlueskySource(http=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
                         budget=SourceBudget(**presupuesto),
                         credentials=credenciales or CREDENCIALES, author_salt=SAL)


async def todos(generador):
    return [x async for x in generador]


class TestDeclaracion(unittest.TestCase):
    def test_usuario_y_contrasena_de_app(self):
        self.assertEqual(BlueskySource.id, "bluesky")
        self.assertTrue(BlueskySource.requires_credentials)
        campos = {c.name: (c.env_var, c.secret, c.required) for c in BlueskySource.credential_fields}
        self.assertEqual(campos, {
            "identifier": ("RIR_BLUESKY_IDENTIFIER", False, True),
            "app_password": ("RIR_BLUESKY_APP_PASSWORD", True, True)})
        self.assertTrue(BlueskySource.terms_url.startswith("https://"))


class TestSesion(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        BlueskySource.sessions.clear()

    async def test_crea_la_sesion_con_la_contrasena_de_app(self):
        peticiones = []
        await todos(fuente(servidor(peticiones)).search(SearchQuery(keywords=["invoice"])))
        sesion = peticiones[0]
        self.assertEqual((sesion.method, urlparse(str(sesion.url)).path),
                         ("POST", "/xrpc/com.atproto.server.createSession"))
        import json

        self.assertEqual(json.loads(sesion.content), {"identifier": CREDENCIALES["identifier"],
                                                      "password": CREDENCIALES["app_password"]})
        self.assertEqual(peticiones[1].headers["Authorization"], "Bearer jwt-acceso")

    async def test_la_sesion_se_reutiliza_entre_escaneos(self):
        peticiones = []
        await todos(fuente(servidor(peticiones)).search(SearchQuery(keywords=["a"])))
        await todos(fuente(servidor(peticiones)).search(SearchQuery(keywords=["b"])))
        sesiones = [p for p in peticiones if p.url.path.endswith("createSession")]
        self.assertEqual(len(sesiones), 1)

    async def test_otra_cuenta_no_reutiliza_la_sesion(self):
        peticiones = []
        await todos(fuente(servidor(peticiones)).search(SearchQuery(keywords=["a"])))
        otra = dict(CREDENCIALES, identifier="otra-inventada.bsky.social")
        await todos(fuente(servidor(peticiones), otra).search(SearchQuery(keywords=["a"])))
        self.assertEqual(len([p for p in peticiones if p.url.path.endswith("createSession")]), 2)

    async def test_contrasena_rechazada(self):
        def manejador(peticion):
            return httpx.Response(401, json={"error": "AuthenticationRequired",
                                             "message": "Invalid identifier or password"})

        with self.assertRaises(SourceAuthFailed):
            await todos(fuente(manejador).search(SearchQuery(keywords=["x"])))

    async def test_una_contrasena_mala_no_se_reintenta(self):
        # createSession tiene un límite bajo por cuenta: no se gasta en vano.
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(401, json={"error": "AuthenticationRequired"})

        with self.assertRaises(SourceAuthFailed):
            await todos(fuente(manejador).search(SearchQuery(keywords=["x"])))
        self.assertEqual(len(peticiones), 1)

    async def test_un_token_caducado_se_renueva_una_vez(self):
        peticiones = []
        busquedas = iter([httpx.Response(401, json={"error": "ExpiredToken"}),
                          httpx.Response(200, json=resultados(POST))])

        def manejador(peticion):
            peticiones.append(peticion)
            if peticion.url.path.endswith("createSession"):
                return httpx.Response(200, json=SESION)
            return next(busquedas)

        items = await todos(fuente(manejador).search(SearchQuery(keywords=["x"])))
        self.assertEqual(len(items), 1)
        self.assertEqual(len([p for p in peticiones if p.url.path.endswith("createSession")]), 2)


class TestBusqueda(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        BlueskySource.sessions.clear()

    async def test_busca_recientes_dentro_de_la_ventana(self):
        peticiones = []
        consulta = SearchQuery(keywords=["invoice"], phrases=["is there a tool"],
                               since=datetime(2026, 1, 1, tzinfo=UTC))
        await todos(fuente(servidor(peticiones)).search(consulta))
        url = urlparse(str(peticiones[1].url))
        params = parse_qs(url.query)
        self.assertEqual(url.path, "/xrpc/app.bsky.feed.searchPosts")
        self.assertEqual(params["q"], ['invoice "is there a tool"'])
        self.assertEqual(params["sort"], ["latest"])
        self.assertEqual(params["since"], ["2026-01-01T00:00:00Z"])

    async def test_un_post_con_url_por_did_y_sin_handle(self):
        [item] = await todos(fuente(servidor([])).search(SearchQuery(keywords=["invoice"])))
        self.assertEqual((item.id, item.kind), (f"bluesky:{DID}/3kinventado2x", "post"))
        self.assertEqual(item.url, f"https://bsky.app/profile/{DID}/post/3kinventado2x")
        self.assertEqual(item.community, "Bluesky")
        self.assertEqual(item.language, "en")
        self.assertEqual((item.engagement.replies, item.engagement.reactions), (4, 19))
        self.assertEqual(item.created_at, datetime(2026, 6, 1, 12, 0, tzinfo=UTC))
        volcado = item.model_dump_json()
        self.assertNotIn("autora-inventada", volcado, "D-M7: nunca el @handle")
        self.assertNotIn("Autora", volcado)

    async def test_el_mismo_post_en_dos_busquedas_sale_una_vez(self):
        items = await todos(fuente(servidor([])).search(SearchQuery(keywords=["a", "b"])))
        self.assertEqual(len(items), 1)

    async def test_cuota_agotada_con_las_cabeceras_de_bluesky(self):
        def manejador(peticion):
            if peticion.url.path.endswith("createSession"):
                return httpx.Response(200, json=SESION)
            return httpx.Response(429, headers={"ratelimit-limit": "3000",
                                                "ratelimit-remaining": "0",
                                                "ratelimit-reset": "4102444800"})

        adaptador = fuente(manejador)
        with self.assertRaises(SourceRateLimited):
            await todos(adaptador.search(SearchQuery(keywords=["x"])))
        self.assertEqual((adaptador.quota.limit, adaptador.quota.remaining), (3000, 0))


class TestSonda(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        BlueskySource.sessions.clear()

    async def test_la_sonda_es_una_busqueda_minima_autenticada(self):
        peticiones = []
        resultado = await fuente(servidor(peticiones, resultados())).probe()
        self.assertTrue(resultado.ok)
        self.assertEqual(parse_qs(urlparse(str(peticiones[-1].url)).query)["limit"], ["1"])


if __name__ == "__main__":
    unittest.main()
