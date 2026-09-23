"""
Escaneo multifuente en paralelo (F2.5)
======================================

Cada fuente corre en paralelo con su presupuesto. El fallo de una se
registra con su código y NO detiene a las demás; lo que trajo antes de
fallar es evidencia real y se conserva. Un presupuesto agotado no es un
fallo: la fuente termina con ese motivo. Al final se deduplica.
"""

import asyncio
import unittest
from datetime import UTC, datetime

import httpx

from core.evidence.model import SearchQuery
from core.sources.base import CostModel, SourceAdapter
from core.sources.budget import SourceBudget
from core.sources.errors import SourceAuthFailed
from core.sources.scan import run_multisource_scan

SAL = "4e" * 32
QUERY = SearchQuery(keywords=["invoice"])
LARGO = "I export every invoice by hand into a spreadsheet each month and it takes hours of work."


class Base(SourceAdapter):
    terms_url = "https://example.com/t"
    commercial_use_allowed = True
    requires_credentials = False
    cost_model = CostModel(unit="request")
    textos: tuple[str, ...] = ()
    falla_tras: int | None = None
    retraso = 0.0

    async def probe(self):  # pragma: no cover
        raise NotImplementedError

    async def search(self, query):
        for n, texto in enumerate(self.textos):
            if self.falla_tras is not None and n == self.falla_tras:
                raise SourceAuthFailed(self.id, "HTTP 401")
            await asyncio.sleep(self.retraso)
            yield self._item(nativo=str(n), community="c", kind="post", text=texto,
                             url=f"https://example.com/{self.id}/{n}", author=f"u{n}",
                             created_at=datetime(2026, 9, 1, n, tzinfo=UTC))


def fuente(clase, **presupuesto):
    return clase(http=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: None)),
                 budget=SourceBudget(**presupuesto), credentials={}, author_salt=SAL)


class Buena(Base):
    id = "buena"
    display_name = "Buena"
    textos = ("queja uno", "queja dos")


class Rota(Base):
    id = "rota"
    display_name = "Rota"
    textos = ("antes del fallo", "nunca llega")
    falla_tras = 1


class Copiona(Base):
    id = "copiona"
    display_name = "Copiona"
    textos = (LARGO,)


class Original(Base):
    id = "original"
    display_name = "Original"
    textos = (LARGO,)


class TestParalelo(unittest.IsolatedAsyncioTestCase):
    async def test_el_fallo_de_una_fuente_no_detiene_las_demas(self):
        eventos = []
        resultado = await run_multisource_scan(
            [fuente(Buena), fuente(Rota)], QUERY, on_event=eventos.append)
        self.assertEqual(resultado.per_source["buena"].status, "done")
        rota = resultado.per_source["rota"]
        self.assertEqual((rota.status, rota.error_code, rota.items), ("failed", "source_auth_failed", 1))
        ids = {i.id for i in resultado.items}
        self.assertEqual(ids, {"buena:0", "buena:1", "rota:0"}, "lo traído antes del fallo se conserva")
        tipos = {(e["type"], e["source"]) for e in eventos}
        self.assertIn(("source:error", "rota"), tipos)
        self.assertIn(("source:done", "buena"), tipos)

    async def test_un_presupuesto_agotado_termina_la_fuente_sin_fallarla(self):
        resultado = await run_multisource_scan([fuente(Buena, max_items=1)], QUERY)
        estado = resultado.per_source["buena"]
        self.assertEqual((estado.status, estado.stop_reason, estado.items),
                         ("done", "source_budget_exhausted", 1))

    async def test_corren_a_la_vez(self):
        class Lenta(Buena):
            id = "lenta"
            retraso = 0.2

        class OtraLenta(Buena):
            id = "otra"
            retraso = 0.2

        inicio = asyncio.get_running_loop().time()
        await run_multisource_scan([fuente(Lenta), fuente(OtraLenta)], QUERY)
        self.assertLess(asyncio.get_running_loop().time() - inicio, 0.7)

    async def test_el_crossposting_entre_fuentes_se_deduplica(self):
        resultado = await run_multisource_scan([fuente(Original), fuente(Copiona)], QUERY)
        self.assertEqual(len(resultado.items), 1)
        self.assertEqual(len(resultado.duplicates), 1)

    async def test_un_error_inesperado_de_una_fuente_tampoco_detiene_las_demas(self):
        class Explota(Buena):
            id = "explota"

            async def search(self, query):
                raise RuntimeError("fallo de programación")
                yield  # pragma: no cover

        resultado = await run_multisource_scan([fuente(Buena), fuente(Explota)], QUERY)
        self.assertEqual(resultado.per_source["explota"].error_code, "internal_error")
        self.assertEqual(len(resultado.items), 2)


if __name__ == "__main__":
    unittest.main()
