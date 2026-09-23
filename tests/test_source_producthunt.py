"""
Fuente 9: Product Hunt (API GraphQL v2 oficial)
===============================================

Dobles con la forma documentada (api.producthunt.com/v2/docs):
- POST /v2/api/graphql con Authorization: Bearer <developer token>.
- La API no busca por texto: topics(query:) da los temas del perfil y
  posts(topic:, postedAfter:, first:) sus productos, con comments(first:).
- Post: id, name, tagline, description, url, createdAt, votesCount,
  commentsCount. Comment: id, body, createdAt, votesCount, url, user {id}.
  Los usuarios ajenos llegan ocultos (id "0"): no se cuentan como autor.
- Errores GraphQL con HTTP 200 en `errors`; cuota por complejidad en
  X-Rate-Limit-Limit/-Remaining/-Reset (segundos).

Términos: sin uso comercial sin permiso. Datos inventados (R8).
"""

import json
import unittest
from datetime import UTC, datetime

import httpx

from core.evidence.model import SearchQuery
from core.sources.budget import SourceBudget
from core.sources.errors import SourceAuthFailed, SourceRateLimited
from core.sources.producthunt import ProductHuntSource

SAL = "9f" * 32
TOKEN = {"token": "ph-token-inventado"}
TEMAS = {"data": {"topics": {"edges": [{"node": {"id": "1", "slug": "invoicing", "name": "Invoicing"}}]}}}
POSTS = {"data": {"posts": {"edges": [{"node": {
    "id": "700001", "name": "FacturaFácil", "tagline": "Invoices that export themselves",
    "description": "Stop copying invoices into spreadsheets.",
    "url": "https://www.producthunt.com/posts/facturafacil", "createdAt": "2026-05-20T07:00:00Z",
    "votesCount": 240, "commentsCount": 2,
    "comments": {"edges": [
        {"node": {"id": "c1", "body": "Wish it supported multi-currency, I'd pay for that.",
                  "createdAt": "2026-05-20T09:00:00Z", "votesCount": 12,
                  "url": "https://www.producthunt.com/posts/facturafacil?comment=c1",
                  "user": {"id": "0", "username": "[REDACTED]"}}},
        {"node": {"id": "c2", "body": "Does it work with QuickBooks?",
                  "createdAt": "2026-05-21T09:00:00Z", "votesCount": 3,
                  "url": "https://www.producthunt.com/posts/facturafacil?comment=c2",
                  "user": {"id": "4242", "username": "usuaria_inventada"}}},
    ]}}}]}}}


def servidor(peticiones, temas=TEMAS, posts=POSTS, cabeceras=None):
    def manejador(peticion):
        cuerpo = json.loads(peticion.content)
        peticiones.append((peticion, cuerpo))
        datos = temas if "topics(" in cuerpo["query"] else posts
        return httpx.Response(200, json=datos, headers=cabeceras or {})
    return manejador


def fuente(manejador):
    return ProductHuntSource(http=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
                             budget=SourceBudget(), credentials=TOKEN, author_salt=SAL)


async def todos(generador):
    return [x async for x in generador]


class TestDeclaracion(unittest.TestCase):
    def test_token_y_solo_uso_personal(self):
        self.assertEqual(ProductHuntSource.id, "producthunt")
        self.assertFalse(ProductHuntSource.commercial_use_allowed)
        self.assertTrue(ProductHuntSource.requires_credentials)
        [token] = ProductHuntSource.credential_fields
        self.assertEqual((token.env_var, token.secret, token.required),
                         ("RIR_PRODUCTHUNT_TOKEN", True, True))


class TestBusqueda(unittest.IsolatedAsyncioTestCase):
    async def test_temas_del_perfil_y_luego_sus_productos_en_la_ventana(self):
        peticiones = []
        consulta = SearchQuery(keywords=["invoicing"], since=datetime(2026, 1, 1, tzinfo=UTC))
        await todos(fuente(servidor(peticiones)).search(consulta))
        (p_temas, temas), (_p_posts, posts) = peticiones
        self.assertEqual(str(p_temas.url), "https://api.producthunt.com/v2/api/graphql")
        self.assertEqual(p_temas.headers["Authorization"], "Bearer ph-token-inventado")
        self.assertEqual(temas["variables"]["query"], "invoicing")
        self.assertEqual(posts["variables"]["topic"], "invoicing")
        self.assertEqual(posts["variables"]["postedAfter"], "2026-01-01T00:00:00Z")

    async def test_producto_y_comentarios_con_autor_oculto_sin_contar(self):
        producto, oculto, visible = await todos(fuente(servidor([])).search(
            SearchQuery(keywords=["invoicing"])))
        self.assertEqual((producto.id, producto.kind), ("producthunt:700001", "product"))
        self.assertEqual(producto.title, "FacturaFácil")
        self.assertEqual(producto.text, "Invoices that export themselves\n\nStop copying invoices into spreadsheets.")
        self.assertEqual(producto.url, "https://www.producthunt.com/posts/facturafacil")
        self.assertEqual((producto.engagement.score, producto.engagement.replies), (240, 2))
        self.assertEqual(producto.community, "Product Hunt · Invoicing")
        self.assertEqual((oculto.kind, oculto.thread_id), ("comment", "producthunt:700001"))
        self.assertIsNone(oculto.author_hash, "id 0 = usuario oculto: no es un autor contable")
        self.assertIsNotNone(visible.author_hash)
        self.assertEqual(visible.url, "https://www.producthunt.com/posts/facturafacil?comment=c2")
        self.assertNotIn("usuaria_inventada", visible.model_dump_json(), "R9")

    async def test_sin_temas_que_casen_no_pide_productos(self):
        peticiones = []
        vacio = {"data": {"topics": {"edges": []}}}
        self.assertEqual(await todos(fuente(servidor(peticiones, temas=vacio)).search(
            SearchQuery(keywords=["nada"]))), [])
        self.assertEqual(len(peticiones), 1)

    async def test_token_invalido_en_errors_con_http_200(self):
        def manejador(_peticion):
            return httpx.Response(200, json={"errors": [{"error": "invalid_oauth_token",
                                                         "error_description": "inventado"}]})

        with self.assertRaises(SourceAuthFailed):
            await todos(fuente(manejador).search(SearchQuery(keywords=["x"])))

    async def test_complejidad_agotada(self):
        def manejador(_peticion):
            return httpx.Response(429, json={"errors": [{"error": "rate_limit_reached"}]},
                                  headers={"X-Rate-Limit-Limit": "6250", "X-Rate-Limit-Remaining": "0",
                                           "X-Rate-Limit-Reset": "900"})

        adaptador = fuente(manejador)
        with self.assertRaises(SourceRateLimited):
            await todos(adaptador.search(SearchQuery(keywords=["x"])))
        self.assertEqual((adaptador.quota.limit, adaptador.quota.remaining), (6250, 0))


class TestSonda(unittest.IsolatedAsyncioTestCase):
    async def test_sonda_minima(self):
        peticiones = []
        resultado = await fuente(servidor(peticiones)).probe()
        self.assertTrue(resultado.ok)
        self.assertIn("first: 1", peticiones[0][1]["query"])


if __name__ == "__main__":
    unittest.main()
