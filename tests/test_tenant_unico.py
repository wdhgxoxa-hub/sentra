"""
Un solo tenant local y ninguna referencia a un esquema que no existe (AUD-067, AUD-069)
======================================================================================

El tenant de la instalación local lo crea la migración 001 y lo repiten Rust
(`LOCAL_TENANT`) y Python (`DEFAULT_TENANT_ID`): son dos lenguajes y no
pueden compartir la constante, así que se comprueba que las tres digan lo
mismo. Y `sql/schema.sql` se convirtió en la migración 001 hace tiempo: el
código no puede seguir mandando a leerlo.
"""

import re
import unittest
from pathlib import Path

from core.storage.postgres_store import DEFAULT_TENANT_ID

RAIZ = Path(__file__).resolve().parents[1]


class TestTenantUnico(unittest.TestCase):
    def test_rust_python_y_la_migracion_dicen_el_mismo_tenant(self):
        rust = (RAIZ / "ui/src-tauri/src/commands/mutations.rs").read_text("utf-8")
        local = re.search(r'const LOCAL_TENANT: &str = "([0-9a-f-]+)";', rust)
        self.assertIsNotNone(local)
        assert local is not None
        migracion = (RAIZ / "sql/migrations/001_initial_schema.sql").read_text("utf-8")
        self.assertEqual(local.group(1), DEFAULT_TENANT_ID)
        self.assertIn(f"'{DEFAULT_TENANT_ID}'", migracion)


class TestSinEsquemaFantasma(unittest.TestCase):
    def test_el_codigo_no_manda_a_un_schema_sql_que_no_existe(self):
        self.assertFalse((RAIZ / "sql" / "schema.sql").exists())
        menciones = [
            f"{p.relative_to(RAIZ)}"
            for carpeta in ("core", "scripts", "ui/src", "ui/src-tauri/src", "docs")
            for p in (RAIZ / carpeta).rglob("*")
            if p.suffix in (".py", ".rs", ".ts", ".tsx", ".md")
            and "sql/schema.sql" in p.read_text("utf-8")
        ]
        self.assertEqual(menciones, [])


if __name__ == "__main__":
    unittest.main()
