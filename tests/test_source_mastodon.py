"""
Fuente 7: Mastodon (API oficial de la instancia)
================================================

Dobles con la forma documentada (docs.joinmastodon.org):
- GET /api/v2/search?q&type=statuses&limit&resolve=false con Bearer
  (permiso read:search) -> {accounts, statuses, hashtags}.
- Status: id, created_at, content (HTML), url (con @usuario), uri,
  language, visibility, replies_count, reblogs_count, favourites_count y
  account {id, acct, username}.
- Cuota: X-RateLimit-Limit/-Remaining y X-RateLimit-Reset en ISO 8601.

D-M7: la URL guardada es la de la API por id de estado
(https://<instancia>/api/v1/statuses/<id>), sin @usuario; la comunidad es el
dominio del servidor del autor, sin su nombre. Solo estados públicos. El
token solo tiene read:search y read:statuses: la sonda es una búsqueda
mínima (verify_credentials exigiría read:accounts). Datos inventados (R8).
"""

import unittest
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx

from core.evidence.model import SearchQuery
from core.sources.budget import SourceBudget
from core.sources.errors import SourceAuthFailed, SourceCredentialsMissing
from core.sources.mastodon import MastodonSource

SAL = "ad" * 32
CREDENCIALES = {"instance": "mastodon.social", "access_token": "tok-inventado"}
ESTADO = {
    "id": "113000000000000001", "created_at": "2026-06-03T08:30:00.000Z",
    "content": "<p>Every quarter I rebuild invoices by hand.<br>Is there a tool?</p>",
    "url": "https://fosstodon.example/@autora_inventada/113000000000000001",
    "uri": "https://fosstodon.example/users/autora_inventada/statuses/9",
    "language": "en", "visibility": "public", "sensitive": False, "spoiler_text": "",
    "replies_count": 5, "reblogs_count": 2, "favourites_count": 14,
    "account": {"id": "1090", "acct": "autora_inventada@fosstodon.example",
                "username": "autora_inventada", "display_name": "Autora Inventada"},
}


def respuesta(*estados):
    return {"accounts": [], "statuses": list(estados), "hashtags": []}


def fuente(manejador, credenciales=None):
    return MastodonSource(http=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
                          budget=SourceBudget(), credentials=credenciales or CREDENCIALES,
                          author_salt=SAL)


async def todos(generador):
    return [x async for x in generador]


class TestDeclaracion(unittest.TestCase):
    def test_instancia_y_token(self):
        self.assertEqual(MastodonSource.id, "mastodon")
        self.assertTrue(MastodonSource.requires_credentials)
        self.assertFalse(MastodonSource.commercial_use_allowed)
        campos = {c.name: (c.env_var, c.secret, c.required) for c in MastodonSource.credential_fields}
        self.assertEqual(campos, {
            "instance": ("RIR_MASTODON_INSTANCE", False, True),
            "access_token": ("RIR_MASTODON_ACCESS_TOKEN", True, True)})


class TestBusqueda(unittest.IsolatedAsyncioTestCase):
    async def test_busca_estados_en_la_instancia_con_bearer(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=respuesta())

        await todos(fuente(manejador).search(SearchQuery(keywords=["invoice"],
                                                         phrases=["is there a tool"])))
        url = urlparse(str(peticiones[0].url))
        params = parse_qs(url.query)
        self.assertEqual((url.scheme, url.netloc, url.path),
                         ("https", "mastodon.social", "/api/v2/search"))
        self.assertEqual((params["type"], params["resolve"]), (["statuses"], ["false"]))
        # Solo el tema: con la frase entre comillas devolvía 0 (49 consultas medidas).
        self.assertEqual(params["q"], ["invoice"])
        self.assertEqual(peticiones[0].headers["Authorization"], "Bearer tok-inventado")

    async def test_un_estado_sin_usuario_en_url_ni_comunidad(self):
        [item] = await todos(fuente(lambda _r: httpx.Response(200, json=respuesta(ESTADO)))
                             .search(SearchQuery(keywords=["invoice"])))
        self.assertEqual(item.id, "mastodon:mastodon.social:113000000000000001")
        self.assertEqual(item.url, "https://mastodon.social/api/v1/statuses/113000000000000001")
        self.assertEqual(item.community, "fosstodon.example")
        self.assertEqual(item.text, "Every quarter I rebuild invoices by hand.\nIs there a tool?")
        self.assertEqual((item.language, item.kind), ("en", "post"))
        self.assertEqual((item.engagement.replies, item.engagement.reactions), (5, 14))
        self.assertEqual(item.created_at, datetime(2026, 6, 3, 8, 30, tzinfo=UTC))
        volcado = item.model_dump_json()
        for nombre in ("autora_inventada", "Autora Inventada"):
            self.assertNotIn(nombre, volcado, "D-M7/R9: ningún nombre de usuario")

    async def test_solo_estados_publicos_y_dentro_de_la_ventana(self):
        privado = dict(ESTADO, id="2", visibility="unlisted")
        viejo = dict(ESTADO, id="3", created_at="2025-01-01T00:00:00.000Z")
        items = await todos(fuente(lambda _r: httpx.Response(
            200, json=respuesta(ESTADO, privado, viejo))).search(
                SearchQuery(keywords=["x"], since=datetime(2026, 1, 1, tzinfo=UTC))))
        self.assertEqual([i.id.rsplit(":", 1)[1] for i in items], ["113000000000000001"])

    async def test_la_instancia_admite_url_y_rechaza_lo_que_no_es_un_dominio(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=respuesta())

        await todos(fuente(manejador, dict(CREDENCIALES, instance="https://Mastodon.Social/"))
                    .search(SearchQuery(keywords=["x"])))
        self.assertEqual(urlparse(str(peticiones[0].url)).netloc, "mastodon.social")
        for mala in ("mastodon.social/../x", "user@mastodon.social", "localhost:8080", ""):
            with self.subTest(instancia=mala), self.assertRaises(SourceCredentialsMissing):
                await todos(fuente(manejador, dict(CREDENCIALES, instance=mala))
                            .search(SearchQuery(keywords=["x"])))

    async def test_token_rechazado(self):
        with self.assertRaises(SourceAuthFailed):
            await todos(fuente(lambda _r: httpx.Response(401, json={"error": "The access token is invalid"}))
                        .search(SearchQuery(keywords=["x"])))

    async def test_reset_de_cuota_en_iso_8601(self):
        def manejador(_peticion):
            return httpx.Response(200, json=respuesta(), headers={
                "X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "299",
                "X-RateLimit-Reset": "2026-09-23T21:05:00.000Z"})

        adaptador = fuente(manejador)
        await todos(adaptador.search(SearchQuery(keywords=["x"])))
        self.assertEqual((adaptador.quota.limit, adaptador.quota.remaining), (300, 299))
        self.assertEqual(adaptador.quota.reset_epoch,
                         datetime(2026, 9, 23, 21, 5, tzinfo=UTC).timestamp())


class TestSonda(unittest.IsolatedAsyncioTestCase):
    async def test_la_sonda_es_una_busqueda_minima(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=respuesta())

        resultado = await fuente(manejador).probe()
        self.assertTrue(resultado.ok)
        params = parse_qs(urlparse(str(peticiones[0].url)).query)
        self.assertEqual((urlparse(str(peticiones[0].url)).path, params["limit"]),
                         ("/api/v2/search", ["1"]))


if __name__ == "__main__":
    unittest.main()
