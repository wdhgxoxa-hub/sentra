"""
Traductor de citas
==================

Las quejas llegan en inglés y hay que leerlas rápido. Esto las traduce con dos
motores, según lo que haya configurado:

- **Gemini**, si hay clave. Traduce conservando el tono: una queja escrita con
  fastidio tiene que sonar fastidiada, porque ese tono *es* el dato.
- **Sin conexión**, si no la hay. El corpus de demostración viene traducido a
  mano frase a frase; para lo demás queda un diccionario de expresiones que
  sustituye lo que reconoce y deja el resto en su idioma.

Lo segundo se marca siempre como aproximado. Una traducción a medias que se
presenta como buena es peor que no traducir: sobre estas frases se decide si
construir algo, y una cita mal entendida cambia la decisión.

Solo se guardan en caché las traducciones del modelo, que son las que cuestan
dinero. Las de sin conexión son manipulación de cadenas y sale más barato
rehacerlas que recordarlas; además, así mejoran solas en cuanto se configura
una clave.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

MODELO_POR_DEFECTO = "gemini-2.5-flash"

IDIOMAS = {"es": "Spanish", "en": "English"}

ClientFactory = Callable[[str], Any]


@dataclass(frozen=True)
class Translation:
    text: str
    #: "gemini" o "offline".
    engine: str
    #: True cuando el texto solo está traducido en parte.
    approximate: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "engine": self.engine,
            "approximate": self.approximate,
        }


# --- Caché -------------------------------------------------------------------

_CACHE: Dict[Tuple[str, str], Translation] = {}
MAX_CACHE = 2000


def clear_cache() -> None:
    _CACHE.clear()


def _recordar(texto: str, idioma: str, traduccion: Translation) -> None:
    if len(_CACHE) >= MAX_CACHE:
        # Tirar lo más viejo basta: son citas de una sesión, no un índice.
        for clave in list(_CACHE)[: MAX_CACHE // 4]:
            _CACHE.pop(clave, None)
    _CACHE[(texto, idioma)] = traduccion


# --- Motor sin conexión ------------------------------------------------------

#: Corpus de demostración, traducido a mano. Son las frases que se ven al
#: probar la aplicación sin credenciales, así que merecen una traducción de
#: verdad y no un apaño.
PRETRADUCIDAS: Dict[str, str] = {
    # Títulos
    "manual invoice export is broken again":
        "La exportación manual de facturas vuelve a estar rota",
    "invoice export broken after the update":
        "La exportación de facturas se rompió tras la actualización",
    "manual invoice workflow is broken":
        "El flujo manual de facturación está roto",
    "bank reconciliation is manual and slow":
        "La conciliación bancaria es manual y lenta",
    "manual bank matching every month":
        "Cuadre bancario a mano todos los meses",
    "support replies are a repetitive task":
        "Responder soporte es una tarea repetitiva",
    "happy friday everyone": "Feliz viernes a todos",
    "this tool fixed my broken invoice problem":
        "Esta herramienta me arregló el problema de facturación",
    "manual invoice export broken once more":
        "La exportación manual de facturas, rota una vez más",
    "invoice export is broken and manual":
        "La exportación de facturas está rota y es manual",
    "manual reconciliation wastes my week":
        "La conciliación manual me come la semana",
    "repetitive support work takes hours":
        "El trabajo repetitivo de soporte lleva horas",
    "manual support replies every day":
        "Respuestas de soporte a mano todos los días",
    "deploying takes forever to finish":
        "Desplegar tarda una eternidad en terminar",
    "just saying hello to the sub": "Solo paso a saludar al foro",
    # Cuerpos
    "the invoice export is completely broken and it is frustrating. i would pay "
    "for a tool that fixes this manual invoice process.":
        "La exportación de facturas está completamente rota y es frustrante. "
        "Pagaría por una herramienta que arregle este proceso manual de "
        "facturación.",
    "this manual invoice export is broken and wastes hours every week.":
        "Esta exportación manual de facturas está rota y hace perder horas cada "
        "semana.",
    "reconciling the bank statement by hand is a tedious process. i would pay "
    "for something that automates this manual matching.":
        "Conciliar el extracto bancario a mano es un proceso tedioso. Pagaría "
        "por algo que automatice este cuadre manual.",
    "answering the same support questions is a repetitive task that takes hours "
    "every day. i need automation for this manual work.":
        "Responder las mismas preguntas de soporte es una tarea repetitiva que "
        "lleva horas todos los días. Necesito automatizar este trabajo manual.",
    "the release step takes forever to finish and kills my productivity.":
        "El paso de publicación tarda una eternidad en terminar y me destroza "
        "la productividad.",
    "hope you all have a great weekend.":
        "Espero que paséis un buen fin de semana.",
    "nice to meet you all.": "Encantado de conoceros.",
    "use my referral link and promo code save20 for a discount, ref=99.":
        "Usa mi enlace de referido y el código SAVE20 para un descuento, ref=99.",
}

#: Expresiones frecuentes en quejas sobre software. De más larga a más corta:
#: si "is broken" se sustituyera después de "broken", quedaría "is roto".
EXPRESIONES: Sequence[Tuple[str, str]] = (
    ("i would pay for", "pagaría por"),
    ("takes forever to finish", "tarda una eternidad en terminar"),
    ("takes forever", "tarda una eternidad"),
    ("wastes hours", "hace perder horas"),
    ("takes hours", "lleva horas"),
    ("every single day", "todos los santos días"),
    ("every week", "cada semana"),
    ("every month", "cada mes"),
    ("every day", "todos los días"),
    ("by hand", "a mano"),
    ("is completely broken", "está completamente roto"),
    ("are broken", "están rotos"),
    ("is broken", "está roto"),
    ("kills my productivity", "me destroza la productividad"),
    ("repetitive task", "tarea repetitiva"),
    ("manual work", "trabajo manual"),
    ("bank statement", "extracto bancario"),
    ("bank reconciliation", "conciliación bancaria"),
    ("invoice export", "exportación de facturas"),
    ("support questions", "preguntas de soporte"),
    ("release step", "paso de publicación"),
    ("referral link", "enlace de referido"),
    ("promo code", "código promocional"),
    ("frustrating", "frustrante"),
    ("tedious", "tedioso"),
    ("broken", "roto"),
    ("manual", "manual"),
    ("invoice", "factura"),
    ("automation", "automatización"),
    ("automates", "automatiza"),
    ("workflow", "flujo de trabajo"),
    ("deploying", "desplegar"),
    ("again", "otra vez"),
    ("slow", "lento"),
)


def _mayuscula_inicial(texto: str) -> str:
    return texto[:1].upper() + texto[1:] if texto else texto


def _offline_una_linea(linea: str) -> Tuple[str, bool]:
    """Traduce una línea. Devuelve `(texto, aproximada)`."""
    limpia = linea.strip()
    if not limpia:
        return linea, False

    exacta = PRETRADUCIDAS.get(limpia.lower())
    if exacta:
        return exacta, False

    salida = linea
    tocado = False
    for original, destino in EXPRESIONES:
        patron = re.compile(rf"\b{re.escape(original)}\b", re.IGNORECASE)
        if patron.search(salida):
            salida = patron.sub(destino, salida)
            tocado = True

    if not tocado:
        # Nada reconocido: se devuelve el original. Inventar aquí seria peor.
        return linea, True

    return _mayuscula_inicial(salida), True


def _offline(texto: str) -> Translation:
    if not texto.strip():
        return Translation(texto, "offline", False)

    lineas, aproximada = [], False
    for linea in texto.split("\n"):
        traducida, parcial = _offline_una_linea(linea)
        lineas.append(traducida)
        aproximada = aproximada or parcial

    return Translation("\n".join(lineas), "offline", aproximada)


# --- Motor con modelo --------------------------------------------------------


def _cliente_real(api_key: str) -> Any:
    from google import genai

    return genai.Client(api_key=api_key)


def _prompt(textos: Sequence[str], idioma: str) -> str:
    nombre = IDIOMAS.get(idioma, IDIOMAS["es"])
    entrada = json.dumps(list(textos), ensure_ascii=False)
    return (
        f"Translate each string in this JSON array into {nombre}.\n"
        "Keep the informal, angry or tired tone of the original: the tone is "
        "part of the data. Keep product names, code, URLs and promo codes "
        "untouched. Do not explain anything.\n"
        f"Answer with a JSON array of {len(textos)} strings, nothing else.\n\n"
        f"{entrada}"
    )


def _parsear(bruto: str, esperados: int) -> Optional[List[str]]:
    """Saca el array del texto del modelo, tolerando el cercado en ```json."""
    texto = (bruto or "").strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```[a-z]*\s*", "", texto)
        texto = re.sub(r"\s*```$", "", texto)

    try:
        datos = json.loads(texto)
    except (ValueError, TypeError):
        return None

    if not isinstance(datos, list) or len(datos) != esperados:
        return None
    if not all(isinstance(elemento, str) for elemento in datos):
        return None
    return datos


