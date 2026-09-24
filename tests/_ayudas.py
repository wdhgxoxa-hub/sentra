"""Ayudas de tipos para los tests (D4)."""


def presente[T](valor: T | None) -> T:
    """El valor que el test da por existente. Si llega None, el test falla
    aquí con un mensaje claro en vez de con un AttributeError más adelante."""
    if valor is None:
        raise AssertionError("se esperaba un valor y llegó None")
    return valor
