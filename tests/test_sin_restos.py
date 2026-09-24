"""
Sin restos de la biblioteca de repositorios (AUD2-017, DP11 A)
==============================================================

El proyecto empezó como una biblioteca de 57 repositorios clonados (1,6 GB en
repos/) con su especificación, su plan y su matriz de selección. SENTRA no
los usa: los clones viven fuera, en F:\\archivo_sentra\\repos, y esos
documentos en docs/historico/, con una nota que dice de dónde vienen.
"""

import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
HISTORICO = RAIZ / "docs" / "historico"
ARCHIVADOS = {
    "SPECIFICATION.md": "SPECIFICATION.md",
    "PLAN.md": "PLAN.md",
    "docs/ARQUITECTURA_POSTGRES_Y_FRONTEND.md": "ARQUITECTURA_POSTGRES_Y_FRONTEND.md",
    "docs/MATRIZ_SELECCION_BEST_OF_BREED.md": "MATRIZ_SELECCION_BEST_OF_BREED.md",
    "tasks/SPEC-blueprint.md": "SPEC-blueprint.md",
}
SCRIPTS_DE_CLONES = (
    "scripts/clone_manager.py", "scripts/clone_batch2.py", "scripts/generate_index.py",
    "scripts/repo_analyzer.py", "scripts/verify_integrity.py", "scripts/test_radar.py",
    "scripts/update_results.py", "scripts/print_report.py", "scripts/test_candidates.py",
    "logs/repo_catalog.json",
)


class TestSinRestos(unittest.TestCase):
    def test_los_clones_no_viven_en_el_proyecto(self):
        self.assertFalse((RAIZ / "repos").exists())

    def test_los_documentos_de_la_biblioteca_estan_en_historico(self):
        for antes, ahora in ARCHIVADOS.items():
            with self.subTest(documento=antes):
                self.assertFalse((RAIZ / antes).exists())
                self.assertTrue((HISTORICO / ahora).is_file())

    def test_los_scripts_de_la_biblioteca_de_clones_no_viven_en_el_proyecto(self):
        # Sin los clones no tienen uso; se archivaron en F:\archivo_sentra\scripts.
        for resto in SCRIPTS_DE_CLONES:
            with self.subTest(resto=resto):
                self.assertFalse((RAIZ / resto).exists())

    def test_el_historico_explica_de_donde_viene(self):
        nota = (HISTORICO / "LEEME.md").read_text("utf-8")
        self.assertIn("F:\\archivo_sentra\\repos", nota)
        for ahora in ARCHIVADOS.values():
            self.assertIn(ahora, nota)


if __name__ == "__main__":
    unittest.main()
