"""Dobles del SDK de Gemini compartidos por los tests: un catálogo de modelos y
el control de prueba (registro en memoria de core.llm.control)."""

from types import SimpleNamespace


def modelo(nombre, acciones=("generateContent",)):
    return SimpleNamespace(
        name=f"models/{nombre}", display_name=nombre.upper(),
        input_token_limit=1_000_000, output_token_limit=65_536,
        supported_actions=list(acciones),
    )


CATALOGO = [
    modelo("gemini-2.5-flash"),
    modelo("gemini-3.5-flash"),
    modelo("gemini-3.6-flash"),
    modelo("gemini-3.6-flash-lite"),
    modelo("gemini-3.1-pro-preview"),
    modelo("text-embedding-004", acciones=("embedContent",)),
]


class ClienteConCatalogo:
    """Doble del SDK: lista el catálogo y cuenta las llamadas."""

    llamadas_a_list = 0

    def __init__(self, _clave=None):
        self.models = self

    def list(self):
        ClienteConCatalogo.llamadas_a_list += 1
        return iter(CATALOGO)


def control_de_prueba(run_id=None):
    """Un ControlDeGemini con registro en memoria (el proveedor no se crea sin control)."""
    from core.llm.control import ControlDeGemini, RegistroEnMemoria

    return ControlDeGemini(RegistroEnMemoria(), run_id=run_id)
