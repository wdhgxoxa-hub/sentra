"""
Persistencia del juez (F3.8, D-M1)
==================================

Migración 010: `evidence_labels` (caché de etiquetas por hash de contenido y
etiquetador), `niche_verdicts` (un veredicto por grupo con compuertas,
dimensiones, regla y abogado) y `cluster_evidence` (sus miembros). El Top 6
se ordena por veredicto y luego por puntaje, sin rellenar (AUD-007).
Base desechable; datos inventados.
"""

import unittest
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from core.evidence.model import EvidenceItem
from core.judge.clustering import CLUSTERING_VERSION
from core.judge.labels import VerifiedLabel
from core.judge.store import (
    PostgresLabelCache,
    recent_evidence,
    top_verdicts,
    verdict_detail,
)
from core.storage.postgres_store import PostgresStore, run_async
from tests._ayudas import presente
from tests._postgres import ADMIN_DSN, postgres_available

TEST_DB = "rir_judge_store_test"
AHORA = datetime(2026, 9, 1, tzinfo=UTC)


def pieza(n):
    return EvidenceItem(id=f"hackernews:{n}", source="hackernews", community="Ask HN", kind="post",
                        text=f"queja inventada número {n}", url=f"https://example.com/{n}",
                        author_hash=f"{n:064x}", created_at=AHORA - timedelta(days=3),
                        fetched_at=AHORA, data_source="real")


def veredicto(clave, verdict, score, miembros):
    return {"opportunity_id": None, "cluster_key": clave, "keywords": ["facturas"],
            "verdict": verdict, "rule": "7: pasan todas", "score": score,
            "weights_version": "judge-weights-v1", "missing": [],
            "labeler_version": "labels-v2/m", "clustering_version": "clustering-v2",
            "gates": [{"gate": f"G{n}", "passed": True, "value": 2, "threshold": 2,
                       "evidence_ids": miembros} for n in range(1, 9)],
            "dimensions": [{"name": "frecuencia", "value": 3, "normalized": 0.1,
                            "item_ids": miembros, "note": None}],
            "advocate": {"verdict_before": verdict, "verdict_after": verdict, "downgraded": False,
                         "reason": None, "arguments": [], "discarded": []},
            "member_ids": miembros}


