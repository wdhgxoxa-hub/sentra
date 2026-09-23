"""
Motor de arquitectura (Google Gemini)
=====================================

Toma un cluster de quejas y le pide a Gemini un plan de construcción en dos
fases: un MVP que se pueda levantar en un par de días y un producto de verdad
para cuando el MVP valide.

A diferencia del sintetizador de `blueprint.py`, que es determinista y no
inventa, aquí sí hay un modelo generativo: lo que devuelve son *propuestas*
—stack, esquema, código— que hay que revisar antes de ejecutar. La evidencia
del radar entra como dato de entrada y el prompt insiste en que las cifras no
se adornen, pero nada de lo que salga de aquí es una medición.

La clave vive en el `.env` del proyecto, nunca en la base ni en el frontend,
igual que las credenciales de Reddit.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator, Mapping, Optional, Tuple

# Los lectores tolerantes del cluster ya existen en el sintetizador: leen las
# dos grafías de cada campo y saben mirar dentro de `breakdown`. Duplicarlos
# aquí sería asegurarse de que un día dejen de coincidir.
from core.intelligence.blueprint import _campo, _citas, _lista, _numero
from core.intelligence.gemini_client import GeminiError, stream_text

MODELO_POR_DEFECTO = "gemini-2.5-pro"

#: Modelos ofrecidos en la interfaz. El Pro va primero a propósito: esto es
#: diseño de arquitectura, donde importa más razonar bien que responder rápido.
MODELOS_DISPONIBLES = ("gemini-2.5-pro", "gemini-2.5-flash")

IDIOMA_POR_DEFECTO = "es"

ClientFactory = Callable[[str], Any]


class GeminiSinConfigurar(GeminiError):
    """No hay clave de API guardada."""


# --- Instrucción de sistema --------------------------------------------------

SISTEMA_ES = """\
Eres un arquitecto de software senior. Recibes la evidencia real de un problema
detectado en foros públicos y devuelves un plan de construcción ejecutable.

Escribe en Markdown, en español, con esta estructura exacta y nada más:

# FASE 1: MVP EXPRESS (24-48 h)

## Lógica central
Lo mínimo indispensable para quitar el dolor descrito. Una lista corta: si algo
no ataca la queja concreta, fuera.

## Stack mínimo y estructura de carpetas
El stack más aburrido que resuelva esto, y por qué. Después, el árbol de
carpetas en un bloque de código.

## Esquema SQL inicial
Un bloque ```sql con las tablas imprescindibles, claves e índices.

## Endpoints mínimos
Tabla de endpoints REST o RPC: método, ruta, para qué sirve.

## Código del módulo principal
Un bloque de código **funcional y completo** del núcleo, listo para copiar y
ejecutar. Nada de `TODO`, ni de funciones vacías, ni de pseudocódigo.

# FASE 2: PRODUCTO PRO / SCALE

## Hoja de ruta
Qué se construye después y en qué orden, atado a lo que pide la demanda que se
ve en la evidencia.

## Monetización
Modelo de cobro y precio orientativo, coherente con la disposición a pagar que
traen los datos. Si la evidencia no muestra ninguna, dilo y propón cómo
averiguarla antes de poner precio.

## Infraestructura
Despliegue, observabilidad y arquitectura para cuando haya usuarios de verdad.

Reglas:
- Apóyate en las cifras y citas que te den; no inventes datos de mercado ni
  número de usuarios.
- Si algo no se puede deducir de la evidencia, dilo en una línea en lugar de
  rellenar.
- Prefiere lo concreto a lo genérico: nombres de tablas, rutas, ficheros.
"""

SISTEMA_EN = """\
You are a senior software architect. You receive real evidence of a problem
spotted in public forums and return an executable build plan.

Write in Markdown, in English, with this exact structure and nothing else:

# FASE 1: MVP EXPRESS (24-48 h)

## Core logic
The bare minimum that removes the pain described. A short list: if something
does not attack the specific complaint, drop it.

## Minimal stack and folder layout
The most boring stack that solves this, and why. Then the folder tree in a code
block.

## Initial SQL schema
A ```sql block with the essential tables, keys and indexes.

## Minimal endpoints
A table of REST or RPC endpoints: method, path, what it is for.

## Main module code
A **working, complete** code block for the core, ready to copy and run. No
`TODO`s, no empty functions, no pseudocode.

# FASE 2: PRO / SCALE PRODUCT

## Roadmap
What gets built next and in what order, tied to the demand visible in the
evidence.

## Monetisation
Pricing model and a ballpark figure, consistent with the willingness to pay in
the data. If the evidence shows none, say so and propose how to find out before
setting a price.

## Infrastructure
Deployment, observability and architecture for when there are real users.

Rules:
- Lean on the figures and quotes provided; do not invent market data or user
  counts.
- If something cannot be derived from the evidence, say so in one line instead
  of padding.
