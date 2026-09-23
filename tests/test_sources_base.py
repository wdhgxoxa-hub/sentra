"""
Contrato común de las fuentes (F2.1)
====================================

Diez plataformas con APIs distintas se comportan igual hacia dentro:
- errores tipados (nunca «0 resultados» ante un fallo: lección de AUD-003);
- presupuesto por escaneo comprobado ANTES de enviar;
- Retry-After y X-RateLimit-* respetados;
- User-Agent identificable (R5).

Se prueba con un adaptador mínimo sobre httpx.MockTransport: ninguna
petición sale a la red.
"""

import unittest
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx

from core.evidence.model import EvidenceItem, SearchQuery
from core.sources.base import USER_AGENT, CostModel, SourceAdapter
from core.sources.budget import DEFAULT_MAX_ITEMS, DEFAULT_MAX_REQUESTS, SourceBudget
from core.sources.errors import (
    SourceAuthFailed,
    SourceBudgetExhausted,
    SourceForbidden,
    SourceNotFound,
    SourceRateLimited,
    SourceUnavailable,
)

SAL = "1a" * 32


class FuentePrueba(SourceAdapter):
    id = "prueba"
    display_name = "Fuente de prueba"
    terms_url = "https://example.com/terms"
    commercial_use_allowed = True
    requires_credentials = False
    cost_model = CostModel(unit="request", per_request=1.0)

    async def probe(self):
        await self._get("https://api.example.com/ping")
        return self._probe_ok("ok")

    async def search(self, query: SearchQuery) -> AsyncIterator[EvidenceItem]:
        datos = await self._get("https://api.example.com/search", params={"q": query.keywords[0]})
        for hit in datos["hits"]:
            yield self._item(
                nativo=str(hit["id"]), community="c", kind="post", text=hit["text"],
                url=f"https://example.com/{hit['id']}", author=hit.get("user"),
                created_at=datetime(2026, 9, 1, tzinfo=UTC),
            )


def cliente(manejador):
    return httpx.AsyncClient(transport=httpx.MockTransport(manejador))


def fuente(manejador, **presupuesto):
    esperas: list[float] = []

    async def dormir(segundos):
        esperas.append(segundos)

    f = FuentePrueba(http=cliente(manejador), budget=SourceBudget(**presupuesto),
                     credentials={}, author_salt=SAL, sleep=dormir)
    return f, esperas


QUERY = SearchQuery(keywords=["invoice"])


async def todos(generador):
    return [x async for x in generador]


class TestErroresTipados(unittest.IsolatedAsyncioTestCase):
    async def test_cada_estado_http_tiene_su_error(self):
        casos = {401: SourceAuthFailed, 403: SourceForbidden, 404: SourceNotFound}
        for estado, error in casos.items():
            f, _ = fuente(lambda _r, e=estado: httpx.Response(e, json={}))
            with self.subTest(estado=estado), self.assertRaises(error) as ctx:
                await todos(f.search(QUERY))
            self.assertEqual(ctx.exception.source, "prueba")

    async def test_un_fallo_nunca_se_convierte_en_cero_resultados(self):
        f, _ = fuente(lambda _r: httpx.Response(500, text="boom"))
        with self.assertRaises(SourceUnavailable):
            await todos(f.search(QUERY))

    async def test_la_red_caida_es_error_tipado(self):
        def sin_red(_r):
            raise httpx.ConnectError("sin red")

        f, _ = fuente(sin_red)
        with self.assertRaises(SourceUnavailable):
            await todos(f.search(QUERY))


