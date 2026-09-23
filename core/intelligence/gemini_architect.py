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

from collections.abc import Callable, Iterator, Mapping
from typing import Any

# Los lectores tolerantes del cluster ya existen en el sintetizador: leen las
# dos grafías de cada campo y saben mirar dentro de `breakdown`. Duplicarlos
# aquí sería asegurarse de que un día dejen de coincidir.
from core.intelligence.blueprint import _campo, _citas, _lista, _numero, _stats
from core.intelligence.gemini_client import (
    GeminiError,
    GeminiIncomplete,
    build_config,
    ping,
    stream_text,
)

MODELO_POR_DEFECTO = "gemini-2.5-pro"

#: Modelos ofrecidos en la interfaz. El Pro va primero a propósito: esto es
#: diseño de arquitectura, donde importa más razonar bien que responder rápido.
MODELOS_DISPONIBLES = ("gemini-2.5-pro", "gemini-2.5-flash")

IDIOMA_POR_DEFECTO = "es"

#: Límite de salida del plan. En la familia 2.5 el razonamiento cuenta dentro
#: de este límite: con menos, un plan con código se queda a medias.
MAX_OUTPUT_TOKENS = 65_536

#: Timeout de cada petición del plan (ms). Por debajo de los 600 s del puente
#: de Rust, para que el corte llegue como error tipado y no como caída.
TIMEOUT_MS = 540_000

#: La prueba de clave es una llamada mínima: si tarda, algo va mal.
PROBE_TIMEOUT_MS = 30_000
PROBE_MAX_OUTPUT_TOKENS = 1_024

#: Secciones que el plan debe traer, en el orden en que las pide el sistema.
#: Se buscan como títulos Markdown (la línea empieza por #) y por prefijo,
#: sin distinguir mayúsculas: «# FASE 1: MVP EXPRESS (24-48 h)» cuenta.
SECCIONES_OBLIGATORIAS = {
    "es": (
        "FASE 1", "Lógica central", "Stack mínimo y estructura de carpetas",
        "Esquema SQL inicial", "Endpoints mínimos", "Código del módulo principal",
        "FASE 2", "Hoja de ruta", "Monetización", "Infraestructura",
    ),
    "en": (
        "FASE 1", "Core logic", "Minimal stack and folder layout",
        "Initial SQL schema", "Minimal endpoints", "Main module code",
        "FASE 2", "Roadmap", "Monetisation", "Infrastructure",
    ),
}

#: Cómo se nombra en la lista de ausentes el aviso inicial exigido con datos
#: de demostración o de procedencia desconocida (AUD-017).
AVISO_AUSENTE = {"es": "aviso de procedencia", "en": "provenance warning"}

ClientFactory = Callable[[str], Any]


class GeminiSinConfigurar(GeminiError):
    """No hay clave de API guardada."""


# --- Instrucción de sistema --------------------------------------------------

SISTEMA_ES = """\
Eres un arquitecto de software senior. Recibes un dossier con la evidencia de
un problema —cifras, citas numeradas y su procedencia— y devuelves un plan de
construcción ejecutable.

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
- Cada afirmación sobre el problema o sobre quien lo sufre lleva entre
  corchetes el número de cita que la sostiene, por ejemplo [2]. Si ninguna cita
  la sostiene, no la hagas.
- Las etiquetas de gravedad e intención las pone un clasificador automático
  (el dossier dice cuál): son indicios, no mediciones.
"""

SISTEMA_EN = """\
You are a senior software architect. You receive a dossier with the evidence
of a problem —figures, numbered quotes and their provenance— and return an
executable build plan.

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
- Every claim about the problem or about who suffers it carries, in square
  brackets, the quote number that supports it, e.g. [2]. If no quote supports
  it, do not make it.
- Severity and intent labels come from an automatic classifier (the dossier
  says which one): they are hints, not measurements.
"""

#: Línea que el documento debe llevar al principio cuando los datos no son de
#: Reddit (AUD-017). Se pide literal para poder comprobarla después.
AVISO_DEMO = {
    "es": "> **AVISO: datos de demostración.** Este plan no se apoya en quejas "
          "de usuarios.",
    "en": "> **WARNING: demonstration data.** This plan does not rest on "
          "complaints from users.",
}
AVISO_DESCONOCIDA = {
    "es": "> **AVISO: procedencia de los datos desconocida.** No consta si "
          "proceden de Reddit o de la demostración.",
    "en": "> **WARNING: unknown data provenance.** It is not recorded whether "
          "the data comes from Reddit or from the demo.",
}

