"""Calcula los vectores e5 del conjunto dorado de agrupación (B3).

    python scripts/embed_golden_clusters.py

Escribe tests/fixtures/golden_clusters_e5.npz con los ids, los vectores y el
modelo y pooling que los produjeron. Los tests de calibración leen ese
fichero (no cargan el modelo de 2,24 GB) y comprueban que sus metadatos
siguen coincidiendo con el código. Volver a ejecutarlo solo si cambia el
conjunto dorado, el modelo o el pooling.

Además (clustering-v5) escribe la versión «publicación» de cada ítem: su
frase del problema rodeada del contexto que comparten los posts reales del
mismo tema (saludo, stack, código, agradecimiento), en
golden_clusters_posts.json, y sus vectores en golden_clusters_posts_e5.npz.
Mide si agrupar por la frase del problema (lo que hace el juez) supera a
agrupar por el texto entero. Las plantillas se fijaron antes de medir; la
elección por ítem es determinista (semilla = id). Textos INVENTADOS (R8).
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core.storage.embeddings import (
    E5_POOLING,
    MULTILINGUAL_MODEL_NAME,
    FastEmbedEmbedder,
)

FIXTURES = RAIZ / "tests" / "fixtures"
DORADO = FIXTURES / "golden_clusters.json"
SALIDA = FIXTURES / "golden_clusters_e5.npz"
PUBLICACIONES = FIXTURES / "golden_clusters_posts.json"
SALIDA_PUBLICACIONES = FIXTURES / "golden_clusters_posts_e5.npz"

#: Contexto común a los posts reales del tema (notificaciones y correo): no
#: distingue ningún problema, que es justo lo que confunde a los vectores del
#: texto entero.
CONTEXTO = {
    "en": {
        "antes": [
            "Hi all, long time lurker here.",
            "We run a small SaaS on AWS with a Postgres backend and send a few thousand emails a day.",
            "Our stack is Node.js with a queue for background jobs; notifications go out by email and push.",
            "For context, we're a team of three and I handle most of the infrastructure.",
            "I've read the docs and a few Stack Overflow answers but nothing seems to fit our case.",
            "We use a transactional email provider and a mobile app for the notifications.",
        ],
        "despues": [
            "Any pointers appreciated, thanks in advance!",
            "Code (simplified): sendNotification(user, template, { channel: 'email' }).",
            "Happy to share more details about our setup if it helps.",
            "Thanks for reading, this has been bugging us for weeks.",
        ],
    },
    "es": {
        "antes": [
            "Hola a todos, os leo desde hace tiempo.",
            "Tenemos un SaaS pequeño en AWS con PostgreSQL y mandamos unos miles de correos al día.",
            "Usamos Node.js con una cola para los trabajos en segundo plano; los avisos salen por correo y push.",
            "Para contexto: somos tres y yo llevo casi toda la infraestructura.",
            "He leído la documentación y varias respuestas en Stack Overflow, pero nada encaja con nuestro caso.",
            "Usamos un proveedor de correo transaccional y una app móvil para las notificaciones.",
        ],
        "despues": [
            "Cualquier pista es bienvenida, ¡gracias!",
            "Código (simplificado): enviarAviso(usuario, plantilla, { canal: 'correo' }).",
            "Puedo dar más detalles del montaje si ayuda.",
            "Gracias por leer, esto nos trae de cabeza desde hace semanas.",
        ],
    },
}


def publicacion(item: dict) -> str:
    """La frase del problema dentro de un post con el contexto común del tema."""
    rng = random.Random(str(item["id"]))
    contexto = CONTEXTO[item["lang"]]
    antes = rng.sample(contexto["antes"], 2)
    despues = rng.choice(contexto["despues"])
    return " ".join([*antes, item["text"], despues])


def _guardar(salida: Path, items: list[dict], vectores: np.ndarray, version: str) -> None:
    np.savez_compressed(
        salida, ids=np.asarray([i["id"] for i in items]), vectors=vectores,
        model=np.asarray(MULTILINGUAL_MODEL_NAME), pooling=np.asarray(E5_POOLING),
        golden_version=np.asarray(version))


def main() -> None:
    conjunto = json.loads(DORADO.read_text(encoding="utf-8"))
    items = conjunto["items"]
    embebedor = FastEmbedEmbedder(MULTILINGUAL_MODEL_NAME)
    vectores = np.asarray(embebedor.embed_batch([i["text"] for i in items]), dtype=np.float32)
    _guardar(SALIDA, items, vectores, conjunto["version"])
    print(f"{len(items)} vectores de {vectores.shape[1]} dimensiones en {SALIDA.name}")

    posts = [{"id": i["id"], "group": i["group"], "lang": i["lang"], "problem": i["text"],
              "post": publicacion(i)} for i in items]
    PUBLICACIONES.write_text(json.dumps(
        {"version": conjunto["version"], "note": (
            "Versión «publicación» del conjunto dorado (clustering-v5): la frase del problema "
            "rodeada del contexto común del tema. Generado por scripts/embed_golden_clusters.py; "
            "textos INVENTADOS (R8)."), "items": posts}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    vectores_posts = np.asarray(embebedor.embed_batch([p["post"] for p in posts]), dtype=np.float32)
    _guardar(SALIDA_PUBLICACIONES, items, vectores_posts, conjunto["version"])
    print(f"{len(posts)} publicaciones en {PUBLICACIONES.name} y {SALIDA_PUBLICACIONES.name}")


if __name__ == "__main__":
    main()
