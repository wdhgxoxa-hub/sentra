"""
Token del sidecar (AUD-013, decisión D-B)
=========================================

Rust genera un token aleatorio en cada arranque, se lo pasa al sidecar en
`RIR_SIDECAR_TOKEN` y lo manda en `Authorization: Bearer`. El sidecar:

- no arranca sin token, salvo con `--insecure-dev` explícito;
- responde 401 en TODOS los endpoints con un token ausente o incorrecto,
  incluido /api/health: expone el estado de la configuración (si hay
  credenciales, qué motor corre) y Rust, que conoce el token, lo usa igual;
- compara en tiempo constante.

Los tokens de prueba se construyen en ejecución: ningún literal con forma
de secreto llega al repositorio.
"""

import hmac
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from core.orchestration import sidecar_server
from core.orchestration.sidecar_server import create_app
from tests._sin_red import prohibir_red_real

TOKEN = "ab" * 32
OTRO = "cd" * 32


class ConApp(unittest.TestCase):

    def setUp(self):
        prohibir_red_real(self)
        self.tmp = Path(tempfile.mkdtemp(prefix="rir_token_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)


    def app(self, **kwargs):
        return create_app(persist_default=False,
                          env_path=str(self.tmp / ".env"), **kwargs)


class TestArranque(ConApp):

    def test_la_app_no_se_construye_sin_token(self):
        with self.assertRaises(sidecar_server.SidecarSinToken):
            self.app()

    def test_un_token_corto_se_rechaza(self):
        with self.assertRaises(sidecar_server.SidecarSinToken):
            self.app(token="a" * (sidecar_server.MIN_TOKEN_LENGTH - 1))

    def test_con_insecure_dev_explicito_si_se_construye(self):
        self.app(insecure_dev=True)

    def test_el_proceso_no_arranca_sin_token(self):
        with mock.patch.dict("os.environ", {sidecar_server.TOKEN_ENV_VAR: ""}), \
                mock.patch("uvicorn.run") as servir, \
                self.assertRaises(SystemExit) as ctx:
            sidecar_server.main([])
        self.assertNotEqual(ctx.exception.code, 0)
        servir.assert_not_called()

    def test_con_insecure_dev_el_proceso_arranca(self):
        with mock.patch.dict("os.environ", {sidecar_server.TOKEN_ENV_VAR: ""}), \
                mock.patch("uvicorn.run") as servir, \
                mock.patch.object(sidecar_server, "create_app") as fabrica:
            sidecar_server.main(["--insecure-dev"])
        servir.assert_called_once()
        self.assertTrue(fabrica.call_args.kwargs["insecure_dev"])

    def test_con_token_en_el_entorno_el_proceso_arranca_con_el(self):
        with mock.patch.dict("os.environ", {sidecar_server.TOKEN_ENV_VAR: TOKEN}), \
                mock.patch("uvicorn.run") as servir, \
                mock.patch.object(sidecar_server, "create_app") as fabrica:
            sidecar_server.main([])
        servir.assert_called_once()
        self.assertEqual(fabrica.call_args.kwargs["token"], TOKEN)


class TestPeticiones(ConApp):

    def setUp(self):
        super().setUp()
        self.aplicacion = self.app(token=TOKEN)
        self.client = TestClient(self.aplicacion)

    def rutas(self):
        for ruta in self.aplicacion.routes:
            if getattr(ruta, "path", "").startswith("/api/"):
                for metodo in sorted(ruta.methods - {"HEAD"}):
                    yield metodo, ruta.path

    def test_hay_rutas_que_comprobar(self):
        self.assertGreater(len(list(self.rutas())), 10)

    def test_token_incorrecto_da_401_en_todos_los_endpoints(self):
        for cabecera in ({}, {"Authorization": f"Bearer {OTRO}"},
                         {"Authorization": f"Basic {TOKEN}"}, {"Authorization": TOKEN},
                         {"X-Radar-Token": TOKEN}):
            for metodo, ruta in self.rutas():
                with self.subTest(ruta=ruta, metodo=metodo, esquema=list(cabecera)):
                    respuesta = self.client.request(metodo, ruta, headers=cabecera, json={})
                    self.assertEqual(respuesta.status_code, 401)

    def test_con_el_token_correcto_funciona(self):
        respuesta = self.client.get("/api/health", headers={"Authorization": f"Bearer {TOKEN}"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["status"], "ok")

    def test_la_comparacion_es_en_tiempo_constante(self):
        with mock.patch.object(sidecar_server.hmac, "compare_digest",
                               wraps=hmac.compare_digest) as comparar:
            self.client.get("/api/health", headers={"Authorization": f"Bearer {OTRO}"})
        comparar.assert_called()


if __name__ == "__main__":
    unittest.main()
