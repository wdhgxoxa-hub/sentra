"""
Fuente 3: GitHub (API REST oficial, búsqueda de issues)
=======================================================

Dobles con la forma que documenta GitHub para GET /search/issues
(docs.github.com/en/rest/search/search#search-issues-and-pull-requests,
versión 2022-11-28): `total_count`, `incomplete_results` e `items` con id,
number, title, body (markdown), html_url, repository_url, user.login,
created_at (ISO 8601), comments, reactions.total_count y, solo en los pull
requests, `pull_request`. NO contrastados con una respuesta real: no hay
token de GitHub en el .env y R7 no permite probarla sin credencial.
Contenido y autores inventados (R8).
"""

import unittest
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx

from core.evidence.model import SearchQuery
from core.sources.budget import SourceBudget
from core.sources.github import GitHubSource

SAL = "9c" * 32
DESDE = datetime(2026, 3, 1, tzinfo=UTC)

ISSUE = {
    "id": 3100000001, "number": 412, "title": "Export invoices to CSV is missing",
    "body": "Every month I copy invoices by hand into a spreadsheet.\r\nWould pay for this.",
    "html_url": "https://github.com/ejemplo-org/facturador/issues/412",
    "repository_url": "https://api.github.com/repos/ejemplo-org/facturador",
    "user": {"login": "usuaria-inventada", "type": "User"},
    "created_at": "2026-06-02T10:15:00Z", "state": "open", "comments": 9,
    "reactions": {"total_count": 23, "+1": 20, "heart": 3}, "labels": [],
}
PULL = dict(ISSUE, id=3100000002, number=413, title="Add CSV export",
            html_url="https://github.com/ejemplo-org/facturador/pull/413",
            pull_request={"url": "https://api.github.com/repos/ejemplo-org/facturador/pulls/413"})


def respuesta(*items):
    return {"total_count": len(items), "incomplete_results": False, "items": list(items)}


def fuente(manejador, credenciales=None, **presupuesto):
    return GitHubSource(
        http=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
        budget=SourceBudget(**presupuesto), credentials=credenciales or {}, author_salt=SAL,
    )


async def todos(generador):
    return [x async for x in generador]


class TestDeclaracion(unittest.TestCase):
    def test_token_opcional_y_terminos(self):
        self.assertEqual(GitHubSource.id, "github")
        self.assertFalse(GitHubSource.requires_credentials)
        [token] = GitHubSource.credential_fields
        self.assertEqual((token.env_var, token.required, token.secret),
                         ("RIR_GITHUB_TOKEN", False, True))
        self.assertTrue(GitHubSource.terms_url.startswith("https://docs.github.com/"))


class TestBusqueda(unittest.IsolatedAsyncioTestCase):
    async def test_busca_issues_en_la_ventana_con_las_cabeceras_de_la_api(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=respuesta())

        consulta = SearchQuery(keywords=["invoice"], phrases=["would pay"], since=DESDE,
                               targets={"github": ["ejemplo-org/facturador", "otra/cosa"]})
        await todos(fuente(manejador).search(consulta))
        peticion = peticiones[0]
        url = urlparse(str(peticion.url))
        self.assertEqual((url.netloc, url.path), ("api.github.com", "/search/issues"))
        q = parse_qs(url.query)["q"][0]
        for parte in ('"invoice"', '"would pay"', "is:issue", "created:>=2026-03-01",
                      "repo:ejemplo-org/facturador", "repo:otra/cosa"):
            self.assertIn(parte, q)
        self.assertEqual(peticion.headers["Accept"], "application/vnd.github+json")
        self.assertEqual(peticion.headers["X-GitHub-Api-Version"], "2022-11-28")
        self.assertNotIn("Authorization", peticion.headers)

    async def test_con_token_lo_envia_como_bearer(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=respuesta())

        await todos(fuente(manejador, {"token": "tok-inventado"}).search(
            SearchQuery(keywords=["x"])))
        self.assertEqual(peticiones[0].headers["Authorization"], "Bearer tok-inventado")

    async def test_un_issue_con_su_repo_interaccion_y_enlace(self):
        [issue] = await todos(fuente(lambda _r: httpx.Response(200, json=respuesta(ISSUE))).search(
            SearchQuery(keywords=["invoice"])))
        self.assertEqual((issue.id, issue.kind), ("github:3100000001", "issue"))
        self.assertEqual(issue.community, "ejemplo-org/facturador")
        self.assertEqual(issue.title, "Export invoices to CSV is missing")
        self.assertEqual(issue.text,
                         "Every month I copy invoices by hand into a spreadsheet.\nWould pay for this.")
        self.assertEqual(issue.url, "https://github.com/ejemplo-org/facturador/issues/412")
        self.assertEqual((issue.engagement.replies, issue.engagement.reactions), (9, 23))
        self.assertEqual(issue.created_at, datetime(2026, 6, 2, 10, 15, tzinfo=UTC))
        self.assertNotIn("usuaria-inventada", issue.model_dump_json(), "autor solo como hash (R9)")

    async def test_los_pull_requests_no_son_quejas(self):
        items = await todos(fuente(lambda _r: httpx.Response(200, json=respuesta(PULL, ISSUE))).search(
            SearchQuery(keywords=["invoice"])))
        self.assertEqual([i.id for i in items], ["github:3100000001"])

    async def test_sin_cuerpo_usa_el_titulo(self):
        [issue] = await todos(fuente(lambda _r: httpx.Response(
            200, json=respuesta(dict(ISSUE, body=None)))).search(SearchQuery(keywords=["x"])))
        self.assertEqual(issue.text, ISSUE["title"])

    async def test_el_mismo_issue_en_dos_busquedas_sale_una_vez(self):
        items = await todos(fuente(lambda _r: httpx.Response(200, json=respuesta(ISSUE))).search(
            SearchQuery(keywords=["invoice", "billing"])))
        self.assertEqual(len(items), 1)

    async def test_no_pide_mas_busquedas_que_su_presupuesto(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=respuesta())

        await todos(fuente(manejador, max_requests=3).search(
            SearchQuery(keywords=["a", "b"], phrases=["x", "y"])))
        self.assertEqual(len(peticiones), 3)

    async def test_la_cuota_agotada_es_rate_limit_y_no_acceso_denegado(self):
        from core.sources.errors import SourceRateLimited

        cabeceras = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "4102444800"}
        with self.assertRaises(SourceRateLimited):
            await todos(fuente(lambda _r: httpx.Response(403, headers=cabeceras)).search(
                SearchQuery(keywords=["x"])))


class TestSonda(unittest.IsolatedAsyncioTestCase):
    async def test_consulta_rate_limit_que_no_gasta_cuota(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json={"resources": {"search": {
                "limit": 10, "remaining": 10, "reset": 4102444800, "used": 0}}})

        resultado = await fuente(manejador).probe()
        self.assertTrue(resultado.ok)
        self.assertEqual(urlparse(str(peticiones[0].url)).path, "/rate_limit")
        self.assertIn("10", resultado.detail)

    async def test_un_token_rechazado_se_informa_con_codigo(self):
        resultado = await fuente(lambda _r: httpx.Response(401), {"token": "malo"}).probe()
        self.assertEqual((resultado.ok, resultado.code), (False, "source_auth_failed"))


if __name__ == "__main__":
    unittest.main()
