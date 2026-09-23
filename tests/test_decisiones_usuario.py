"""
Decisiones del usuario D-M8 a D-M11 (misión de cierre, 2026-09-23)
===================================================================

Un test por decisión, para que ninguna cambie sin que falle algo:

- D-M8  Un CONSTRUIR sin abogado del diablo disponible baja a INVESTIGAR MÁS.
- D-M9  El hueco de competencia vale 0,5 sin menciones de competidores y se
        marca «sin_datos» (la UI lo muestra como «sin datos de competencia»).
- D-M10 Las URLs de GitHub llevan owner/repo; el autor de la issue, solo hash.
- D-M11 El enlace de Mastodon es la URL de la API (JSON), sin @usuario.

Datos inventados (R8).
"""

import asyncio
import unittest
from datetime import UTC, datetime, timedelta

import httpx

from core.evidence.model import EvidenceItem, SearchQuery
from core.judge.advocate import run_advocate
from core.judge.dimensions import NO_COMPETITION_EVIDENCE_GAP, score_cluster
from core.judge.gates import judge_cluster
from core.judge.labels import VerifiedLabel
from core.sources.budget import SourceBudget

AHORA = datetime(2026, 9, 1, tzinfo=UTC)
FUENTES = ("hackernews", "stackexchange", "github")
SAL = "d0" * 32


def grupo_construir():
    items = [EvidenceItem(id=f"{FUENTES[n % 3]}:{n}", source=FUENTES[n % 3], community="c",
                          kind="post", text=f"queja inventada {n}", url=f"https://example.com/{n}",
                          author_hash=f"{n:064x}", created_at=AHORA - timedelta(days=5),
                          fetched_at=AHORA, thread_id=f"{FUENTES[n % 3]}:{n}", data_source="real")
             for n in range(10)]
    etiquetas = {i.id: VerifiedLabel(item_id=i.id, content_hash="h", labeler="t", is_pain="yes",
                                     intent="queja", workaround_described="no", wtp_signal="no")
                 for i in items}
    etiquetas[items[0].id] = etiquetas[items[0].id].model_copy(update={"workaround_described": "yes"})
    etiquetas[items[1].id] = etiquetas[items[1].id].model_copy(update={"wtp_signal": "yes"})
    return items, etiquetas


async def todos(generador):
    return [x async for x in generador]


class TestDecisionesDelUsuario(unittest.TestCase):
    def test_d_m8_sin_abogado_un_construir_baja_a_investigar(self):
        items, etiquetas = grupo_construir()
        juicio = judge_cluster(items, etiquetas, now=AHORA)
        self.assertEqual(juicio.verdict, "CONSTRUIR")
        resultado = run_advocate(juicio, items, provider=None, model=None)
        self.assertEqual((resultado.verdict_after, resultado.reason),
                         ("INVESTIGAR MÁS", "advocate_unavailable"))

    def test_d_m9_hueco_neutro_y_marcado_sin_datos(self):
        items, etiquetas = grupo_construir()
        hueco = next(d for d in score_cluster(items, etiquetas, now=AHORA).dimensions
                     if d.name == "hueco")
        self.assertEqual(NO_COMPETITION_EVIDENCE_GAP, 0.5)
        self.assertEqual((hueco.value, hueco.normalized, hueco.note), (None, 0.5, "sin_datos"))

    def test_d_m10_github_url_con_owner_repo_y_autor_solo_hash(self):
        from core.sources.github import GitHubSource

        issue = {"id": 1, "number": 7, "title": "Export is broken", "body": "It breaks every week.",
                 "html_url": "https://github.com/org-inventada/app/issues/7",
                 "repository_url": "https://api.github.com/repos/org-inventada/app",
                 "user": {"login": "autora_inventada"}, "created_at": "2026-06-01T00:00:00Z",
                 "comments": 0, "reactions": {"total_count": 0}}
        fuente = GitHubSource(
            http=httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _r: httpx.Response(200, json={"items": [issue]}))),
            budget=SourceBudget(), credentials={}, author_salt=SAL)
        [item] = asyncio.run(todos(fuente.search(SearchQuery(keywords=["x"]))))
        self.assertEqual(item.url, "https://github.com/org-inventada/app/issues/7")
        self.assertEqual(item.community, "org-inventada/app")
        self.assertNotIn("autora_inventada", item.model_dump_json())
        self.assertEqual(len(item.author_hash or ""), 64)

    def test_d_m11_mastodon_enlaza_la_api_sin_usuario(self):
        from core.sources.mastodon import MastodonSource

        estado = {"id": "9", "created_at": "2026-06-01T00:00:00.000Z", "visibility": "public",
                  "content": "<p>Invoices are painful every single month</p>",
                  "url": "https://mastodon.social/@autora_inventada/9",
                  "account": {"id": "5", "acct": "autora_inventada", "username": "autora_inventada"}}
        fuente = MastodonSource(
            http=httpx.AsyncClient(transport=httpx.MockTransport(
                lambda _r: httpx.Response(200, json={"statuses": [estado]}))),
            budget=SourceBudget(), credentials={"instance": "mastodon.social", "access_token": "t"},
            author_salt=SAL)
        [item] = asyncio.run(todos(fuente.search(SearchQuery(keywords=["x"]))))
        self.assertEqual(item.url, "https://mastodon.social/api/v1/statuses/9")
        self.assertNotIn("@", item.url)
        self.assertNotIn("autora_inventada", item.model_dump_json())


if __name__ == "__main__":
    unittest.main()