_PROCEDENCIA_REDDIT = {
    "es": "\nEl dossier trae evidencia real: publicaciones públicas de Reddit.\n",
    "en": "\nThe dossier holds real evidence: public Reddit posts.\n",
}

_EXIGE_AVISO = {
    "es": "\n{motivo} Advierte al inicio del documento, antes de «# FASE 1», "
          "con esta línea exacta:\n\n{aviso}\n",
    "en": "\n{motivo} Warn at the very top of the document, before \"# FASE 1\", "
          "with this exact line:\n\n{aviso}\n",
}

_MOTIVO_DEMO = {
    "es": "Los datos del dossier son de DEMOSTRACIÓN: los generó la propia "
          "aplicación y no proceden de ningún foro. No presentes nada como "
          "demanda comprobada.",
    "en": "The dossier data is DEMONSTRATION data: the app generated it and it "
          "does not come from any forum. Present nothing as proven demand.",
}
_MOTIVO_DESCONOCIDA = {
    "es": "No consta de dónde salen los datos del dossier. No los presentes "
          "como demanda comprobada.",
    "en": "The origin of the dossier data is not recorded. Do not present it "
          "as proven demand.",
}

_NOMBRE_MOTOR = {
    "es": {"heuristic": "heurístico", "transformers": "NLI con transformers"},
    "en": {"heuristic": "heuristic", "transformers": "NLI with transformers"},
}


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
) -> tuple[str, str]:
    """Arma la instrucción de sistema y el dossier del problema.

    Devuelve `(sistema, peticion)`. El dossier lleva solo lo que hay en la base:
    cifras, comunidades y citas textuales. Nada de perfiles de usuario
    inventados, que es lo que un modelo rellenaría solo si se le deja.
    """
    idioma = "en" if language == "en" else "es"
    fuente = _campo(cluster, "data_source")
    sistema = (SISTEMA_EN if idioma == "en" else SISTEMA_ES) + _clausula_de_procedencia(
        fuente, idioma
    )

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
    procedencia = _cabecera_de_procedencia(fuente, menciones, _stats(cluster), idioma)

    if idioma == "es":
        sin_apanos = "ninguna citada por los usuarios"
        lineas = [
            *procedencia,
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
            *procedencia,
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
        lineas.insert(len(procedencia) + 2, f"{etiqueta_trabajo}: {trabajo}")

    # Numeradas para que el plan pueda citarlas: «[2]» (AUD-017).
    for numero, cita in enumerate(citas, start=1):
        lineas.append(f'[{numero}] "{cita.quote}" — r/{cita.subreddit}')

    if not citas:
        lineas.append("- " + ("(no hay citas guardadas)" if idioma == "es" else "(no quotes stored)"))

    return sistema, "\n".join(lineas)


def _clausula_de_procedencia(fuente: Any, idioma: str) -> str:
    """Qué se le dice al modelo sobre el origen de los datos.

    Solo con datos de Reddit se afirma que la evidencia es real. Con demo, o
    sin procedencia registrada, se declara y se exige un aviso literal al
    principio del documento: un plan bien escrito sobre datos inventados es
    justo lo que alguien confundiría con una oportunidad de verdad.
    """
    if fuente == "reddit":
        return _PROCEDENCIA_REDDIT[idioma]
    if fuente == "demo":
        motivo, aviso = _MOTIVO_DEMO[idioma], AVISO_DEMO[idioma]
    else:
        motivo, aviso = _MOTIVO_DESCONOCIDA[idioma], AVISO_DESCONOCIDA[idioma]
    return _EXIGE_AVISO[idioma].format(motivo=motivo, aviso=aviso)


def _cabecera_de_procedencia(
    fuente: Any, menciones: int, stats: Mapping[str, Any], idioma: str
) -> list[str]:
    """Primeras líneas del dossier: fuente, clasificador e indeterminadas."""
    es = idioma == "es"
    if fuente == "reddit":
        origen = "Reddit (publicaciones públicas)" if es else "Reddit (public posts)"
    elif fuente == "demo":
        origen = (
            "DEMOSTRACIÓN (generados por la aplicación, no proceden de ningún foro)"
            if es else "DEMONSTRATION (generated by the app, not from any forum)"
        )
    else:
        origen = "desconocida" if es else "unknown"

    de, quejas = ("de", "quejas") if es else ("of", "complaints")
    motores = stats.get("classifier_engines")
    if isinstance(motores, Mapping) and motores:
        nombres = _NOMBRE_MOTOR[idioma]
        clasificador = ", ".join(
            f"{nombres.get(str(motor), str(motor))} ({int(n)} {de} {menciones} {quejas})"
            for motor, n in motores.items()
        )
    else:
        clasificador = "no registrado" if es else "not recorded"

    indeterminadas = stats.get("severity_undetermined")
    if isinstance(indeterminadas, (int, float)):
        gravedad = f"{int(indeterminadas)} {de} {menciones} {quejas}"
    else:
        gravedad = "no registrada" if es else "not recorded"

    if es:
        return [
            f"Procedencia: {origen}",
            f"Clasificador: {clasificador}",
            f"Gravedad indeterminada: {gravedad}",
            "",
        ]
    return [
        f"Provenance: {origen}",
        f"Classifier: {clasificador}",
        f"Undetermined severity: {gravedad}",
        "",
    ]


# --- Llamada al modelo -------------------------------------------------------


def _config(sistema: str) -> Any:
    return build_config(
        timeout_ms=TIMEOUT_MS,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        system_instruction=sistema,
    )


def _normalizar(texto: str) -> str:
    return " ".join(texto.split()).casefold()


def secciones_ausentes(texto: str, language: str, fuente: Any) -> list[str]:
    """Qué secciones exigidas no aparecen como título en el plan.

    Con datos de demo o sin procedencia, el aviso inicial (AUD-017) también
    es obligatorio y debe ir antes del primer título.
    """
    idioma = "en" if language == "en" else "es"
    lineas = texto.splitlines()
    es_titulo = [linea.strip().startswith("#") for linea in lineas]
    titulos = [
        _normalizar(linea.strip().lstrip("#"))
        for linea, titulo in zip(lineas, es_titulo, strict=True) if titulo
    ]
    ausentes = [
        seccion for seccion in SECCIONES_OBLIGATORIAS[idioma]
        if not any(t.startswith(seccion.casefold()) for t in titulos)
    ]

    if fuente != "reddit":
        aviso = (AVISO_DEMO if fuente == "demo" else AVISO_DESCONOCIDA)[idioma]
        primero = es_titulo.index(True) if True in es_titulo else len(lineas)
        if _normalizar(aviso) not in _normalizar("\n".join(lineas[:primero])):
            ausentes.append(AVISO_AUSENTE[idioma])
    return ausentes


def stream_architecture(
    cluster: Mapping[str, Any],
    *,
    api_key: str,
    model: str = MODELO_POR_DEFECTO,
    language: str = IDIOMA_POR_DEFECTO,
    client_factory: ClientFactory | None = None,
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
    partes: list[str] = []
    for texto in stream_text(
        api_key,
        model=model,
        contents=peticion,
        config=_config(sistema),
        client_factory=client_factory,
    ):
        partes.append(texto)
        yield texto

    # El documento ya se ha visto llegar, pero no se da por terminado sin
    # la estructura pedida (AUD-020).
    faltan = secciones_ausentes("".join(partes), language, _campo(cluster, "data_source"))
    if faltan:
        raise GeminiIncomplete(
            f"Faltan secciones exigidas: {', '.join(faltan)}", missing=faltan
        )


def probe_api_key(
    api_key: str,
    *,
    model: str = MODELO_POR_DEFECTO,
    client_factory: ClientFactory | None = None,
) -> tuple[bool, str]:
    """Comprueba que la clave sirve, con la llamada más barata posible.

    Devuelve `(ok, detalle)` en lugar de lanzar: quien pulsa «probar» espera
    una respuesta, no una excepción.
    """
    if not (api_key or "").strip():
        return False, "No hay clave que probar."

    try:
        ping(
            api_key,
            model=model,
            config=build_config(
                timeout_ms=PROBE_TIMEOUT_MS,
                max_output_tokens=PROBE_MAX_OUTPUT_TOKENS,
                system_instruction="Responde solo: ok",
            ),
            client_factory=client_factory,
        )
    except GeminiError as exc:
        return False, f"La clave no funciona: {exc}"

    return True, f"Clave válida. Modelo {model} disponible."
