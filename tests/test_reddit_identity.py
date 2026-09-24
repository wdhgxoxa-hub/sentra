"""
El cliente de Reddit se identifica y no finge ser un navegador (AUD-014)
=======================================================================

Antes el cliente usaba curl_cffi con `impersonate="chrome124"` y el módulo
bypass.py añadía cookies (over18, _options, loid) y cabeceras Sec-Fetch-*
de navegador. Reddit exige lo contrario: un User-Agent que identifique la
aplicación y a su autor, con el formato

    <plataforma>:<app>:<versión> (by /u/<usuario>)

Aquí se comprueba, con la red real de httpx y un servidor falso
(`httpx.MockTransport`), que ninguna petición —token, listado, hilo— lleva
cabeceras Sec-Ch-*/Sec-Fetch-*, cookies ni un UA de navegador, y que un UA
de relleno se rechaza con un error tipado y traducido, antes de salir a la red.
"""

import ast
import asyncio
import importlib
import inspect
import re
import unittest
from functools import partial
from pathlib import Path
from unittest import mock

import httpx

from core.ingestion import RedditIngestionClient
from core.ingestion.auth import RedditOAuth
from core.ingestion.errors import RedditUserAgentInvalid
from core.ingestion.user_agent import validar_user_agent
from tests._sin_red import prohibir_red_real

RAIZ = Path(__file__).resolve().parents[1]
UA = "python:sentra-tests:1.0 (by /u/sentra_ci)"


def listado():
    return {"kind": "Listing", "data": {"after": None, "children": [
        {"kind": "t3", "data": {"id": "abc", "title": "t", "selftext": "", "author": "u",
                                "subreddit": "SaaS", "created_utc": 1758000000.0,
                                "permalink": "/r/SaaS/comments/abc/"}}]}}


def hilo():
    return [listado(), {"kind": "Listing", "data": {"children": [
        {"kind": "t1", "data": {"id": "c1", "body": "the export is broken", "author": "a",
                                "score": 3, "created_utc": 1758000000.0,
                                "permalink": "/r/SaaS/comments/abc/x/c1/", "parent_id": "t3_abc"}}]}}]


class RedFalsa:
    """Servidor falso: anota cada petición y responde como Reddit."""

    def __init__(self):
        self.peticiones: list[httpx.Request] = []

    def __call__(self, peticion: httpx.Request) -> httpx.Response:
        self.peticiones.append(peticion)
        if peticion.url.path == "/api/v1/access_token":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if "/comments/" in peticion.url.path:
            return httpx.Response(200, json=hilo())
        return httpx.Response(200, json=listado())


class ConRedFalsa(unittest.TestCase):

    def setUp(self):
        prohibir_red_real(self)
        self.red = RedFalsa()
        cliente = partial(httpx.AsyncClient, transport=httpx.MockTransport(self.red))
        for destino in ("core.ingestion.client.AsyncClient", "core.ingestion.auth.AsyncClient"):
            parche = mock.patch(destino, cliente)
            parche.start()
            self.addCleanup(parche.stop)

    def cliente(self, user_agent=UA):
        oauth = RedditOAuth(client_id="cid", client_secret="csec", user_agent=user_agent)
        return RedditIngestionClient(oauth=oauth, rate_limit_delay=0)


