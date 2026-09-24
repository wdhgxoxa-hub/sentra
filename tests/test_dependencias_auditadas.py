"""
Dependencias auditadas (AUD2-021, DP7 A)
=======================================

`pip-audit` y `cargo audit` son herramientas de desarrollo; la compuerta las
corre con AUDIT=1 y toda release pasa por ellas (README).

`cargo audit` lee el Cargo.lock y avisa de RUSTSEC-2023-0071 (rsa 0.9, ataque
Marvin, sin versión corregida). sqlx 0.8 deja en el lockfile a sqlx-mysql y
sus dependencias aunque SENTRA solo compile PostgreSQL: rsa no entra en el
grafo de ningún objetivo ni se compila. Por eso se ignora en
ui/src-tauri/.cargo/audit.toml, y este test hace que el ignorado solo valga
mientras siga siendo cierto: si rsa entra en el grafo, falla.
"""

import shutil
import subprocess
import tomllib
import unittest
from pathlib import Path

TAURI = Path(__file__).resolve().parents[1] / "ui" / "src-tauri"
IGNORADOS = {"RUSTSEC-2023-0071": "rsa"}


class TestDependenciasAuditadas(unittest.TestCase):
    def test_solo_se_ignora_lo_justificado(self):
        config = tomllib.loads((TAURI / ".cargo" / "audit.toml").read_text("utf-8"))
        self.assertEqual(set(config["advisories"]["ignore"]), set(IGNORADOS))

    @unittest.skipUnless(shutil.which("cargo"), "sin cargo")
    def test_lo_ignorado_no_entra_en_el_grafo_de_ningun_objetivo(self):
        for crate in IGNORADOS.values():
            with self.subTest(crate=crate):
                salida = subprocess.run(
                    ["cargo", "tree", "--offline", "-i", crate, "--target", "all", "-e", "normal,build"],
                    cwd=TAURI, capture_output=True, text=True, check=False)
                self.assertIn("nothing to print", salida.stderr + salida.stdout,
                              f"{crate} ha entrado en el grafo: el ignorado de audit.toml ya no vale")


if __name__ == "__main__":
    unittest.main()
