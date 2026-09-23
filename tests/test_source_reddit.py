"""
Fuente 4: Reddit como adaptador (API oficial OAuth)
===================================================

Refactor del cliente de Reddit al contrato de fuentes. R7 prohíbe llamar a
Reddit mientras no haya aprobación: el adaptador está marcado como
pendiente de aprobación, así que nunca entra en un escaneo, «Probar» no
sale a la red y `search` se niega aunque haya credenciales. Solo uso
personal (commercial_use_allowed = false).

Dobles con la forma documentada de la API de Reddit
(www.reddit.com/dev/api): POST /api/v1/access_token (client_credentials,
autenticación básica, User-Agent propio) y GET oauth.reddit.com/r/{sub}/
search con `data.children[].data` (name, title, selftext, permalink,
subreddit, author, created_utc, score, num_comments). Ninguna llamada
real (R7). Contenido y autores inventados (R8).
"""

import base64
import os
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx

from core.evidence.model import SearchQuery
from core.sources.budget import SourceBudget
from core.sources.errors import (
    SourceAuthFailed,
    SourceCredentialsMissing,
    SourcePendingApproval,
)
from core.sources.reddit import RedditSource
from core.sources.registry import InMemorySourcesState, active_sources, source_status

SAL = "3d" * 32
UA = "desktop:sentra:0.1.0 (by /u/usuaria_inventada)"
CREDENCIALES = {"client_id": "id-inventado", "client_secret": "secreto-inventado", "user_agent": UA}
ENV = {"RIR_REDDIT_CLIENT_ID": "id-inventado", "RIR_REDDIT_CLIENT_SECRET": "secreto-inventado",
       "RIR_REDDIT_USER_AGENT": UA}
POST = {"kind": "t3", "data": {
    "name": "t3_inv001", "title": "Invoicing tool that exports to my accountant?",
    "selftext": "I copy every invoice by hand. Would pay for this.",
    "permalink": "/r/SaaS/comments/inv001/invoicing_tool/", "subreddit": "SaaS",
    "author": "autor_inventado", "created_utc": 1780000000.0, "score": 31, "num_comments": 12}}


def listado(*hijos):
    return {"kind": "Listing", "data": {"children": list(hijos), "after": None}}


class Aprobada(RedditSource):
    """El mismo adaptador sin la marca de aprobación: solo para probar el código."""

    pending_approval = None


def fuente(manejador, clase=Aprobada, credenciales=None):
    return clase(http=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
                 budget=SourceBudget(), credentials=credenciales or CREDENCIALES, author_salt=SAL)


async def todos(generador):
    return [x async for x in generador]


class TestDeclaracion(unittest.TestCase):
    def test_credenciales_uso_personal_y_pendiente_de_aprobacion(self):
        self.assertEqual(RedditSource.id, "reddit")
        self.assertFalse(RedditSource.commercial_use_allowed)
        self.assertTrue(RedditSource.requires_credentials)
        campos = {c.name: (c.env_var, c.secret, c.required) for c in RedditSource.credential_fields}
        self.assertEqual(campos["client_id"], ("RIR_REDDIT_CLIENT_ID", False, True))
        self.assertEqual(campos["client_secret"], ("RIR_REDDIT_CLIENT_SECRET", True, True))
        self.assertEqual(campos["user_agent"], ("RIR_REDDIT_USER_AGENT", False, True))
        self.assertTrue(RedditSource.pending_approval)


