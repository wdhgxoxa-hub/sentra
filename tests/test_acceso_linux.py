"""
Acceso del lanzador en Linux
============================

En Windows el acceso era `Desktop\\SENTRA.lnk` → `sentra.exe`. En Linux es una
entrada de escritorio: `scripts/linux/sentra.desktop.in` rellena con la raíz
real del repo por `python -m scripts.acceso_linux`. Solo se instala en
`$XDG_DATA_HOME/applications/sentra.desktop`; `--en-seco` no escribe nada.
"""

from __future__ import annotations

import configparser
import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts import acceso_linux

RAIZ = Path(__file__).resolve().parents[1]


def _leer_entrada(texto: str) -> configparser.SectionProxy:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[assignment,method-assign]
    parser.read_string(texto)
    return parser["Desktop Entry"]


class TestAccesoLinux(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_acceso_linux_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.datos = self.tmp / "datos"
        self.entorno = {
            "HOME": str(self.tmp / "casa"),
            "XDG_DATA_HOME": str(self.datos),
        }
        self.destino = self.datos / "applications" / "sentra.desktop"

    def _main(self, *argumentos: str) -> tuple[int, str, str]:
        salida, errores = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
            codigo = acceso_linux.main(list(argumentos), entorno=self.entorno)
        return codigo, salida.getvalue(), errores.getvalue()

    def test_la_entrada_tiene_las_claves_y_rutas_del_repo(self) -> None:
        entrada = _leer_entrada(acceso_linux.renderizar(RAIZ))
        self.assertEqual(entrada["Type"], "Application")
        self.assertEqual(entrada["Name"], "SENTRA")
        self.assertEqual(entrada["Terminal"], "false")
        self.assertTrue(entrada["Comment"])
        self.assertTrue(entrada["Categories"].endswith(";"))
        self.assertEqual(entrada["StartupWMClass"], "sentra")
        exe = Path(entrada["Exec"])
        self.assertEqual(
            exe, RAIZ / "ui" / "src-tauri" / "target" / "release" / "sentra"
        )
        self.assertEqual(Path(entrada["Path"]), RAIZ)
        icono = Path(entrada["Icon"])
        self.assertTrue(icono.is_file(), icono)
        self.assertEqual(icono.suffix, ".png")
        for clave in ("Exec", "Path", "Icon"):
            with self.subTest(clave=clave):
                ruta = Path(entrada[clave])
                self.assertTrue(ruta.is_absolute())
                self.assertTrue(ruta.is_relative_to(RAIZ))
        self.assertNotIn("@", acceso_linux.renderizar(RAIZ))

    def test_el_destino_sigue_xdg_data_home_y_si_no_home(self) -> None:
        self.assertEqual(acceso_linux.destino_permitido(self.entorno), self.destino)
        solo_home = {"HOME": "/casa/walter"}
        self.assertEqual(
            acceso_linux.destino_permitido(solo_home),
            Path("/casa/walter/.local/share/applications/sentra.desktop"),
        )
        # La especificación XDG ignora una XDG_DATA_HOME relativa.
        relativa = {"HOME": "/casa/walter", "XDG_DATA_HOME": "datos"}
        self.assertEqual(
            acceso_linux.destino_permitido(relativa),
            Path("/casa/walter/.local/share/applications/sentra.desktop"),
        )

    def test_en_seco_no_escribe_nada_y_ensena_destino_y_entrada(self) -> None:
        codigo, salida, errores = self._main("--en-seco")
        self.assertEqual(codigo, 0, errores)
        self.assertIn(str(self.destino), salida)
        self.assertIn("[Desktop Entry]", salida)
        self.assertFalse(self.datos.exists())

    def test_en_seco_avisa_sin_fallar_si_falta_el_binario(self) -> None:
        falso = self.tmp / "no_existe" / "sentra"
        codigo, _, errores = self._main("--en-seco", "--binario", str(falso))
        self.assertEqual(codigo, 0)
        self.assertIn("Aviso", errores)
        self.assertFalse(self.datos.exists())

    def test_escribir_sin_binario_se_niega(self) -> None:
        falso = self.tmp / "no_existe" / "sentra"
        codigo, _, errores = self._main("--binario", str(falso))
        self.assertNotEqual(codigo, 0)
        self.assertIn("release", errores)
        self.assertFalse(self.destino.exists())

    def test_otra_ruta_destino_se_rechaza(self) -> None:
        for otra in (
            self.tmp / "otra" / "sentra.desktop",
            self.datos / "applications" / "otro.desktop",
            Path("/usr/share/applications/sentra.desktop"),
        ):
            with self.subTest(destino=str(otra)):
                codigo, _, errores = self._main("--destino", str(otra))
                self.assertNotEqual(codigo, 0)
                self.assertIn("Me niego", errores)
                self.assertFalse(otra.exists())
        self.assertFalse(self.datos.exists())

    def test_instalar_escribe_solo_en_el_destino_permitido(self) -> None:
        binario = self.tmp / "sentra"
        binario.write_bytes(b"")
        codigo, _, errores = self._main("--binario", str(binario))
        self.assertEqual(codigo, 0, errores)
        self.assertEqual(
            self.destino.read_text(encoding="utf-8"), acceso_linux.renderizar(RAIZ)
        )
        self.assertEqual(
            list(self.datos.rglob("*")), [self.destino.parent, self.destino]
        )

    def test_una_raiz_con_caracteres_que_romperian_exec_se_rechaza(self) -> None:
        for mala in ("/home/walter/mi repo", "/tmp/a%b", "/tmp/x\nExec=rm"):
            with self.subTest(raiz=repr(mala)), self.assertRaises(ValueError):
                acceso_linux.renderizar(Path(mala))


if __name__ == "__main__":
    unittest.main()
