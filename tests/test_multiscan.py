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
from typing import Any

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
    return clase(http=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(599))),
                 budget=SourceBudget(**presupuesto), credentials={}, author_salt=SAL)


class Buena(Base):
    id = "buena"
    display_name = "Buena"
    textos: tuple[str, ...] = ("queja uno", "queja dos")


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
        eventos: list[dict[str, Any]] = []
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

    async def test_una_fuente_omitida_consta_con_su_motivo_y_sin_peticiones(self):
        """Medida B (Fase 3): lo que no encaja con el tema no se consulta y se dice."""
        resultado = await run_multisource_scan([fuente(Buena)], QUERY,
                                               omitidas={"github": "omitida:no_es_software"})
        github = resultado.per_source["github"]
        self.assertEqual((github.status, github.stop_reason, github.items, github.requests),
                         ("done", "omitida:no_es_software", 0, 0))
        self.assertEqual(resultado.per_source["buena"].status, "done")

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

    async def test_conserva_todo_lo_traido_para_guardar_los_duplicados(self):
        # evidence_duplicates apunta a las dos filas: la copia también se guarda.
        resultado = await run_multisource_scan([fuente(Original), fuente(Copiona)], QUERY)
        self.assertEqual({i.id for i in resultado.fetched}, {"original:0", "copiona:0"})

    async def test_devuelve_los_vectores_calculados_para_no_repetirlos(self):
        def embed(items):
            return {i.id: [1.0, float(n)] for n, i in enumerate(items)}

        resultado = await run_multisource_scan([fuente(Buena)], QUERY, embed=embed)
        self.assertEqual(set(resultado.vectors), {"buena:0", "buena:1"})

    async def test_cancelar_para_cada_fuente_y_conserva_lo_traido(self):
        class Larga(Buena):
            id = "larga"
            textos = tuple(f"queja {n}" for n in range(20))

        pedido = {"parar": False}

        def al_evento(evento):
            if evento["type"] == "source:progress":
                pedido["parar"] = True

        resultado = await run_multisource_scan(
            [fuente(Larga)], QUERY, on_event=al_evento, should_stop=lambda: pedido["parar"])
        larga = resultado.per_source["larga"]
        self.assertTrue(resultado.cancelled)
        self.assertEqual((larga.status, larga.stop_reason), ("done", "cancelled"))
        self.assertLess(larga.items, 20)
        self.assertEqual(len(resultado.fetched), larga.items, "lo traído antes se conserva")

    async def test_sin_cancelar_no_consta_como_cancelado(self):
        resultado = await run_multisource_scan([fuente(Buena)], QUERY, should_stop=lambda: False)
        self.assertFalse(resultado.cancelled)

    async def test_los_vectores_se_calculan_fuera_del_bucle_del_servidor(self):
        # e5-large tarda segundos: en el bucle bloquearía al sidecar entero.
        import threading

        hilos = []

        def embed(items):
            hilos.append(threading.current_thread())
            return {}

        await run_multisource_scan([fuente(Buena)], QUERY, embed=embed)
        self.assertIsNot(hilos[0], threading.current_thread())

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


class Abundante(Base):
    """Trae `cuantas` piezas distintas (fecha fija: la hora no da para 600)."""

    cuantas = 0

    async def search(self, query):
        for n in range(self.cuantas):
            yield self._item(nativo=str(n), community="c", kind="post",
                             text=f"queja distinta número {n} de la fuente {self.id} con bastante texto",
                             url=f"https://example.com/{self.id}/{n}", author=f"u{n}",
                             created_at=datetime(2026, 9, 1, tzinfo=UTC))


def abundante(nombre: str, cuantas: int):
    clase = type(nombre, (Abundante,), {"id": nombre, "display_name": nombre, "cuantas": cuantas})
    return fuente(clase)


class TestRepartoEntreFuentes(unittest.IsolatedAsyncioTestCase):
    """Fase 3 (Walter): en el escaneo 1, YouTube trajo 500 de 512 piezas. Ninguna
    fuente se lleva más de la mitad del cupo del escaneo; lo que no usan las
    fuentes sin resultados queda para las que sí traen, dentro de su mitad."""

    async def test_una_fuente_abundante_no_pasa_de_la_mitad_del_cupo(self):
        from core.sources.scan import CUPO_POR_ESCANEO

        r = await run_multisource_scan([abundante("mucha", 600), abundante("poca", 30)], QUERY)
        self.assertEqual(r.per_source["mucha"].items, CUPO_POR_ESCANEO // 2)
        self.assertEqual(r.per_source["mucha"].stop_reason, "source_budget_exhausted")
        self.assertEqual(r.per_source["poca"].items, 30)

    async def test_el_total_no_pasa_del_cupo_y_nadie_pasa_de_la_mitad(self):
        from core.sources.scan import CUPO_POR_ESCANEO

        r = await run_multisource_scan([abundante(f"f{n}", 400) for n in range(3)], QUERY)
        cuentas = [p.items for p in r.per_source.values()]
        self.assertLessEqual(sum(cuentas), CUPO_POR_ESCANEO)
        self.assertTrue(all(c <= CUPO_POR_ESCANEO // 2 for c in cuentas), cuentas)
        self.assertEqual(sum(cuentas), CUPO_POR_ESCANEO, "el cupo libre se reparte hasta llenarse")

    async def test_el_cupo_es_por_escaneo_y_no_se_arrastra_al_siguiente(self):
        fuentes = [abundante("sola", 300)]
        await run_multisource_scan(fuentes, QUERY)
        fuentes[0].budget.spent_items = 0
        r = await run_multisource_scan(fuentes, QUERY)
        self.assertEqual(r.per_source["sola"].items, 250)