class TestCuotas(unittest.IsolatedAsyncioTestCase):
    async def test_un_retry_after_razonable_se_espera_y_se_reintenta(self):
        respuestas = [httpx.Response(429, headers={"Retry-After": "3"}),
                      httpx.Response(200, json={"hits": [{"id": 1, "text": "hola"}]})]
        f, esperas = fuente(lambda _r: respuestas.pop(0))
        items = await todos(f.search(QUERY))
        self.assertEqual(len(items), 1)
        self.assertEqual(esperas, [3.0])
        self.assertEqual(f.budget.spent_requests, 2, "el reintento también cuenta")

    async def test_un_retry_after_largo_se_devuelve_como_error_con_su_espera(self):
        f, esperas = fuente(lambda _r: httpx.Response(429, headers={"Retry-After": "3600"}))
        with self.assertRaises(SourceRateLimited) as ctx:
            await todos(f.search(QUERY))
        self.assertEqual(ctx.exception.retry_after, 3600.0)
        self.assertEqual(esperas, [])

    async def test_los_5xx_se_reintentan_con_espera_creciente(self):
        respuestas = [httpx.Response(503), httpx.Response(503),
                      httpx.Response(200, json={"hits": []})]
        f, esperas = fuente(lambda _r: respuestas.pop(0))
        self.assertEqual(await todos(f.search(QUERY)), [])
        self.assertEqual(len(esperas), 2)
        self.assertLess(esperas[0], esperas[1])

    async def test_las_cabeceras_de_cuota_quedan_registradas(self):
        f, _ = fuente(lambda _r: httpx.Response(200, json={"hits": []}, headers={
            "X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "57", "X-RateLimit-Reset": "1790000000"}))
        await todos(f.search(QUERY))
        self.assertEqual((f.quota.limit, f.quota.remaining, f.quota.reset_epoch),
                         (60, 57, 1790000000.0))


class TestPresupuesto(unittest.IsolatedAsyncioTestCase):
    async def test_agotado_la_peticion_no_sale(self):
        enviadas = []

        def manejador(peticion):
            enviadas.append(peticion)
            return httpx.Response(200, json={"hits": []})

        f, _ = fuente(manejador, max_requests=1)
        await todos(f.search(QUERY))
        with self.assertRaises(SourceBudgetExhausted) as ctx:
            await todos(f.search(QUERY))
        self.assertEqual(len(enviadas), 1)
        self.assertEqual(ctx.exception.code, "source_budget_exhausted")

    async def test_el_tope_de_items_corta_la_busqueda(self):
        hits = [{"id": i, "text": f"texto {i}"} for i in range(5)]
        f, _ = fuente(lambda _r: httpx.Response(200, json={"hits": hits}), max_items=3)
        with self.assertRaises(SourceBudgetExhausted):
            await todos(f.search(QUERY))
        self.assertEqual(f.budget.spent_items, 3)

    def test_los_topes_por_defecto_son_los_de_d_m4(self):
        self.assertEqual((DEFAULT_MAX_REQUESTS, DEFAULT_MAX_ITEMS), (25, 500))


class TestIdentidadYAutoria(unittest.IsolatedAsyncioTestCase):
    async def test_se_identifica_con_un_user_agent_propio(self):
        vistas = []

        def manejador(peticion):
            vistas.append(peticion.headers.get("User-Agent"))
            return httpx.Response(200, json={"hits": []})

        f, _ = fuente(manejador)
        await todos(f.search(QUERY))
        self.assertEqual(vistas, [USER_AGENT])
        self.assertIn("SENTRA", USER_AGENT)
        self.assertNotIn("Mozilla", USER_AGENT, "nada de suplantar un navegador (R4)")

    async def test_el_item_lleva_id_global_procedencia_real_y_autor_hasheado(self):
        f, _ = fuente(lambda _r: httpx.Response(
            200, json={"hits": [{"id": 9, "text": "texto", "user": "alguien_real"}]}))
        [item] = await todos(f.search(QUERY))
        self.assertEqual((item.id, item.source, item.data_source), ("prueba:9", "prueba", "real"))
        self.assertRegex(item.author_hash, r"^[0-9a-f]{64}$")
        self.assertNotIn("alguien_real", item.model_dump_json())


class TestCodigosTraducidos(unittest.TestCase):
    def test_es_y_en_traducen_cada_codigo_de_fuente(self):
        import re
        from pathlib import Path

        from core.sources.errors import TODOS

        raiz = Path(__file__).resolve().parents[1] / "ui" / "src" / "i18n"
        for idioma in ("es", "en"):
            fuente = (raiz / f"{idioma}.ts").read_text(encoding="utf-8")
            bloque = re.search(r"\n  errors: \{(.*?)\n  \},", fuente, re.DOTALL)
            traducidos = set(re.findall(r"^\s+(\w+):", bloque.group(1), re.MULTILINE))
            with self.subTest(idioma=idioma):
                self.assertEqual({e.code for e in TODOS} - traducidos, set())


if __name__ == "__main__":
    unittest.main()
