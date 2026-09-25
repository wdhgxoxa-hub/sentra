"""
Persistencia de un escaneo multifuente (F2.5)
=============================================

Se guarda todo lo traído (los duplicados también: evidence_duplicates
apunta a filas reales), después el crossposting, los vectores de los
canónicos reutilizando los ya calculados, y la ejecución se cierra con los
fallos por fuente. Cada fuente que respondió de verdad queda verificada
con hora; la que falló, en error con su código.
"""

import unittest
from datetime import UTC, datetime
from typing import Any

from core.evidence.model import EvidenceItem
from core.sources.dedup import Duplicate
from core.sources.persist import persist_multiscan, record_source_outcomes
from core.sources.registry import InMemorySourcesState
from core.sources.scan import MultiScanResult, SourceProgress
from tests._ayudas import presente

AHORA = datetime(2026, 9, 1, tzinfo=UTC)


def item(fuente, nativo, texto="queja"):
    return EvidenceItem(
        id=f"{fuente}:{nativo}", source=fuente, community="c", kind="post", text=texto,
        url=f"https://example.com/{nativo}", author_hash=None, created_at=AHORA,
        fetched_at=AHORA, data_source="real",
    )


class AlmacenDoble:
    def __init__(self):
        self.llamadas = []

    async def upsert_evidence(self, items, run_id=None):
        self.llamadas.append(("evidencia", [i.id for i in items], run_id))
        return len(items)

    async def save_duplicates(self, duplicates):
        self.llamadas.append(("duplicados", [d.duplicate_id for d in duplicates]))
        return len(duplicates)

    async def save_source_outcomes(self, run_id, outcomes):
        self.llamadas.append(("fuentes", run_id, [(o.source, o.status, o.stop_reason) for o in outcomes]))
        return len(outcomes)

    async def finish_run(self, run_id, stats, errors=(), status="completed", **_):
        self.llamadas.append(("cierre", run_id, dict(stats), list(errors), status))

    async def purge_expired_evidence(self, source, days):
        self.llamadas.append(("purga", source, days))
        return [f"{source}:caducado"]


class VectoresDoble:
    def __init__(self):
        self.recibido: tuple[list[str], dict[str, Any]] | None = None

    def upsert(self, items, vectors=None):
        self.recibido = ([i.id for i in items], dict(vectors or {}))
        return len(items)

    def delete(self, ids):
        self.borrados = list(ids)


def resultado():
    original, copia, otro = item("hn", "1"), item("se", "9"), item("hn", "2")
    return MultiScanResult(
        items=[original, otro],
        duplicates=[Duplicate("se:9", "hn:1", "fingerprint", None)],
        fetched=[original, copia, otro],
        vectors={"hn:1": [1.0, 0.0], "se:9": [1.0, 0.0], "hn:2": [0.0, 1.0]},
        per_source={
            "hn": SourceProgress("hn", status="done", items=2, requests=3),
            "se": SourceProgress("se", status="failed", items=1, error_code="source_rate_limited",
                                 detail="HTTP 429"),
        },
    )