@unittest.skipUnless(postgres_available(), "PostgreSQL no disponible")
class TestPersistenciaDelJuez(unittest.TestCase):
    dsn: ClassVar[str]

    @classmethod
    def setUpClass(cls):
        import psycopg

        from scripts.migrate import migrate

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')
        cls.dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={TEST_DB}")
        from pathlib import Path

        migrate(cls.dsn, Path(__file__).resolve().parents[1] / "sql" / "migrations")

    @classmethod
    def tearDownClass(cls):
        import psycopg

        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')

    def run_store(self, funcion):
        async def main():
            async with PostgresStore(dsn=self.dsn) as store:
                return await funcion(store)

        return run_async(main())

    def test_la_cache_de_etiquetas_sobrevive_entre_conexiones(self):
        etiqueta = VerifiedLabel(item_id="hackernews:1", content_hash="a" * 64, labeler="labels-v1/m",
                                 is_pain="yes", intent="queja", workaround_described="no",
                                 wtp_signal="undetermined", evidence_spans={"is_pain": "queja"})
        PostgresLabelCache(self.dsn).put(etiqueta)
        leida = presente(PostgresLabelCache(self.dsn).get("a" * 64, "labels-v1/m"))
        self.assertEqual(leida.model_dump(exclude={"item_id"}), etiqueta.model_dump(exclude={"item_id"}))
        self.assertIsNone(PostgresLabelCache(self.dsn).get("a" * 64, "labels-v2/m"))

    def test_guarda_veredictos_con_sus_miembros_y_el_top_6_ordena_por_veredicto(self):
        items = [pieza(n) for n in range(1, 10)]

        async def guardar(store):
            await store.upsert_evidence(items)
            run_id = await store.start_run("perfil", trigger_source="multifuente", data_source="real")
            await store.save_verdicts(run_id, [
                veredicto("a", "INVESTIGAR MÁS", 80.0, ["hackernews:1", "hackernews:2", "hackernews:3"]),
                veredicto("b", "CONSTRUIR", 40.0, ["hackernews:4", "hackernews:5", "hackernews:6"]),
                veredicto("c", "DESCARTAR", 95.0, ["hackernews:7", "hackernews:8", "hackernews:9"]),
            ])
            await store.finish_run(run_id, {"fetched": 9, "stored": 9})
            return run_id

        run_id = self.run_store(guardar)
        top = self.run_store(lambda store: top_verdicts(store, run_id))
        self.assertEqual([v["cluster_key"] for v in top["verdicts"]], ["b", "a", "c"])
        self.assertEqual((top["target"], top["build_count"]), (6, 1))
        self.assertEqual(top["verdicts"][0]["member_ids"], ["hackernews:4", "hackernews:5", "hackernews:6"])
        self.assertEqual(top["verdicts"][0]["gates"][0]["gate"], "G1")
        self.assertIn("1 de 6", top["reason"])
        # B4: versiones de cada veredicto y las actuales, para marcar lo antiguo.
        self.assertEqual((top["verdicts"][0]["labeler_version"], top["verdicts"][0]["clustering_version"]),
                         ("labels-v2/m", "clustering-v2"))
        from core.judge.clustering import CLUSTERING_VERSION
        from core.judge.dimensions import WEIGHTS_VERSION
        from core.judge.labels import LABELER_VERSION

        self.assertEqual(top["current_versions"], {"labeler": LABELER_VERSION,
                                                   "clustering": CLUSTERING_VERSION,
                                                   "weights": WEIGHTS_VERSION})
        # Mapa de corroboración y evidencia con atribución obligatoria (D-SE3).
        primero = top["verdicts"][0]
        self.assertEqual(primero["corroboration"], {"hackernews": 3})
        evidencia = {e["id"]: e for e in primero["evidence"]}
        self.assertEqual(set(evidencia), {"hackernews:4", "hackernews:5", "hackernews:6"})
        self.assertEqual(evidencia["hackernews:4"]["attribution"],
                         {"badge": "Hacker News", "site": "Ask HN", "url": "https://example.com/4"})
        self.assertEqual(evidencia["hackernews:4"]["excerpt"], "queja inventada número 4")

    def test_una_ejecucion_juzgada_sin_nichos_es_la_ultima_y_se_explica(self):
        """AUD2-001: el juez nuevo puede no formar ningún nicho. Antes «la última
        juzgada» era la última con veredictos, y el Radar habría enseñado los de
        una ejecución anterior como si fueran los actuales."""
        from core.judge.store import SIN_NICHOS, latest_judged_run, marcar_juzgada

        items = [pieza(n) for n in range(40, 43)]

        async def guardar(store):
            await store.upsert_evidence(items)
            antigua = await store.start_run("perfil", trigger_source="multifuente", data_source="real")
            await store.save_verdicts(antigua, [veredicto("z", "DESCARTAR", 10.0, [i.id for i in items])])
            await marcar_juzgada(store, antigua, construir=0)
            nueva = await store.start_run("perfil", trigger_source="rejuicio", data_source="real")
            await store.save_verdicts(nueva, [])
            await marcar_juzgada(store, nueva, construir=0)
            fila = await store._fetchone(
                "SELECT top_n_target, top_n_found, top_n_reason::text AS motivo FROM pipeline_runs WHERE id = %s",
                (nueva,))
            return nueva, dict(fila), await latest_judged_run(store)

        nueva, marca, ultima = self.run_store(guardar)
        self.assertEqual(ultima, nueva)
        self.assertEqual(marca, {"top_n_target": 6, "top_n_found": 0, "motivo": "datos_insuficientes"})
        top = self.run_store(lambda store: top_verdicts(store, nueva))
        self.assertEqual((top["verdicts"], top["reason"]), ([], SIN_NICHOS))

    def test_el_detalle_de_un_veredicto_trae_toda_su_evidencia_para_los_documentos(self):
        # E2: el dossier y el plan citan por id; el modelo ve el texto entero.
        largo = "queja inventada muy larga " * 60
        items = [pieza(n) for n in (70, 71)]
        items[1] = items[1].model_copy(update={"text": largo, "title": "Título de la 71"})

        async def guardar(store):
            await store.upsert_evidence(items)
            run_id = await store.start_run("perfil", trigger_source="multifuente", data_source="real",
                                           parameters={"topic": "facturas"})
            ids = await store.save_verdicts(run_id, [
                veredicto("detalle", "CONSTRUIR", 70.0, ["hackernews:70", "hackernews:71"])])
            return run_id, ids[0]

        run_id, verdict_id = self.run_store(guardar)
        detalle = presente(self.run_store(lambda store: verdict_detail(store, verdict_id)))
        self.assertEqual((detalle["id"], detalle["run_id"], detalle["verdict"]),
                         (verdict_id, run_id, "CONSTRUIR"))
        self.assertEqual(detalle["run"]["parameters"], {"topic": "facturas"})
        self.assertEqual(detalle["current_versions"]["clustering"], CLUSTERING_VERSION)
        por_id = {e["id"]: e for e in detalle["evidence"]}
        self.assertEqual(set(por_id), {"hackernews:70", "hackernews:71"})
        self.assertEqual(por_id["hackernews:71"]["text"], largo, "el texto entero, no el extracto")
        self.assertEqual(por_id["hackernews:71"]["title"], "Título de la 71")
        self.assertEqual(por_id["hackernews:71"]["data_source"], "real")
        self.assertEqual(por_id["hackernews:70"]["attribution"]["badge"], "Hacker News")
        self.assertNotIn("author_hash", por_id["hackernews:70"], "sin autores (R9)")

    def test_un_veredicto_que_no_existe_o_un_id_que_no_es_uuid_da_none(self):
        self.assertIsNone(self.run_store(
            lambda store: verdict_detail(store, "00000000-0000-0000-0000-00000000dead")))
        self.assertIsNone(self.run_store(lambda store: verdict_detail(store, "no-es-un-uuid")))

    def test_mas_alla_del_top_6_el_resto_va_aparte_en_el_mismo_orden(self):
        # C1 (D-C2): el Radar enseña el Top 6 y la lista completa desde la misma lectura.
        items = [pieza(n) for n in range(40, 48)]

        async def guardar(store):
            await store.upsert_evidence(items)
            run_id = await store.start_run("perfil", trigger_source="multifuente", data_source="real")
            await store.save_verdicts(run_id, [
                veredicto(f"k{n}", "DESCARTAR", float(n), [items[n].id]) for n in range(8)
            ])
            return run_id

        run_id = self.run_store(guardar)
        top = self.run_store(lambda store: top_verdicts(store, run_id))
        self.assertEqual([v["cluster_key"] for v in top["verdicts"]], [f"k{n}" for n in (7, 6, 5, 4, 3, 2)])
        self.assertEqual([v["cluster_key"] for v in top["rest"]], ["k1", "k0"])
        self.assertEqual(top["rest"][0]["evidence"][0]["id"], "hackernews:41")

    def test_el_feed_de_evidencia_es_lo_mas_reciente_sin_duplicados_y_con_atribucion(self):
        from core.sources.dedup import Duplicate

        viejo, nuevo, copia = pieza(60), pieza(61), pieza(62)
        nuevo = nuevo.model_copy(update={"created_at": AHORA - timedelta(days=1), "title": "Título"})
        copia = copia.model_copy(update={"created_at": AHORA})

        async def guardar(store):
            await store.upsert_evidence([viejo, nuevo, copia])
            await store.save_duplicates([Duplicate(copia.id, nuevo.id, "fingerprint", None)])
            return await recent_evidence(store, limit=2)

        feed = self.run_store(guardar)
        self.assertEqual([e["id"] for e in feed], ["hackernews:61", "hackernews:60"])
        self.assertEqual(feed[0]["title"], "Título")
        self.assertEqual(feed[0]["excerpt"], "queja inventada número 61")
        self.assertEqual(feed[0]["attribution"],
                         {"badge": "Hacker News", "site": "Ask HN", "url": "https://example.com/61"})
        self.assertEqual((feed[0]["source"], feed[0]["data_source"]), ("hackernews", "real"))
        self.assertNotIn("author_hash", feed[0], "el feed no lleva autores (R9)")

    def test_las_identidades_anteriores_salen_de_la_ultima_lectura(self):
        from core.judge.store import previous_identities

        items = [pieza(n) for n in range(30, 33)]
        uuid_fijo = "22222222-2222-2222-2222-222222222222"

        async def guardar(store):
            await store.upsert_evidence(items)
            run_id = await store.start_run("perfil", trigger_source="multifuente", data_source="real")
            v = veredicto("id", "INVESTIGAR MÁS", 10.0, [i.id for i in items])
            v["opportunity_id"] = uuid_fijo
            await store.save_verdicts(run_id, [v])
            return await previous_identities(store)

        previos = {p.opportunity_id: p for p in self.run_store(guardar)}
        self.assertEqual(previos[uuid_fijo].miembros, {i.id for i in items})
        self.assertEqual(previos[uuid_fijo].palabras, {"facturas"})

    def test_un_veredicto_invalido_no_entra(self):
        import psycopg

        async def guardar(store):
            await store.upsert_evidence([pieza(20)])
            run_id = await store.start_run("perfil", trigger_source="multifuente", data_source="real")
            await store.save_verdicts(run_id, [veredicto("x", "QUIZÁS", 1.0, ["hackernews:20"])])

        with self.assertRaises(psycopg.errors.CheckViolation):
            self.run_store(guardar)


if __name__ == "__main__":
    unittest.main()
