"""
Fuente 10: X (API v2 de pago) — deshabilitada y sin llamadas reales
===================================================================

R7 prohíbe cualquier llamada real a X en esta misión. Dos capas:
- `pending_approval`: nunca entra en un escaneo, «Probar» no sale a la red
  y `search` se niega aunque haya credenciales (como Reddit).
- `disabled_by_default`: sin estado guardado, la fuente sale apagada.

El código sigue la API v2 documentada (docs.x.com): GET
/2/tweets/search/recent con Bearer; respuesta {data: [{id, text,
created_at, author_id, lang, public_metrics}], meta}. Coste en USD por
petición con tope por escaneo. Solo dobles; datos inventados (R8).
"""

import unittest

import httpx

from core.evidence.model import SearchQuery
from core.sources.budget import SourceBudget
from core.sources.errors import SourceBudgetExhausted, SourcePendingApproval
from core.sources.registry import InMemorySourcesState, active_sources, source_status
from core.sources.x import XSource
from tests._ayudas import presente

SAL = "e0" * 32
TOKEN = {"bearer_token": "x-token-inventado"}
ENV = {"RIR_X_BEARER_TOKEN": "x-token-inventado"}
TUIT = {"id": "1900000000000000001", "text": "Invoicing tools are all terrible, would pay for one that works",
        "created_at": "2026-06-10T12:00:00.000Z", "author_id": "12345", "lang": "en",
        "public_metrics": {"retweet_count": 1, "reply_count": 4, "like_count": 20, "quote_count": 0}}


class Aprobada(XSource):
    """Sin la marca de aprobación: solo para probar el código con dobles."""

    pending_approval = None


def prohibido(_peticion):
    raise AssertionError("R7: ninguna llamada real a X")


def fuente(manejador, clase=XSource, budget=None):
    return clase(http=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
                 budget=budget or clase.default_budget(), credentials=TOKEN, author_salt=SAL)


async def todos(generador):
    return [x async for x in generador]


class TestDeshabilitada(unittest.IsolatedAsyncioTestCase):
    def test_sale_apagada_por_defecto_y_fuera_del_escaneo(self):
        self.assertTrue(XSource.disabled_by_default)
        estado = source_status(XSource, ENV, None, commercial_mode=False)
        self.assertEqual(estado.status, "deshabilitada_por_usuario")
        self.assertFalse(estado.active)
        self.assertEqual(active_sources([XSource], ENV, InMemorySourcesState(), False), [])

    def test_encendida_por_el_usuario_sigue_sin_llamar(self):
        guardado = InMemorySourcesState()
        guardado.set_disabled("x", False)
        estado = source_status(XSource, ENV, guardado.get("x"), commercial_mode=False)
        self.assertEqual(estado.status, "no_configurada")
        self.assertFalse(estado.active)

    async def test_search_y_probar_se_niegan_sin_red(self):
        with self.assertRaises(SourcePendingApproval):
            await todos(fuente(prohibido).search(SearchQuery(keywords=["x"])))
        resultado = await fuente(prohibido).probe()
        self.assertEqual((resultado.ok, resultado.code), (False, "source_pending_approval"))


class TestCodigoConDobles(unittest.IsolatedAsyncioTestCase):
    def test_coste_en_usd_con_tope_por_escaneo(self):
        self.assertEqual(XSource.cost_model.unit, "usd")
        presupuesto = XSource.default_budget()
        self.assertIsNotNone(presupuesto.max_usd)
        self.assertGreater(presente(presupuesto.max_usd), 0)

    async def test_busqueda_reciente_con_bearer_y_sin_nombre_de_usuario(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json={"data": [TUIT], "meta": {"result_count": 1}})

        [item] = await todos(fuente(manejador, clase=Aprobada).search(SearchQuery(keywords=["invoice"])))
        self.assertEqual(peticiones[0].url.path, "/2/tweets/search/recent")
        self.assertEqual(peticiones[0].headers["Authorization"], "Bearer x-token-inventado")
        self.assertEqual(item.id, "x:1900000000000000001")
        self.assertEqual(item.url, "https://x.com/i/web/status/1900000000000000001")
        self.assertEqual((item.engagement.replies, item.engagement.reactions), (4, 20))

    async def test_el_tope_en_usd_corta_antes_de_gastar(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json={"data": [TUIT], "meta": {"result_count": 1}})

        tope = SourceBudget(source="x", max_usd=XSource.cost_model.per_request)
        with self.assertRaises(SourceBudgetExhausted):
            await todos(fuente(manejador, clase=Aprobada, budget=tope).search(
                SearchQuery(keywords=["a", "b"])))
        self.assertEqual(len(peticiones), 1)


if __name__ == "__main__":
    unittest.main()
