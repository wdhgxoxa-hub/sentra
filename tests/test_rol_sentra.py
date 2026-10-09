"""
El script que crea los roles de SENTRA (scripts/rol_sentra.py)
==============================================================

Lo ejecuta Walter una vez, como `postgres`. Las contraseñas las teclea él
(getpass) y nunca llegan en claro al servidor: se envía el verificador
SCRAM-SHA-256 calculado en local, así no quedan en el log de PostgreSQL.
El pgpass.conf compartido solo se lee (lo lee libpq); el de SENTRA queda
solo para tu usuario (Windows: icacls sin herencia; Linux: 0600).
"""

import base64
import hashlib
import hmac
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import rol_sentra

# RFC 7677, sección 3: usuario «user», contraseña «pencil».
SAL = base64.b64decode("W22ZaJ0SNY7soEsUEjb6gQ==")
AUTH_MESSAGE = (
    b"n=user,r=rOprNGfwEbeRWgbNEkqO,"
    b"r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0,s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096,"
    b"c=biws,r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0"
)
PRUEBA_DEL_CLIENTE = base64.b64decode("dHzbZapWIk4jUhN+Ute9ytag9zjfMHgsqmmiz7AndVQ=")
FIRMA_DEL_SERVIDOR = base64.b64decode("6rriTRBi23WpRR/wtup+mMhUZUn/dB5nLTJRsjl95G4=")


def claves(verificador: str) -> tuple[bytes, bytes]:
    """StoredKey y ServerKey de «SCRAM-SHA-256$<i>:<sal>$<StoredKey>:<ServerKey>»."""
    _, _, resto = verificador.partition("$")
    _, _, llaves = resto.partition("$")
    guardada, servidor = llaves.split(":")
    return base64.b64decode(guardada), base64.b64decode(servidor)


def el_servidor_acepta(verificador: str) -> bool:
    """Lo que hace el servidor con la prueba del cliente de la RFC."""
    guardada, servidor = claves(verificador)
    firma = hmac.new(guardada, AUTH_MESSAGE, hashlib.sha256).digest()
    clave_cliente = bytes(a ^ b for a, b in zip(PRUEBA_DEL_CLIENTE, firma, strict=True))
    return (hashlib.sha256(clave_cliente).digest() == guardada
            and hmac.new(servidor, AUTH_MESSAGE, hashlib.sha256).digest() == FIRMA_DEL_SERVIDOR)


class TestVerificadorScram(unittest.TestCase):
    def test_el_verificador_valida_el_ejemplo_de_la_rfc_7677(self):
        v = rol_sentra.verificador_scram("pencil", sal=SAL, iteraciones=4096)
        self.assertTrue(v.startswith("SCRAM-SHA-256$4096:W22ZaJ0SNY7soEsUEjb6gQ==$"), v)
        self.assertTrue(el_servidor_acepta(v))

    def test_otra_contrasena_no_pasa(self):
        self.assertFalse(el_servidor_acepta(rol_sentra.verificador_scram("pencil2", sal=SAL, iteraciones=4096)))

    def test_cada_verificador_lleva_su_propia_sal(self):
        self.assertNotEqual(rol_sentra.verificador_scram("x"), rol_sentra.verificador_scram("x"))


class TestPgpass(unittest.TestCase):
    def test_la_linea_escapa_dos_puntos_y_barras(self):
        self.assertEqual(rol_sentra.linea_pgpass("reddit_intelligence_radar", "sentra_owner", "a:b\\c"),
                         "localhost:5432:reddit_intelligence_radar:sentra_owner:a\\:b\\\\c")

    def test_solo_escribe_en_el_pgpass_de_sentra(self):
        compartido = Path.home() / "AppData" / "Roaming" / "postgresql" / "pgpass.conf"
        with self.assertRaises(ValueError):
            rol_sentra.escribir_pgpass(["x"], ruta=compartido)

    def test_icacls_quita_la_herencia_y_deja_solo_al_usuario(self):
        self.assertEqual(rol_sentra.orden_icacls(Path("C:/x/pgpass.conf"), "PC\\walter"),
                         ["icacls", str(Path("C:/x/pgpass.conf")), "/inheritance:r", "/grant:r", "PC\\walter:(F)"])


@unittest.skipIf(os.name == "nt", "en Windows los permisos van con icacls")
class TestPermisosPosix(unittest.TestCase):
    """libpq ignora un pgpass legible por grupo u otros: debe nacer con 0600."""

    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.destino = Path(carpeta.name) / "SENTRA" / "pgpass.conf"
        parche = mock.patch.object(rol_sentra, "ruta_pgpass", return_value=self.destino)
        parche.start()
        self.addCleanup(parche.stop)
        anterior = os.umask(0o022)
        self.addCleanup(os.umask, anterior)

    def modo(self, ruta: Path) -> int:
        return stat.S_IMODE(ruta.stat().st_mode)

    def test_el_pgpass_nace_solo_para_el_usuario(self):
        ruta = rol_sentra.escribir_pgpass(["localhost:5432:*:u:secreto"])
        self.assertEqual(ruta, self.destino)
        self.assertEqual(self.modo(ruta), 0o600)
        self.assertEqual(ruta.read_text(encoding="utf-8"), "localhost:5432:*:u:secreto\n")

    def test_un_temporal_viejo_y_abierto_no_deja_el_pgpass_abierto(self):
        self.destino.parent.mkdir(parents=True)
        temporal = self.destino.with_suffix(".tmp")
        temporal.write_text("viejo", encoding="utf-8")
        temporal.chmod(0o644)
        rol_sentra.escribir_pgpass(["x"])
        self.assertEqual(self.modo(self.destino), 0o600)
        self.assertFalse(temporal.exists())

    def test_en_seco_en_linux_dice_chmod_600(self):
        with (mock.patch.object(rol_sentra, "_roles_existentes", return_value=[]),
              mock.patch.object(rol_sentra, "sentencias_de_propiedad", return_value=([], [])),
              mock.patch("builtins.print") as imprimir):
            rol_sentra.en_seco("dsn")
        texto = "\n".join(" ".join(map(str, c.args)) for c in imprimir.call_args_list)
        self.assertIn(f"chmod 600 {self.destino}", texto)
        self.assertNotIn("icacls", texto)


class TestSentencias(unittest.TestCase):
    def test_los_roles_no_son_superusuarios_y_solo_pruebas_crea_bases(self):
        owner, pruebas = rol_sentra.sentencias_de_roles("SCRAM-SHA-256$v1", "SCRAM-SHA-256$v2")
        for sentencia in (owner, pruebas):
            self.assertIn("NOSUPERUSER", sentencia)
            self.assertIn("NOCREATEROLE", sentencia)
            self.assertIn("NOBYPASSRLS", sentencia)
        self.assertIn("NOCREATEDB", owner)
        self.assertIn(" CREATEDB", pruebas)

    def test_en_seco_no_se_ve_ninguna_contrasena_ni_verificador(self):
        texto = "\n".join(rol_sentra.para_mostrar(rol_sentra.sentencias_de_roles("SCRAM-SHA-256$secreto", "SCRAM-SHA-256$otro")))
        self.assertNotIn("secreto", texto)
        self.assertNotIn("otro", texto)


if __name__ == "__main__":
    unittest.main()
