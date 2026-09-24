"""
Sin restos del nombre antiguo (AUD-066, D-C6)
=============================================

El proyecto se renombró a SENTRA a medias: identificador de Tauri, lib de
Cargo, nombre del servicio del sidecar, User-Agent, clave de preferencias,
canal del arranque y cabeceras de módulos seguían con «Reddit Intelligence
Radar». Aquí se vigila el código y la configuración.

Excepciones deliberadas (D-C6): las migraciones aplicadas están congeladas
(R12), y el nombre de la base de datos y las claves `RIR_*` del `.env` no
son visibles y cambiarlos obligaría a migrar datos y secretos. Los
documentos históricos de planificación tampoco se reescriben.
"""

import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
RESTOS = re.compile(
    r"reddit intelligence radar|reddit-intelligence-radar|radar_lib|radar-desktop"
    r"|rir\.preferences|radar:sidecar",
    re.IGNORECASE,
)
CARPETAS = ("core", "scripts", "tests", "ui/src", "ui/src-tauri/src")
FICHEROS = ("ui/src-tauri/tauri.conf.json", "ui/src-tauri/Cargo.toml", "ui/package.json",
            "requirements.txt", "requirements-dev.txt", ".env.example", ".gitignore")


class TestSinNombreAntiguo(unittest.TestCase):
    def test_ni_el_codigo_ni_la_configuracion_usan_el_nombre_antiguo(self):
        rutas = [p for c in CARPETAS for p in (RAIZ / c).rglob("*")
                 if p.suffix in (".py", ".rs", ".ts", ".tsx", ".json") and p.name != Path(__file__).name]
        rutas += [RAIZ / f for f in FICHEROS]
        restos = [
            f"{p.relative_to(RAIZ)}:{n}"
            for p in rutas
            for n, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1)
            if RESTOS.search(linea)
        ]
        self.assertEqual(restos, [])

    def test_el_identificador_es_el_de_sentra(self):
        import json

        conf = json.loads((RAIZ / "ui/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
        self.assertEqual((conf["productName"], conf["identifier"]), ("SENTRA", "com.sentra.desktop"))


if __name__ == "__main__":
    unittest.main()
