"""
Red real prohibida en los tests
===============================

Un test que monta el sidecar y toca una ruta de Gemini llamaría a la API de
verdad si nadie sustituye el cliente del SDK. Pasó: al empezar a listar
modelos antes de generar, cuatro tests antiguos llamaron a models.list con
su clave ficticia. `prohibir_red_real` hace que eso falle en el acto y diga
por qué; el test que necesita un catálogo lo parchea encima. Lo mismo para
el cliente HTTP de las fuentes (Hacker News, Stack Exchange...).
"""

from __future__ import annotations

import unittest
from typing import NoReturn
from unittest import mock


def _cliente_prohibido(_clave: str) -> NoReturn:
    raise AssertionError(
        "Red real prohibida en los tests: sustituye core.llm.gemini._cliente_real por un doble."
    )


def _http_prohibido() -> NoReturn:
    raise AssertionError(
        "Red real prohibida en los tests: sustituye core.sources.http.new_client por un "
        "cliente con httpx.MockTransport."
    )


def _juez_prohibido(*_args: object) -> NoReturn:
    raise AssertionError(
        "Base real prohibida en los tests: el juez del sidecar escribiría en PostgreSQL. "
        "Sustituye core.orchestration.sidecar.multiscan._juzgar por un doble."
    )


def prohibir_red_real(caso: unittest.TestCase) -> None:
    """Durante el test no se pueden crear ni el cliente del SDK de Gemini ni el
    cliente HTTP de las fuentes."""
    gemini = mock.patch("core.llm.gemini._cliente_real", _cliente_prohibido)
    gemini.start()
    caso.addCleanup(gemini.stop)
    fuentes = mock.patch("core.sources.http.new_client", _http_prohibido)
    fuentes.start()
    caso.addCleanup(fuentes.stop)
    juez = mock.patch("core.orchestration.sidecar.multiscan._juzgar", _juez_prohibido)
    juez.start()
    caso.addCleanup(juez.stop)
