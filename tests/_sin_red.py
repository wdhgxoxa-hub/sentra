"""
Red real prohibida en los tests
===============================

Un test que monta el sidecar y toca una ruta de Gemini llamaría a la API de
verdad si nadie sustituye el cliente del SDK. Pasó: al empezar a listar
modelos antes de generar, cuatro tests antiguos llamaron a models.list con
su clave ficticia. `prohibir_red_real` hace que eso falle en el acto y diga
por qué; el test que necesita un catálogo lo parchea encima.
"""

from __future__ import annotations

import unittest
from typing import Any, NoReturn
from unittest import mock


def _cliente_prohibido(_clave: str) -> NoReturn:
    raise AssertionError(
        "Red real prohibida en los tests: sustituye core.llm.gemini._cliente_real por un doble."
    )


def prohibir_red_real(caso: unittest.TestCase) -> Any:
    """Durante el test, el cliente real del SDK de Gemini no se puede crear."""
    parche = mock.patch("core.llm.gemini._cliente_real", _cliente_prohibido)
    parche.start()
    caso.addCleanup(parche.stop)
    return parche