class TestSinSuplantacion(ConRedFalsa):

    def recorrer(self):
        cliente = self.cliente()
        asyncio.run(cliente.fetch_subreddit_page("SaaS", limit=5))
        asyncio.run(cliente.fetch_thread_comments("SaaS", "abc"))
        return self.red.peticiones

    def test_hay_peticiones_de_token_listado_e_hilo(self):
        rutas = [p.url.path for p in self.recorrer()]
        self.assertIn("/api/v1/access_token", rutas)
        self.assertIn("/r/SaaS/hot", rutas)
        self.assertTrue(any("/comments/abc" in r for r in rutas), rutas)

    def test_ninguna_peticion_lleva_cabeceras_de_navegador(self):
        for peticion in self.recorrer():
            with self.subTest(url=str(peticion.url)):
                nombres = {n.lower() for n in peticion.headers}
                self.assertFalse({n for n in nombres if n.startswith(("sec-ch", "sec-fetch"))})
                self.assertNotIn("cookie", nombres)
                self.assertNotIn("referer", nombres)

    def test_cada_peticion_se_identifica_con_el_user_agent_configurado(self):
        for peticion in self.recorrer():
            with self.subTest(url=str(peticion.url)):
                self.assertEqual(peticion.headers["user-agent"], UA)
                self.assertNotIn("Mozilla", peticion.headers["user-agent"])

    def test_los_hilos_van_por_la_api_oauth_y_no_por_la_web_publica(self):
        for peticion in self.recorrer():
            with self.subTest(url=str(peticion.url)):
                self.assertIn(peticion.url.host, {"oauth.reddit.com", "www.reddit.com"})
                if peticion.url.host == "www.reddit.com":
                    self.assertEqual(peticion.url.path, "/api/v1/access_token")
                self.assertFalse(peticion.url.path.endswith(".json"))

    def test_no_queda_ni_bypass_ni_impersonate_ni_curl_cffi(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("core.ingestion.bypass")
        for fichero in (RAIZ / "core").rglob("*.py"):
            texto = fichero.read_text(encoding="utf-8")
            with self.subTest(fichero=fichero.name):
                self.assertNotRegex(texto, r"impersonate|curl_cffi|over18|Sec-Fetch")
        self.assertNotRegex((RAIZ / "requirements.txt").read_text(encoding="utf-8"), "curl_cffi")

    def test_el_cliente_no_dice_estar_autenticado_sin_haberlo_comprobado(self):
        """R-B: is_authenticated solo miraba si había credenciales, no si
        Reddit las aceptaba, y nadie la usaba. Quien necesite saberlo prueba
        las credenciales (/api/credentials/test)."""
        self.assertFalse(hasattr(RedditIngestionClient, "is_authenticated"))

    def test_quien_crea_el_cliente_usa_sus_parametros_reales(self):
        """Tras quitar la suplantación, scripts/demo_ingestion.py seguía
        pasando impersonate_browser y moría con TypeError al arrancar."""
        admitidos = set(inspect.signature(RedditIngestionClient).parameters)
        for carpeta in ("core", "scripts"):
            for fichero in (RAIZ / carpeta).rglob("*.py"):
                arbol = ast.parse(fichero.read_text(encoding="utf-8"))
                for nodo in ast.walk(arbol):
                    if (
                        isinstance(nodo, ast.Call)
                        and isinstance(nodo.func, ast.Name)
                        and nodo.func.id == "RedditIngestionClient"
                    ):
                        with self.subTest(fichero=fichero.name, linea=nodo.lineno):
                            nombres = {k.arg for k in nodo.keywords if k.arg}
                            self.assertLessEqual(nombres, admitidos)


class TestUserAgent(ConRedFalsa):

    def test_un_user_agent_con_el_formato_de_reddit_es_valido(self):
        for bueno in (UA, "windows:sentra:0.9.2 (by /u/Alguien_Real)"):
            self.assertEqual(validar_user_agent(bueno), bueno)

    def test_el_valor_de_relleno_se_rechaza(self):
        for relleno in ("python:sentra:1.0 (by /u/tu_usuario)",
                        "python:sentra:1.0 (by /u/your_username)",
                        "python:sentra:1.0 (by /u/unknown)"):
            with self.assertRaises(RedditUserAgentInvalid) as ctx:
                validar_user_agent(relleno)
            self.assertEqual(ctx.exception.code, "reddit_user_agent_invalid")

    def test_formatos_que_no_identifican_se_rechazan(self):
        for malo in ("", "   ", "ua", "radar/1.0", "python:sentra:1.0",
                     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"):
            with self.subTest(ua=malo), self.assertRaises(RedditUserAgentInvalid):
                validar_user_agent(malo)

    def test_con_un_user_agent_de_relleno_no_sale_ninguna_peticion(self):
        cliente = self.cliente(user_agent="python:sentra:1.0 (by /u/tu_usuario)")
        with self.assertRaises(RedditUserAgentInvalid):
            asyncio.run(cliente.fetch_subreddit_page("SaaS"))
        self.assertEqual(self.red.peticiones, [])

    def test_el_codigo_tiene_texto_en_es_y_en(self):
        for idioma in ("es", "en"):
            fuente = (RAIZ / "ui" / "src" / "i18n" / f"{idioma}.ts").read_text(encoding="utf-8")
            for bloque in ("errors",):
                encontrado = re.search(rf"\n  {bloque}: \{{(.*?)\n  \}},", fuente, re.DOTALL)
                self.assertIsNotNone(encontrado, (idioma, bloque))
                self.assertIn("reddit_user_agent_invalid:", encontrado.group(1), (idioma, bloque))


if __name__ == "__main__":
    unittest.main()