- Prefer the concrete over the generic: table names, routes, file names.
"""


def _nivel_de_pago(factor: float, idioma: str) -> str:
    if idioma == "es":
        if factor >= 0.66:
            return "explícita (se habla de pagar con todas las letras)"
        if factor >= 0.33:
            return "implícita (se habla de tiempo perdido, no de dinero)"
        return "ninguna (nadie menciona pagar)"
    if factor >= 0.66:
        return "explicit (people say they would pay, in plain words)"
    if factor >= 0.33:
        return "implicit (they talk about wasted time, not money)"
    return "none (nobody mentions paying)"


def build_prompt(
    cluster: Mapping[str, Any], language: str = IDIOMA_POR_DEFECTO
) -> Tuple[str, str]:
    """Arma la instrucción de sistema y el dossier del problema.

    Devuelve `(sistema, peticion)`. El dossier lleva solo lo que hay en la base:
    cifras, comunidades y citas textuales. Nada de perfiles de usuario
    inventados, que es lo que un modelo rellenaría solo si se le deja.
    """
    idioma = "en" if language == "en" else "es"
    sistema = SISTEMA_EN if idioma == "en" else SISTEMA_ES

    etiqueta = str(_campo(cluster, "label", "")).strip()
    trabajo = str(_campo(cluster, "job_statement", "")).strip()
    claves = ", ".join(_lista(cluster, "keywords"))
    comunidades = ", ".join(f"r/{s}" for s in _lista(cluster, "subreddits"))
    apanos = _lista(cluster, "current_solutions")
    menciones = int(_numero(cluster, "mention_count"))
    puntuacion = _numero(cluster, "final_score")
    urgencia = str(_campo(cluster, "urgency_tier", ""))
    pago = _nivel_de_pago(_numero(cluster, "paid_signal_factor"), idioma)
    citas = _citas(cluster)

    if idioma == "es":
        sin_apanos = "ninguna citada por los usuarios"
        lineas = [
            f"Problema: {etiqueta}",
            f"Palabras que lo identifican: {claves}",
            f"Volumen: {menciones} menciones en {comunidades}",
            f"Intensidad: {puntuacion:.0f}/100 (urgencia {urgencia})",
            f"Disposición a pagar detectada: {pago}",
            f"Soluciones que ya usan: {', '.join(apanos) if apanos else sin_apanos}",
            "",
            f"Citas textuales ({len(citas)} distintas):",
        ]
    else:
        sin_apanos = "none quoted by users"
        lineas = [
            f"Problem: {etiqueta}",
            f"Identifying keywords: {claves}",
            f"Volume: {menciones} mentions across {comunidades}",
            f"Intensity: {puntuacion:.0f}/100 ({urgencia} urgency)",
            f"Willingness to pay detected: {pago}",
            f"Workarounds in use: {', '.join(apanos) if apanos else sin_apanos}",
            "",
            f"Verbatim quotes ({len(citas)} distinct):",
        ]

    if trabajo:
        etiqueta_trabajo = (
            "Trabajo por hacer, según el motor" if idioma == "es"
            else "Job to be done, per the engine"
        )
        lineas.insert(2, f"{etiqueta_trabajo}: {trabajo}")

    for cita in citas:
        lineas.append(f'- "{cita.quote}" — r/{cita.subreddit}')

    if not citas:
        lineas.append("- " + ("(no hay citas guardadas)" if idioma == "es" else "(no quotes stored)"))

    return sistema, "\n".join(lineas)


# --- Llamada al modelo -------------------------------------------------------


def _config(sistema: str) -> Any:
    from google.genai import types

    return types.GenerateContentConfig(system_instruction=sistema)


def stream_architecture(
    cluster: Mapping[str, Any],
    *,
    api_key: str,
    model: str = MODELO_POR_DEFECTO,
    language: str = IDIOMA_POR_DEFECTO,
    client_factory: Optional[ClientFactory] = None,
) -> Iterator[str]:
    """Pide el plan a Gemini y va soltando el texto según llega.

    Se transmite en lugar de esperar al final porque un documento con código
    tarda bastante con un modelo de razonamiento: sin ver texto aparecer,
    cualquiera daría por colgada la aplicación.
    """
    if not (api_key or "").strip():
        raise GeminiSinConfigurar(
            "No hay clave de API de Gemini guardada. Se configura en Ajustes."
        )

    sistema, peticion = build_prompt(cluster, language)
    yield from stream_text(
        api_key,
        model=model,
        contents=peticion,
        config=_config(sistema),
        client_factory=client_factory,
    )


def probe_api_key(
    api_key: str,
    *,
    model: str = MODELO_POR_DEFECTO,
    client_factory: Optional[ClientFactory] = None,
) -> Tuple[bool, str]:
    """Comprueba que la clave sirve, con la llamada más barata posible.

    Devuelve `(ok, detalle)` en lugar de lanzar: quien pulsa «probar» espera
    una respuesta, no una excepción.
    """
    if not (api_key or "").strip():
        return False, "No hay clave que probar."

    try:
        # Basta el primer trozo: si llega, la clave y el modelo responden.
        next(iter(stream_text(
            api_key,
            model=model,
            contents="ping",
            config=_config("Responde solo: ok"),
            client_factory=client_factory,
        )), None)
    except GeminiError as exc:
        return False, f"La clave no funciona: {exc}"

    return True, f"Clave válida. Modelo {model} disponible."
