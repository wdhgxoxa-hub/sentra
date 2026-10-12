"""
Paquete de pruebas de SENTRA.

Su existencia permite ejecutar la suite de forma recursiva indicando un
directorio raiz explicito:

    python -m unittest discover -s tests -p "test_*.py" -t .

Al importarlo se instala la red de seguridad de tests/_base_real.py: ningún
test puede conectar a la base real (la prueba de humo la libera).

También instala la de tests/_asyncio_lento.py: un paso que bloquea el bucle de
asyncio más de 0,1 s hace fallar la prueba en vez de quedar en el registro.
"""

from tests._asyncio_lento import vigilar
from tests._base_real import proteger

proteger()
vigilar()
