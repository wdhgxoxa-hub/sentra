"""
Migración 019: resumen del juez en la ejecución (Fase 1, B3)
============================================================

Decisión de Walter (opción A): `pipeline_runs.judge_summary` guarda el
resumen del juez (piezas, las que pasan el filtro, etiquetadas, dolor,
grupos, veredictos...). Antes solo viajaba en el evento judge:done y el
«38 pasan el filtro» del escaneo del 24-09 no quedaba en ningún sitio;
`filtered_in` seguía a 0 porque es una columna de la pipeline antigua que
el flujo multifuente nunca escribió. Las columnas antiguas quedan
documentadas como «pipeline antigua, sin uso».
"""

import json
import unittest

from core.storage.postgres_store import PostgresStore, run_async
from tests._postgres import postgres_available
from tests.test_migracion_015 import BaseHasta014

SIN_USO = ("filtered_in", "filtered_out", "analyzed", "qualified", "rejected", "cycles", "last_cursor",
           "graph_version")


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestMigracion019(BaseHasta014):

    def test_las_ejecuciones_anteriores_quedan_sin_resumen(self):
        self.assertEqual(self._sql("SELECT judge_summary FROM pipeline_runs"), [(None,)])

    def test_el_resumen_del_juez_se_guarda_en_la_ejecucion(self):
        from core.judge.store import guardar_resumen_del_juez

        [(run,)] = self._sql("SELECT id::text FROM pipeline_runs")
        resumen = {"items": 470, "kept": 38, "labeled": 38, "pain": 1, "clusters": 0, "verdicts": {}}

        async def guardar():
            async with PostgresStore(dsn=self.dsn) as store:
                await guardar_resumen_del_juez(store, run, resumen)

        run_async(guardar())
        [(guardado,)] = self._sql("SELECT judge_summary FROM pipeline_runs")
        self.assertEqual(guardado, json.loads(json.dumps(resumen)))

    def test_las_columnas_de_la_pipeline_antigua_estan_documentadas(self):
        comentarios = dict(self._sql(
            "SELECT a.attname, col_description(a.attrelid, a.attnum) FROM pg_attribute a "
            "WHERE a.attrelid = 'radar.pipeline_runs'::regclass AND a.attnum > 0"))
        for columna in SIN_USO:
            with self.subTest(columna=columna):
                self.assertIn("pipeline antigua, sin uso", comentarios[columna] or "")


if __name__ == "__main__":
    unittest.main()
