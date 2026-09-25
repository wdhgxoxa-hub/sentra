"""
Las bases desechables se borran sin FORCE
=========================================

Con el rol sentra_pruebas (sin superusuario), `DROP DATABASE ... WITH (FORCE)`
fallaba a ratos: «se ha denegado el permiso para terminar el proceso».
Cazado el 2026-09-24: eran procesos de autovacuum sobre bases recién creadas
(rir_evidence_store_test, rir_migracion_012_test, rir_migracion_015_test).
FORCE intenta matar todo proceso de la base y un rol sin superusuario no
puede matar un autovacuum. Sin FORCE, el servidor cancela el autovacuum por
su cuenta; las sesiones propias que queden las cierra antes
`borrar_base_de_prueba` (mismo rol: permitido). Nada de pg_signal_backend:
dejaría a los tests matar sesiones de otros proyectos.
"""

import re
import unittest
from pathlib import Path

from tests._postgres import ADMIN_DSN, postgres_available

TESTS = Path(__file__).resolve().parent
NOMBRE = "rir_borrado_de_prueba_test"


class TestSinForce(unittest.TestCase):
    def test_ningun_test_borra_bases_con_force(self):
        con_force = [f"{p.name}:{n}" for p in sorted(TESTS.glob("*.py")) if p.name != Path(__file__).name
                     for n, linea in enumerate(p.read_text("utf-8").splitlines(), start=1)
                     if re.search(r"WITH\s*\(\s*FORCE", linea, re.IGNORECASE)]
        self.assertEqual(con_force, [])

    def test_solo_borra_bases_desechables(self):
        from tests._postgres import borrar_base_de_prueba

        for nombre in ("reddit_intelligence_radar", "postgres", "dsfactory_test", "rir_sin_sufijo"):
            with self.subTest(nombre), self.assertRaises(ValueError):
                borrar_base_de_prueba(nombre)


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestBorrar(unittest.TestCase):
    def test_cierra_las_sesiones_propias_y_borra_la_base(self):
        import psycopg

        from tests._postgres import borrar_base_de_prueba

        borrar_base_de_prueba(NOMBRE)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{NOMBRE}"')
        olvidada = psycopg.connect(ADMIN_DSN.replace("dbname=postgres", f"dbname={NOMBRE}"))
        self.addCleanup(olvidada.close)

        borrar_base_de_prueba(NOMBRE)

        with psycopg.connect(ADMIN_DSN) as conn:
            fila = conn.execute("SELECT count(*) FROM pg_database WHERE datname = %s", (NOMBRE,)).fetchone()
        self.assertEqual(fila, (0,))

    def test_borrar_una_base_que_no_existe_no_falla(self):
        from tests._postgres import borrar_base_de_prueba

        borrar_base_de_prueba("rir_nunca_creada_test")


if __name__ == "__main__":
    unittest.main()
