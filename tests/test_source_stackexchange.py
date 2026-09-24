"""
Fuente 2: Stack Exchange (API oficial v2.3)
===========================================

Dobles fieles al envoltorio común de la API v2.3 (api.stackexchange.com/
docs/wrapper): `items`, `has_more`, `quota_max`, `quota_remaining` y, a
veces, `backoff`; los fallos llegan con `error_id`, `error_name` y
`error_message`. Las preguntas de /search/advanced con el filtro
`withbody` traen question_id, title, body (HTML), link, owner.display_name,
creation_date (epoch), score, answer_count, view_count, is_answered y tags.
Forma contrastada el 2026-09-23 con 2 peticiones reales sin clave (/info y
/search/advanced): quota_max 300, preguntas con todos esos campos.

Reglas de la documentación y de los términos que se prueban aquí:
- `backoff`: esperar esos segundos antes de volver al mismo método.
- No repetir una petición idéntica antes de un minuto.
- Menos de 30 peticiones por segundo por IP.
- Clave opcional (RIR_STACKEXCHANGE_KEY): solo lectura anónima, más cuota.
- Uso comercial remitido a las soluciones de pago: solo uso personal.
Contenido y autores inventados (R8).
"""

import unittest
from datetime import UTC, datetime
from itertools import pairwise
from urllib.parse import parse_qs, urlparse

import httpx

from core.evidence.model import SearchQuery
from core.sources.budget import SourceBudget
from core.sources.errors import SourceAuthFailed, SourceRateLimited
from core.sources.stackexchange import StackExchangeSource

SAL = "5e" * 32
DESDE = datetime(2026, 1, 1, tzinfo=UTC)

PREGUNTA = {
    "question_id": 79000001, "title": "Is there a tool to export invoices from QuickBooks to CSV?",
    "body": "<p>I export every invoice by hand.</p><p>It takes &gt; 3 hours a month.</p>",
    "link": "https://stackoverflow.com/questions/79000001/is-there-a-tool-to-export-invoices",
    "owner": {"display_name": "Autora Inventada", "user_id": 111, "user_type": "registered"},
    "creation_date": 1780000000, "score": 5, "answer_count": 2, "view_count": 340,
    "is_answered": False, "tags": ["csv", "invoices"],
}


def envoltorio(*items, quota_remaining=298, backoff=None, has_more=False):
    datos = {"items": list(items), "has_more": has_more, "quota_max": 300,
             "quota_remaining": quota_remaining}
    if backoff is not None:
        datos["backoff"] = backoff
    return datos


def error(error_id, error_name, estado=None, mensaje="mensaje inventado"):
    return httpx.Response(estado or error_id, json={
        "error_id": error_id, "error_name": error_name, "error_message": mensaje})


class Reloj:
    """Tiempo y esperas falsos: los tests no duermen de verdad."""

    def __init__(self):
        self.ahora = 1000.0
        self.esperas = []
        self.recientes = {}

    def monotonic(self):
        return self.ahora

    async def sleep(self, segundos):
        self.esperas.append(segundos)
        self.ahora += segundos


def fuente(manejador, credenciales=None, reloj=None, **presupuesto):
    reloj = reloj or Reloj()
    adaptador = StackExchangeSource(
        http=httpx.AsyncClient(transport=httpx.MockTransport(manejador)),
        budget=SourceBudget(**presupuesto), credentials=credenciales or {}, author_salt=SAL,
        sleep=reloj.sleep, recent=reloj.recientes,
    )
    adaptador.clock = reloj.monotonic
    return adaptador


async def todos(generador):
    return [x async for x in generador]


class TestDeclaracion(unittest.TestCase):
    def test_clave_opcional_secreta_y_solo_uso_personal(self):
        self.assertEqual(StackExchangeSource.id, "stackexchange")
        self.assertEqual(StackExchangeSource.display_name, "Stack Exchange")
        self.assertFalse(StackExchangeSource.requires_credentials)
        self.assertFalse(StackExchangeSource.commercial_use_allowed)
        [clave] = StackExchangeSource.credential_fields
        self.assertEqual((clave.name, clave.env_var, clave.required, clave.secret),
                         ("key", "RIR_STACKEXCHANGE_KEY", False, True))
        self.assertTrue(StackExchangeSource.terms_url.startswith("https://stackexchange.com/"))


