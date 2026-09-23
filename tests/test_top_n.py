"""
Las 6 mejores oportunidades, o por qué no hay 6 (AUD-007)
=========================================================

El grafo se detiene cuando hay TOP_N problemas cualificados, cuando se agota
la fuente o al llegar al límite de ciclos; nunca por número de señales. Cada
ejecución termina con un resultado explícito: completo (6/6) o incompleto
(k/6) con un motivo tipado. No se rellena con oportunidades no cualificadas.
"""

import itertools
import logging
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from core.ingestion.errors import RedditForbidden
from core.ingestion.synthetic import SyntheticFetcher
from core.orchestration import RadarDependencies, RadarPipeline, build_graph, new_state
from core.orchestration.top_n import TOP_N, rank_key, rank_top
from core.storage import HashEmbedder, HybridSearchEngine, LanceDBStore

# Siete problemas con un término de dolor propio cada uno: no comparten
# vocabulario, así que el agrupado los mantiene separados.
TERMINOS = [
    "invoice", "hourly rate", "client work", "tedious process",
    "drowning in", "kills my productivity", "bottleneck in my",
]
COMUNIDADES = ["SaaS", "smallbusiness", "freelance", "accounting", "startups"]
DIA = 86400.0


def problema(indice: int, edad_dias: float, con_fuerza: bool = True) -> list[dict]:
    """Cinco voces en cinco comunidades sobre el mismo problema."""
    termino = TERMINOS[indice]
    ahora = time.time()
    cuerpo = (
        f"The {termino} step is broken. It is a severe blocker. I would pay for a fix."
        if con_fuerza
        else f"The {termino} step is broken."
    )
    return [
        {
            "id": f"t3_p{indice}_{n}",
            "subreddit": COMUNIDADES[n] if con_fuerza else "SaaS",
            "title": f"The {termino} is broken",
            "selftext": cuerpo,
            "author": f"u/autor{indice}{n}",
            "score": 10,
            "created_utc": ahora - edad_dias * DIA,
            "url": f"https://reddit.com/r/x/comments/p{indice}{n}",
        }
        for n in range(5)
    ]


class FuentePaginada:
    """Sirve páginas encadenadas por cursor, como Reddit. Anota cada llamada."""

    def __init__(self, paginas, sin_fin=False):
        self.paginas = paginas
        self.sin_fin = sin_fin
        self.llamadas = 0

    def __call__(self, subreddit, limit=25, sort="hot", cursor=None):
        self.llamadas += 1
        indice = int(cursor or 0)
        if self.sin_fin:
            return self.paginas[0], str(indice + 1)
        if indice >= len(self.paginas):
            return [], None
        siguiente = str(indice + 1) if indice + 1 < len(self.paginas) else None
        return self.paginas[indice], siguiente


class ConAlmacen(unittest.TestCase):

    def setUp(self):
        logging.disable(logging.CRITICAL)
        self.tmpdir = Path(tempfile.mkdtemp(prefix="rir_top_"))
        self.addCleanup(shutil.rmtree, self.tmpdir, True)
        self.store = LanceDBStore(db_path=str(self.tmpdir / "lance"), embedder=HashEmbedder(dim=32))

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def _ejecutar(self, fetcher, **kwargs):
        deps = RadarDependencies(
            fetcher=fetcher, store=self.store,
            search_engine=HybridSearchEngine(store=self.store),
        )
        return build_graph(deps, **kwargs).invoke(new_state(subreddit="SaaS", limit=100))


