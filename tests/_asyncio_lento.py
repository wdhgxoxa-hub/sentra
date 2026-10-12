"""
Un paso que bloquea el bucle de asyncio es un fallo, no una línea de registro
=============================================================================

`IsolatedAsyncioTestCase` corre cada prueba con asyncio en modo depuración: si
un paso del bucle tarda más de `slow_callback_duration` (0,1 s), asyncio solo
lo apunta en su registro («Executing <Task …> took 0.117 seconds») y la prueba
pasa. Eso es un aviso, y la compuerta es de 0 avisos (2026-10-12): esta red
convierte ese registro en un error de la prueba que lo provoca.

No se sube el umbral: el aviso dice que algo síncrono no deja correr al resto
del bucle. Se arregla la causa (código de la app fuera del bucle con
`asyncio.to_thread`, o una prueba que no simule de un tirón lo que en
producción espera a la red).
"""

from __future__ import annotations

import logging


class BucleBloqueado(AssertionError):
    """Un paso del bucle de asyncio superó `slow_callback_duration`."""


class _Vigia(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if record.msg == "Executing %s took %.3f seconds":
            # Se lanza desde el propio bucle: sale por run_until_complete y la
            # prueba en curso termina en error con este mensaje.
            raise BucleBloqueado(f"asyncio: {record.getMessage()}")


_VIGIA = _Vigia(level=logging.WARNING)


def vigilar() -> None:
    """Instala la red una sola vez en el registro «asyncio»."""
    registro = logging.getLogger("asyncio")
    if _VIGIA not in registro.handlers:
        registro.addHandler(_VIGIA)
