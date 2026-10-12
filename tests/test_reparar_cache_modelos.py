"""
Reparación de la caché de modelos traída de Windows (2026-10-12)
================================================================

fastembed avisaba «Local file sizes do not match the metadata» en cada carga:
su `files_metadata.json` tenía rutas de Windows («\\»). scripts/reparar_cache_modelos
reescribe las rutas solo si cada archivo cuadra con el árbol que guardó
huggingface_hub, y nunca borra el archivo viejo (papelera).
"""

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.reparar_cache_modelos import huella, revisar, ruta_posix

REVISION = "52398278842ec682c6f32300af41344b1c0b0bb2"


def id_git(datos: bytes) -> str:
    return hashlib.sha1(f"blob {len(datos)}\0".encode() + datos, usedforsecurity=False).hexdigest()


class TestRepararCache(unittest.TestCase):

    def setUp(self):
        self.cache = Path(tempfile.mkdtemp(prefix="cache_modelos_"))
        self.addCleanup(shutil.rmtree, self.cache, True)
        self.modelo = self.cache / "models--qdrant--prueba"
        instantanea = self.modelo / "snapshots" / REVISION
        instantanea.mkdir(parents=True)
        (self.modelo / "trees").mkdir()
        self.config = b'{"a": 1}'
        self.onnx = b"\x00onnx" * 100
        (instantanea / "config.json").write_bytes(self.config)
        (instantanea / "model.onnx").write_bytes(self.onnx)
        arbol = {"format_version": 1, "files": {
            "config.json": {"size": len(self.config), "blob_id": id_git(self.config)},
            "model.onnx": {"size": len(self.onnx), "blob_id": "puntero",
                           "lfs_sha256": hashlib.sha256(self.onnx).hexdigest()},
        }}
        (self.modelo / "trees" / f"{REVISION}.json").write_text(json.dumps(arbol))
        self.metadatos = self.modelo / "files_metadata.json"
        self.escribir_metadatos("\\")
        self.a_la_papelera: list[Path] = []

    def escribir_metadatos(self, separador: str) -> None:
        self.metadatos.write_text(json.dumps({
            separador.join(("snapshots", REVISION, "config.json")):
                {"size": len(self.config), "blob_id": id_git(self.config)},
            separador.join(("snapshots", REVISION, "model.onnx")):
                {"size": len(self.onnx), "blob_id": "puntero"},
        }))

    def papelera(self, archivo: Path) -> str:
        destino = self.cache / f"papelera_{len(self.a_la_papelera)}"
        archivo.rename(destino)
        self.a_la_papelera.append(destino)
        return "a la papelera"

    def test_las_rutas_de_windows_pasan_a_rutas_con_barra(self):
        self.assertEqual(ruta_posix(f"snapshots\\{REVISION}\\config.json"),
                         f"snapshots/{REVISION}/config.json")
        self.assertEqual(ruta_posix("snapshots/x/config.json"), "snapshots/x/config.json")

    def test_en_seco_no_toca_nada(self):
        antes = self.metadatos.read_text()
        [r] = revisar(self.cache, aplicar=False, papelera=self.papelera)
        self.assertEqual(r.estado, "reparable")
        self.assertEqual(self.metadatos.read_text(), antes)
        self.assertEqual(self.a_la_papelera, [])

    def test_repara_y_manda_el_viejo_a_la_papelera(self):
        antes = self.metadatos.read_text()
        [r] = revisar(self.cache, aplicar=True, papelera=self.papelera)
        self.assertEqual(r.estado, "reparado")
        nuevos = json.loads(self.metadatos.read_text())
        self.assertEqual(sorted(nuevos), [f"snapshots/{REVISION}/config.json",
                                          f"snapshots/{REVISION}/model.onnx"])
        for clave, valor in nuevos.items():
            self.assertEqual((self.modelo / clave).stat().st_size, valor["size"])
        self.assertEqual([p.read_text() for p in self.a_la_papelera], [antes])
        self.assertEqual(revisar(self.cache, aplicar=True, papelera=self.papelera)[0].estado,
                         "bien")

    def test_un_archivo_que_no_cuadra_no_se_da_por_bueno(self):
        (self.modelo / "snapshots" / REVISION / "model.onnx").write_bytes(b"\x01" * len(self.onnx))
        antes = self.metadatos.read_text()
        [r] = revisar(self.cache, aplicar=True, papelera=self.papelera)
        self.assertEqual(r.estado, "dañado")
        self.assertIn("model.onnx: el sha256 no cuadra", r.detalles)
        self.assertEqual(self.metadatos.read_text(), antes)
        self.assertEqual(self.a_la_papelera, [])

    def test_un_archivo_a_medias_no_se_da_por_bueno(self):
        (self.modelo / "snapshots" / REVISION / "config.json").write_bytes(b"{")
        [r] = revisar(self.cache, aplicar=True, papelera=self.papelera)
        self.assertEqual(r.estado, "dañado")
        self.assertEqual(self.a_la_papelera, [])

    def test_una_cache_ya_de_linux_queda_como_esta(self):
        self.escribir_metadatos("/")
        [r] = revisar(self.cache, aplicar=True, papelera=self.papelera)
        self.assertEqual(r.estado, "bien")
        self.assertEqual(self.a_la_papelera, [])

    def test_la_huella_de_git_es_la_de_git(self):
        # `git hash-object` de un archivo vacío.
        vacio = self.cache / "vacio"
        vacio.write_bytes(b"")
        self.assertEqual(huella(vacio, sha256=False), "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")


if __name__ == "__main__":
    unittest.main()
