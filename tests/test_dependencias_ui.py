"""
Las dependencias de la interfaz tienen quien las use (AUD-060)
==============================================================

Igual que tests/test_requirements.py con Python: cada paquete de
`dependencies` en ui/package.json tiene que importarse desde ui/src o desde
vite.config.ts. El plugin shell de Tauri se inicializaba sin que nada lo
usara, y el Markdown del Arquitecto siguió declarado tras retirarlo.
"""

import json
import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1] / "ui"


def codigo_de_la_ui() -> str:
    fuentes = [p for p in (UI / "src").rglob("*") if p.suffix in (".ts", ".tsx")]
    fuentes.append(UI / "vite.config.ts")
    return "\n".join(p.read_text(encoding="utf-8") for p in fuentes)


class TestDependenciasDeLaUi(unittest.TestCase):
    def test_cada_dependencia_se_importa(self):
        paquete = json.loads((UI / "package.json").read_text(encoding="utf-8"))
        codigo = codigo_de_la_ui()
        sin_uso = [
            nombre for nombre in paquete.get("dependencies", {})
            if not re.search(rf"""from ["']{re.escape(nombre)}(/[^"']*)?["']""", codigo)
        ]
        self.assertEqual(sin_uso, [])


if __name__ == "__main__":
    unittest.main()