class TestPendienteDeAprobacion(unittest.IsolatedAsyncioTestCase):
    def test_con_credenciales_sigue_sin_configurar_y_fuera_del_escaneo(self):
        estado = source_status(RedditSource, ENV, None, commercial_mode=False)
        self.assertEqual(estado.status, "no_configurada")
        self.assertFalse(estado.active)
        self.assertIn("aprobación", estado.detail or "")
        self.assertEqual(active_sources([RedditSource], ENV, InMemorySourcesState(), False), [])

    async def test_search_se_niega_sin_salir_a_la_red(self):
        def prohibido(_peticion):
            raise AssertionError("R7: ninguna llamada a Reddit")

        with self.assertRaises(SourcePendingApproval):
            await todos(fuente(prohibido, clase=RedditSource).search(SearchQuery(keywords=["x"])))

    async def test_probar_se_niega_sin_salir_a_la_red(self):
        def prohibido(_peticion):
            raise AssertionError("R7: ninguna llamada a Reddit")

        resultado = await fuente(prohibido, clase=RedditSource).probe()
        self.assertEqual((resultado.ok, resultado.code), (False, "source_pending_approval"))

    def test_la_ruta_probar_del_sidecar_tampoco_sale(self):
        from fastapi.testclient import TestClient

        from core.ingestion.synthetic import SyntheticFetcher
        from core.orchestration import RadarDependencies
        from core.orchestration.sidecar_server import create_app
        from core.storage import HashEmbedder, LanceDBStore
        from tests._sin_red import prohibir_red_real

        prohibir_red_real(self)
        tmp = tempfile.mkdtemp(prefix="rir_reddit_")
        self.addCleanup(shutil.rmtree, tmp, True)
        with open(os.path.join(tmp, ".env"), "w", encoding="utf-8") as env:
            env.writelines(f"{k}={v}\n" for k, v in ENV.items())
        store = LanceDBStore(db_path=os.path.join(tmp, "l"), embedder=HashEmbedder(dim=16))
        app = create_app(deps=RadarDependencies(fetcher=SyntheticFetcher(), store=store),
                         insecure_dev=True, persist_default=False, env_path=os.path.join(tmp, ".env"))
        cuerpo = TestClient(app).post("/api/sources/reddit/probe").json()
        self.assertEqual((cuerpo["ok"], cuerpo["code"]), (False, "source_pending_approval"))


class TestBusquedaConDobles(unittest.IsolatedAsyncioTestCase):
    async def test_pide_token_y_busca_en_el_subreddit_con_su_user_agent(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            if peticion.url.path == "/api/v1/access_token":
                return httpx.Response(200, json={"access_token": "tok", "token_type": "bearer",
                                                 "expires_in": 86400, "scope": "*"})
            return httpx.Response(200, json=listado(POST))

        consulta = SearchQuery(keywords=["invoice"], since=datetime(2026, 1, 1, tzinfo=UTC),
                               targets={"reddit": ["SaaS"]})
        [item] = await todos(fuente(manejador).search(consulta))
        token, busqueda = peticiones
        self.assertEqual(str(token.url), "https://www.reddit.com/api/v1/access_token")
        basica = base64.b64encode(b"id-inventado:secreto-inventado").decode()
        self.assertEqual(token.headers["Authorization"], f"Basic {basica}")
        self.assertIn(b"grant_type=client_credentials", token.content)
        self.assertEqual(token.headers["User-Agent"], UA)
        url = urlparse(str(busqueda.url))
        params = parse_qs(url.query)
        self.assertEqual((url.netloc, url.path), ("oauth.reddit.com", "/r/SaaS/search"))
        self.assertEqual((params["restrict_sr"], params["sort"], params["t"]), (["1"], ["new"], ["year"]))
        self.assertEqual(busqueda.headers["Authorization"], "bearer tok")
        self.assertEqual(busqueda.headers["User-Agent"], UA)
        self.assertEqual((item.id, item.community, item.kind), ("reddit:t3_inv001", "r/SaaS", "post"))
        self.assertEqual(item.url, "https://www.reddit.com/r/SaaS/comments/inv001/invoicing_tool/")
        self.assertEqual((item.engagement.score, item.engagement.replies), (31, 12))
        self.assertNotIn("autor_inventado", item.model_dump_json(), "autor solo como hash (R9)")

    async def test_lo_anterior_a_la_ventana_se_descarta(self):
        def manejador(peticion):
            if peticion.url.path == "/api/v1/access_token":
                return httpx.Response(200, json={"access_token": "tok", "expires_in": 86400})
            return httpx.Response(200, json=listado(POST))

        consulta = SearchQuery(keywords=["x"], since=datetime(2026, 12, 1, tzinfo=UTC))
        self.assertEqual(await todos(fuente(manejador).search(consulta)), [])

    async def test_un_user_agent_de_relleno_no_sale(self):
        malas = dict(CREDENCIALES, user_agent="desktop:sentra:0.1 (by /u/tu_usuario)")
        with self.assertRaises(SourceCredentialsMissing):
            await todos(fuente(lambda _r: httpx.Response(200), credenciales=malas).search(
                SearchQuery(keywords=["x"])))

    async def test_credenciales_rechazadas(self):
        with self.assertRaises(SourceAuthFailed):
            await todos(fuente(lambda _r: httpx.Response(401)).search(SearchQuery(keywords=["x"])))


if __name__ == "__main__":
    unittest.main()