class TestPersistencia(unittest.IsolatedAsyncioTestCase):
    async def test_guarda_todo_lo_traido_antes_que_los_duplicados(self):
        almacen = AlmacenDoble()
        await persist_multiscan(almacen, "run-1", resultado())
        self.assertEqual(almacen.llamadas[0], ("evidencia", ["hn:1", "se:9", "hn:2"], "run-1"))
        self.assertEqual(almacen.llamadas[1], ("duplicados", ["se:9"]))

    async def test_cierra_la_ejecucion_con_los_fallos_por_fuente(self):
        almacen = AlmacenDoble()
        await persist_multiscan(almacen, "run-1", resultado())
        _, run_id, stats, errores, estado = almacen.llamadas[-1]
        self.assertEqual(run_id, "run-1")
        self.assertEqual((stats["fetched"], stats["stored"]), (3, 3))
        self.assertEqual(errores, ["se: source_rate_limited (HTTP 429)"])
        self.assertEqual(estado, "completed")

    async def test_guarda_como_termino_cada_fuente_antes_de_cerrar(self):
        # Fase 1, B4: el motivo de parada de una fuente (YouTube por su presupuesto)
        # queda en run_source_outcomes; antes solo viajaba a la interfaz.
        almacen = AlmacenDoble()
        cortado = resultado()
        cortado.per_source["yt"] = SourceProgress("yt", status="done", items=419,
                                                  stop_reason="source_budget_exhausted")
        await persist_multiscan(almacen, "run-1", cortado)
        fuentes = [llamada for llamada in almacen.llamadas if llamada[0] == "fuentes"]
        self.assertEqual(fuentes, [("fuentes", "run-1", [("hn", "done", None), ("se", "failed", None),
                                                         ("yt", "done", "source_budget_exhausted")])])
        self.assertEqual(almacen.llamadas[-1][0], "cierre")

    async def test_si_todas_fallan_sin_traer_nada_la_ejecucion_falla(self):
        almacen = AlmacenDoble()
        vacio = MultiScanResult(per_source={
            "hn": SourceProgress("hn", status="failed", error_code="source_unavailable"),
        })
        await persist_multiscan(almacen, "run-2", vacio)
        self.assertEqual(almacen.llamadas[-1][-1], "failed")

    async def test_un_escaneo_cancelado_cierra_la_ejecucion_como_cancelada(self):
        almacen = AlmacenDoble()
        cancelado = resultado()
        cancelado.cancelled = True
        resumen = await persist_multiscan(almacen, "run-3", cancelado)
        self.assertEqual(almacen.llamadas[-1][-1], "cancelled")
        self.assertEqual(resumen["status"], "cancelled")
        # Lo traído hasta la cancelación se guarda igual (AUD-010).
        self.assertEqual(almacen.llamadas[0][1], ["hn:1", "se:9", "hn:2"])

    async def test_purga_lo_caducado_de_las_fuentes_con_retencion(self):
        # Políticas de YouTube: refrescar o borrar en 30 días; también los vectores.
        almacen, vectores = AlmacenDoble(), VectoresDoble()
        resumen = await persist_multiscan(almacen, "run-1", resultado(), vector_store=vectores,
                                          retention={"youtube": 30})
        self.assertIn(("purga", "youtube", 30), almacen.llamadas)
        self.assertEqual(vectores.borrados, ["youtube:caducado"])
        self.assertEqual(resumen["purged"], 1)

    async def test_sin_retencion_no_se_purga_nada(self):
        almacen = AlmacenDoble()
        await persist_multiscan(almacen, "run-1", resultado())
        self.assertFalse([llamada for llamada in almacen.llamadas if llamada[0] == "purga"])

    async def test_los_vectores_son_de_los_canonicos_y_se_reutilizan(self):
        vectores = VectoresDoble()
        await persist_multiscan(AlmacenDoble(), "run-1", resultado(), vector_store=vectores)
        ids, dados = presente(vectores.recibido)
        self.assertEqual(ids, ["hn:1", "hn:2"])
        self.assertEqual(set(dados), {"hn:1", "se:9", "hn:2"})


class TestEstadoDeFuentes(unittest.TestCase):
    def test_la_que_respondio_queda_verificada_y_la_que_fallo_en_error(self):
        estado = InMemorySourcesState()
        record_source_outcomes(estado, resultado().per_source, now=AHORA)
        hn, se = presente(estado.get("hn")), presente(estado.get("se"))
        self.assertEqual((hn.status, hn.last_verified_at), ("verificada", AHORA))
        self.assertEqual((se.status, se.error_code), ("error", "source_rate_limited"))

    def test_un_presupuesto_agotado_no_es_un_error(self):
        estado = InMemorySourcesState()
        record_source_outcomes(estado, {"hn": SourceProgress(
            "hn", status="done", items=5, requests=2, stop_reason="source_budget_exhausted")},
            now=AHORA)
        self.assertEqual(presente(estado.get("hn")).status, "verificada")

    def test_sin_ninguna_peticion_no_hubo_respuesta_que_verifique(self):
        estado = InMemorySourcesState()
        record_source_outcomes(estado, {"hn": SourceProgress("hn", status="done", requests=0)},
                               now=AHORA)
        self.assertIsNone(estado.get("hn"))


if __name__ == "__main__":
    unittest.main()