class TestResultadoDeLaEjecucion(ConAlmacen):

    def test_se_detiene_al_reunir_seis_cualificadas(self):
        primera = [p for i in range(6) for p in problema(i, edad_dias=i * 10)]
        segunda = problema(6, edad_dias=60)
        fuente = FuentePaginada([primera, segunda])
        final = self._ejecutar(fuente)

        self.assertEqual(fuente.llamadas, 1, "con 6 cualificadas no hay que pedir mas")
        top = final["top"]
        self.assertEqual((top["found"], top["target"], top["complete"]), (6, TOP_N, True))
        self.assertIsNone(top["reason"])

    def test_el_ranking_son_las_seis_de_mayor_puntuacion_en_orden(self):
        pagina = [p for i in range(7) for p in problema(i, edad_dias=i * 10)]
        final = self._ejecutar(FuentePaginada([pagina]))

        rankeados = sorted(
            (c for c in final["qualified_clusters"] if c.get("top_rank")),
            key=lambda c: c["top_rank"],
        )
        self.assertEqual([c["top_rank"] for c in rankeados], [1, 2, 3, 4, 5, 6])
        puntos = [c["opportunity_score"] for c in rankeados]
        self.assertEqual(puntos, sorted(puntos, reverse=True))
        # El séptimo, el más viejo, se queda fuera.
        self.assertNotIn("bottleneck in my", {k for c in rankeados for k in c["keywords"]})

    def test_con_datos_insuficientes_no_se_rellena(self):
        final = RadarPipeline(
            deps=RadarDependencies(
                fetcher=SyntheticFetcher(), store=self.store,
                search_engine=HybridSearchEngine(store=self.store),
            )
        ).run_state("SaaS")
        top = final["top"]
        cualificadas = [c for c in final["qualified_clusters"]]
        self.assertFalse(top["complete"])
        self.assertEqual(top["reason"], "datos_insuficientes")
        self.assertEqual(top["found"], len(cualificadas))
        self.assertLess(len(final["clusters"]), TOP_N)
        self.assertTrue(all(c.get("top_rank") is None for c in final["clusters"]
                            if c not in cualificadas))

    def test_fuentes_agotadas_con_problemas_de_sobra_pero_debiles(self):
        pagina = [p for i in range(7) for p in problema(i, edad_dias=0, con_fuerza=False)]
        top = self._ejecutar(FuentePaginada([pagina]))["top"]
        self.assertEqual(top["reason"], "fuentes_agotadas")
        self.assertEqual(top["found"], 0)

    def test_limite_de_ciclos(self):
        fuente = FuentePaginada([problema(0, edad_dias=0, con_fuerza=False)], sin_fin=True)
        final = self._ejecutar(fuente, max_cycles=3)
        self.assertEqual(fuente.llamadas, 3)
        self.assertEqual(final["top"]["reason"], "limite_ciclos")

    def test_sin_acceso_a_reddit(self):
        def rechazo(*_args, **_kwargs):
            raise RedditForbidden("403")

        top = self._ejecutar(rechazo)["top"]
        self.assertEqual(top["reason"], "sin_acceso_reddit")
        self.assertEqual(top["found"], 0)


class TestSidecar(ConAlmacen):

    def _app(self, **kwargs):
        from fastapi.testclient import TestClient

        from core.orchestration.sidecar_server import create_app

        deps = RadarDependencies(
            fetcher=SyntheticFetcher(), store=self.store,
            search_engine=HybridSearchEngine(store=self.store),
        )
        return TestClient(create_app(insecure_dev=True, deps=deps, env_path=str(self.tmpdir / ".env"), **kwargs))

    def test_el_evento_final_trae_el_resultado_y_la_fuente(self):
        import json

        crudo = self._app(persist_default=False).post(
            "/api/scan/stream", json={"subreddit": "SaaS"}).text
        final = [json.loads(linea[5:]) for linea in crudo.splitlines()
                 if linea.startswith("data:")][-1]
        self.assertEqual(final["type"], "run:finished")
        self.assertEqual(final["dataSource"], "demo")
        self.assertEqual(final["top"]["target"], TOP_N)
        self.assertEqual(final["top"]["reason"], "datos_insuficientes")

    def test_la_respuesta_del_escaneo_trae_el_resultado(self):
        cuerpo = self._app(persist_default=False).post(
            "/api/scan", json={"subreddit": "SaaS"}).json()
        self.assertEqual(cuerpo["dataSource"], "demo")
        self.assertEqual(cuerpo["top"]["target"], TOP_N)

    def test_el_sidecar_persiste_la_fuente(self):
        from core.orchestration.sidecar import scan as sidecar_scan

        recibido = {}

        async def espia(state, deps, dsn, status="completed", data_source=None):
            recibido["data_source"] = data_source
            return "run", True, None

        original = sidecar_scan._persist
        sidecar_scan._persist = espia
        try:
            self._app(persist_default=True).post("/api/scan", json={"subreddit": "SaaS"})
        finally:
            sidecar_scan._persist = original
        self.assertEqual(recibido["data_source"], "demo")