class TestBusqueda(unittest.IsolatedAsyncioTestCase):
    async def test_pide_preguntas_con_cuerpo_en_la_ventana_y_el_sitio(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=envoltorio())

        consulta = SearchQuery(keywords=["invoice"], phrases=["is there a tool"], since=DESDE,
                               targets={"stackexchange": ["superuser"]})
        await todos(fuente(manejador).search(consulta))
        url = urlparse(str(peticiones[0].url))
        params = parse_qs(url.query)
        self.assertEqual((url.netloc, url.path), ("api.stackexchange.com", "/2.3/search/advanced"))
        self.assertEqual(params["site"], ["superuser"])
        # Solo el tema: tema + frase exigía todo y daba 0–1 (medido; con el tema solo, 21–30).
        self.assertEqual(params["q"], ["invoice"])
        self.assertEqual(params["filter"], ["withbody"])
        self.assertEqual(params["fromdate"], [str(int(DESDE.timestamp()))])
        self.assertNotIn("key", params, "sin clave: cuota anónima")

    async def test_sin_objetivos_busca_en_stack_overflow(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=envoltorio())

        await todos(fuente(manejador).search(SearchQuery(keywords=["x"])))
        self.assertEqual(parse_qs(urlparse(str(peticiones[0].url)).query)["site"],
                         ["stackoverflow"])

    async def test_con_clave_la_envia_como_parametro_key(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=envoltorio())

        await todos(fuente(manejador, {"key": "clave-inventada"}).search(
            SearchQuery(keywords=["x"])))
        self.assertEqual(parse_qs(urlparse(str(peticiones[0].url)).query)["key"],
                         ["clave-inventada"])

    async def test_una_pregunta_con_su_sitio_texto_limpio_y_enlace(self):
        [pregunta] = await todos(fuente(lambda _r: httpx.Response(
            200, json=envoltorio(PREGUNTA))).search(SearchQuery(keywords=["invoice"])))
        self.assertEqual((pregunta.id, pregunta.kind), ("stackexchange:stackoverflow:79000001",
                                                        "question"))
        self.assertEqual(pregunta.community, "Stack Overflow")
        self.assertEqual(pregunta.text, "I export every invoice by hand.\n\nIt takes > 3 hours a month.")
        self.assertEqual(pregunta.url, PREGUNTA["link"])
        self.assertEqual((pregunta.engagement.score, pregunta.engagement.replies,
                          pregunta.engagement.views), (5, 2, 340))
        self.assertEqual(pregunta.created_at, datetime.fromtimestamp(1780000000, UTC))
        self.assertEqual(pregunta.native_metrics["site"], "stackoverflow")
        self.assertNotIn("Autora Inventada", pregunta.model_dump_json(), "autor solo como hash (R9)")

    async def test_un_sitio_sin_nombre_conocido_usa_el_dominio_del_enlace(self):
        otra = dict(PREGUNTA, link="https://cooking.stackexchange.com/questions/5/x")
        [pregunta] = await todos(fuente(lambda _r: httpx.Response(
            200, json=envoltorio(otra))).search(SearchQuery(
                keywords=["x"], targets={"stackexchange": ["cooking"]})))
        self.assertEqual(pregunta.community, "cooking.stackexchange.com")

    async def test_la_misma_pregunta_en_dos_busquedas_sale_una_vez(self):
        items = await todos(fuente(lambda _r: httpx.Response(200, json=envoltorio(PREGUNTA))).search(
            SearchQuery(keywords=["invoice", "billing"])))
        self.assertEqual(len(items), 1)


class TestCuota(unittest.IsolatedAsyncioTestCase):
    async def test_respeta_backoff_antes_de_volver_al_mismo_metodo(self):
        reloj = Reloj()
        respuestas = iter([envoltorio(backoff=10), envoltorio()])
        await todos(fuente(lambda _r: httpx.Response(200, json=next(respuestas)), reloj=reloj)
                    .search(SearchQuery(keywords=["a", "b"])))
        self.assertIn(10, [round(e) for e in reloj.esperas])

    async def test_nunca_mas_de_30_peticiones_por_segundo(self):
        reloj = Reloj()
        instantes = []

        def manejador(_peticion):
            instantes.append(reloj.ahora)
            return httpx.Response(200, json=envoltorio())

        await todos(fuente(manejador, reloj=reloj).search(
            SearchQuery(keywords=["a", "b", "c", "d"])))
        separaciones = [b - a for a, b in pairwise(instantes)]
        self.assertTrue(all(s >= 1 / 30 for s in separaciones), separaciones)

    async def test_no_repite_una_peticion_identica_antes_de_un_minuto(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=envoltorio(PREGUNTA))

        reloj = Reloj()
        await todos(fuente(manejador, reloj=reloj).search(SearchQuery(keywords=["x"])))
        await todos(fuente(manejador, reloj=reloj).search(SearchQuery(keywords=["x"])))
        self.assertEqual(len(peticiones), 1)
        reloj.ahora += 61
        await todos(fuente(manejador, reloj=reloj).search(SearchQuery(keywords=["x"])))
        self.assertEqual(len(peticiones), 2)

    async def test_la_cuota_diaria_agotada_para_la_fuente(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=envoltorio(PREGUNTA, quota_remaining=0))

        with self.assertRaises(SourceRateLimited):
            await todos(fuente(manejador).search(SearchQuery(keywords=["a", "b"])))
        self.assertEqual(len(peticiones), 1, "con la cuota a 0 no se pide más")

    async def test_throttle_violation_es_limite_de_uso(self):
        with self.assertRaises(SourceRateLimited):
            await todos(fuente(lambda _r: error(502, "throttle_violation", estado=400))
                        .search(SearchQuery(keywords=["x"])))

    async def test_una_clave_invalida_es_credencial_rechazada(self):
        with self.assertRaises(SourceAuthFailed):
            await todos(fuente(lambda _r: error(400, "bad_parameter", mensaje="`key` is not valid"),
                               {"key": "mala"})
                        .search(SearchQuery(keywords=["x"])))


class TestSonda(unittest.IsolatedAsyncioTestCase):
    async def test_info_del_sitio_y_cuota_restante(self):
        peticiones = []

        def manejador(peticion):
            peticiones.append(peticion)
            return httpx.Response(200, json=envoltorio({"total_questions": 24000000},
                                                       quota_remaining=297))

        resultado = await fuente(manejador).probe()
        self.assertTrue(resultado.ok)
        self.assertEqual(urlparse(str(peticiones[0].url)).path, "/2.3/info")
        self.assertIn("297", resultado.detail)

    async def test_un_fallo_se_informa_con_codigo(self):
        resultado = await fuente(lambda _r: error(503, "temporarily_unavailable")).probe()
        self.assertEqual((resultado.ok, resultado.code), (False, "source_unavailable"))


if __name__ == "__main__":
    unittest.main()
