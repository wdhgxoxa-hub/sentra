"""
Migración 016: nombre del problema y caché de G0
===============================================

Decisiones del usuario tras E8: el Radar usa el mismo nombre que el dossier
(el que da G0 a un grupo que es un mismo problema, en es y en en) y la
comprobación de coherencia es estable: su resultado se guarda por grupo y no
se repite. `niche_verdicts.problem_name` es jsonb y nulo en mezclas y en los
veredictos anteriores; `coherence_checks` guarda un resultado por hash del
grupo y versión del revisor.
"""

import json
import unittest

from tests._postgres import postgres_available
from tests.test_migracion_015 import TENANT, BaseHasta014


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestMigracion016(BaseHasta014):

    def test_los_veredictos_anteriores_quedan_sin_nombre(self):
        self.assertEqual(self._sql("SELECT cluster_key, problem_name FROM niche_verdicts ORDER BY cluster_key"),
                         [("mezcla", None), ("nicho", None)])

    def test_un_veredicto_guarda_su_nombre_en_los_dos_idiomas(self):
        nombre = {"es": "Perseguir facturas impagadas", "en": "Chasing unpaid invoices"}
        self._sql("UPDATE niche_verdicts SET problem_name = %s WHERE cluster_key = 'nicho'", (json.dumps(nombre),))
        [(leido,)] = self._sql("SELECT problem_name FROM niche_verdicts WHERE cluster_key = 'nicho'")
        self.assertEqual(leido, nombre)

    def test_la_cache_de_g0_guarda_uno_por_grupo_y_revisor(self):
        import psycopg

        hash_ = "a" * 64
        self._sql("INSERT INTO coherence_checks (tenant_id, group_hash, checker, result) VALUES (%s, %s, 'c3/m', '{}')",
                  (TENANT, hash_))
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self._sql("INSERT INTO coherence_checks (tenant_id, group_hash, checker, result) "
                      "VALUES (%s, %s, 'c3/m', '{}')", (TENANT, hash_))
        with self.assertRaises(psycopg.errors.CheckViolation):
            self._sql("INSERT INTO coherence_checks (tenant_id, group_hash, checker, result) "
                      "VALUES (%s, 'no-es-un-hash', 'c3/m', '{}')", (TENANT,))


if __name__ == "__main__":
    unittest.main()
