"""
Paquete de pruebas de SENTRA.

Su existencia permite ejecutar la suite de forma recursiva indicando un
directorio raiz explicito:

    python -m unittest discover -s tests -p "test_*.py" -t .

Al importarlo se instala la red de seguridad de tests/_base_real.py: ningún
test puede conectar a la base real (la prueba de humo la libera).
"""

from tests._base_real import proteger

proteger()