def _con_modelo(
    textos: Sequence[str],
    idioma: str,
    api_key: str,
    model: str,
    client_factory: Optional[ClientFactory],
) -> Optional[List[str]]:
    from google.genai import types

    fabrica = client_factory or _cliente_real
    try:
        cliente = fabrica(api_key)
        respuesta = cliente.models.generate_content(
            model=model,
            contents=_prompt(textos, idioma),
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return _parsear(getattr(respuesta, "text", ""), len(textos))
    except Exception:
        # Cualquier fallo cae al modo sin conexión: la vista tiene que
        # enseñar algo, y el original traducido a medias es mejor que un hueco.
        logger.warning("La traduccion con Gemini fallo; se usa el modo offline")
        return None


# --- Entrada pública ---------------------------------------------------------


def translate(
    texts: Sequence[str],
    target: str = "es",
    *,
    api_key: str = "",
    model: str = MODELO_POR_DEFECTO,
    client_factory: Optional[ClientFactory] = None,
) -> List[Translation]:
    """Traduce una tanda de citas al idioma pedido.

    Devuelve una traducción por texto y en el mismo orden, pase lo que pase.
    """
    if not texts:
        return []

    idioma = target if target in IDIOMAS else "es"
    salida: List[Optional[Translation]] = [None] * len(texts)
    pendientes: List[int] = []

    for indice, texto in enumerate(texts):
        if not texto.strip():
            salida[indice] = Translation(texto, "offline", False)
            continue
        guardada = _CACHE.get((texto, idioma))
        if guardada:
            salida[indice] = guardada
        else:
            pendientes.append(indice)

    if pendientes and api_key.strip():
        crudos = [texts[i] for i in pendientes]
        traducidos = _con_modelo(crudos, idioma, api_key, model, client_factory)
        if traducidos:
            for indice, texto in zip(pendientes, traducidos):
                traduccion = Translation(texto, "gemini", False)
                _recordar(texts[indice], idioma, traduccion)
                salida[indice] = traduccion
            pendientes = []

    for indice in pendientes:
        salida[indice] = _offline(texts[indice])

    return [t for t in salida if t is not None]