class TestDesempate(unittest.TestCase):

    def test_el_orden_de_entrada_no_cambia_el_ranking(self):
        clusters = [
            {"key": "b", "opportunity_score": 70.0, "mention_count": 5, "community_count": 3},
            {"key": "a", "opportunity_score": 70.0, "mention_count": 5, "community_count": 3},
            {"key": "c", "opportunity_score": 70.0, "mention_count": 9, "community_count": 1},
            {"key": "d", "opportunity_score": 70.0, "mention_count": 5, "community_count": 4},
            {"key": "e", "opportunity_score": 80.0, "mention_count": 1, "community_count": 1},
        ]
        esperado = ["e", "c", "d", "a", "b"]
        for orden in itertools.permutations(clusters):
            self.assertEqual([c["key"] for c in rank_top(list(orden))], esperado)

    def test_la_clave_de_orden_esta_documentada_en_un_solo_sitio(self):
        c = {"key": "k", "opportunity_score": 1.0, "mention_count": 2, "community_count": 3}
        self.assertEqual(rank_key(c), (-1.0, -2, -3, "k"))

    def test_nunca_mas_de_top_n(self):
        muchos = [{"key": str(i), "opportunity_score": float(i), "mention_count": 1,
                   "community_count": 1} for i in range(20)]
        self.assertEqual(len(rank_top(muchos)), TOP_N)



# ---------------------------------------------------------------------
# Persistencia del resultado (PostgreSQL real, base desechable)
# ---------------------------------------------------------------------


ADMIN_DSN = os.environ.get(
    "RIR_PG_ADMIN_DSN", "host=localhost port=5432 user=postgres dbname=postgres"
)
TEST_DB = "rir_top_n_test"


def _postgres_available() -> bool:
    try:
        import psycopg

        with psycopg.connect(ADMIN_DSN, connect_timeout=3):
            return True
    except Exception:  # noqa: BLE001 - sondeo de disponibilidad del servidor de pruebas
        return False


@unittest.skipUnless(_postgres_available(), "PostgreSQL no disponible")
class TestResultadoPersistido(ConAlmacen):

    @classmethod
    def setUpClass(cls):
        import psycopg

        from scripts.migrate import migrate

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        cls.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        migrate(cls.dsn, Path(__file__).resolve().parents[1] / "sql" / "migrations")

    @classmethod
    def tearDownClass(cls):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')

    def _persistir(self, estado, data_source):
        from core.storage.postgres_store import PostgresStore, run_async

        async def escribir():
            async with PostgresStore(dsn=self.dsn) as store:
                return await store.persist_state(estado, data_source=data_source)

        return run_async(escribir())["run_id"]

    def _consulta(self, sql, params=()):
        import psycopg

        with psycopg.connect(self.dsn) as conn:
            return conn.execute(sql, params).fetchall()

    def test_el_run_guarda_objetivo_encontradas_motivo_y_fuente(self):
        estado = RadarPipeline(
            deps=RadarDependencies(
                fetcher=SyntheticFetcher(), store=self.store,
                search_engine=HybridSearchEngine(store=self.store),
            )
        ).run_state("SaaS")
        run_id = self._persistir(estado, "demo")
        fila = self._consulta(
            "SELECT top_n_target, top_n_found, top_n_reason::text, data_source "
            "FROM radar.pipeline_runs WHERE id = %s", (run_id,)
        )[0]
        self.assertEqual(fila, (TOP_N, estado["top"]["found"], "datos_insuficientes", "demo"))

    def test_las_seis_quedan_con_su_posicion(self):
        pagina = [p for i in range(7) for p in problema(i, edad_dias=i * 10)]
        estado = self._ejecutar(FuentePaginada([pagina]))
        run_id = self._persistir(estado, "reddit")
        posiciones = self._consulta(
            "SELECT top_rank, final_score FROM radar.opportunity_clusters "
            "WHERE run_id = %s AND top_rank IS NOT NULL ORDER BY top_rank", (run_id,)
        )
        self.assertEqual([p[0] for p in posiciones], [1, 2, 3, 4, 5, 6])
        puntos = [float(p[1]) for p in posiciones]
        self.assertEqual(puntos, sorted(puntos, reverse=True))
        fila = self._consulta(
            "SELECT top_n_found, top_n_reason FROM radar.pipeline_runs WHERE id = %s",
            (run_id,),
        )[0]
        self.assertEqual(fila, (6, None))


if __name__ == "__main__":
    unittest.main()
