"""
Sintetizador de especificaciones de proyecto (PRD)
=================================================

Convierte un cluster de quejas en un documento que un equipo pueda leer y
ejecutar: qué problema hay, a quién le pasa, qué construir y cómo cobrarlo.

**Es determinista y no inventa.** No hay modelo generativo detrás: cada frase
sale de la evidencia guardada —palabras clave, comunidades, volumen, citas,
factores de puntuación—. Cuando un dato falta, el documento lo dice en voz
alta en lugar de rellenar el hueco con prosa plausible. Un PRD que se inventa
competidores o precios es peor que no tenerlo, porque se lee igual de bien.

El documento se entrega estructurado *y* como Markdown, para poder pintarlo en
la interfaz y a la vez copiarlo a Notion, GitHub o un correo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# Por encima de este factor (0.0-1.0) la gente dice que pagaría con todas las
# letras; por debajo del bajo, nadie ha hablado de dinero.
PAGO_EXPLICITO = 0.66
PAGO_IMPLICITO = 0.33

IDIOMA_POR_DEFECTO = "es"


@dataclass(frozen=True)
class Quote:
    """Una cita textual, tal como la escribió quien se quejó."""

    quote: str
    subreddit: str
    author: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "quote": self.quote,
            "subreddit": self.subreddit,
            "author": self.author,
            "url": self.url,
        }


@dataclass(frozen=True)
class Phase:
    """Una fase del alcance, con lo que entra en ella."""

    name: str
    items: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "items": list(self.items)}


@dataclass(frozen=True)
class Blueprint:
    """El documento completo."""

    product_name: str
    one_liner: str
    executive_summary: str
    problem: str
    solution: str
    mvp: list[Phase]
    why_existing_fail: str
    monetisation: str
    evidence: list[Quote]
    distinct_quotes: int
    markdown: str

    def to_dict(self) -> dict[str, Any]:
        """Forma camelCase, que es la que cruza el puente hacia la interfaz."""
        return {
            "productName": self.product_name,
            "oneLiner": self.one_liner,
            "executiveSummary": self.executive_summary,
            "problem": self.problem,
            "solution": self.solution,
            "mvp": [fase.to_dict() for fase in self.mvp],
            "whyExistingFail": self.why_existing_fail,
            "monetisation": self.monetisation,
            "evidence": [cita.to_dict() for cita in self.evidence],
            "distinctQuotes": self.distinct_quotes,
            "markdown": self.markdown,
        }


# --- Lectura tolerante del cluster -------------------------------------------
# Llega en snake_case desde PostgreSQL y en camelCase desde el puente de Rust.
# Aceptar las dos evita un traductor intermedio que solo sirve para romperse.


def _camel(nombre: str) -> str:
    cabeza, *resto = nombre.split("_")
    return cabeza + "".join(parte.title() for parte in resto)


def _campo(cluster: Mapping[str, Any], nombre: str, defecto: Any = None) -> Any:
    """Busca un campo en las dos grafias y, si no, dentro de `breakdown`.

    PostgreSQL devuelve la puntuacion en columnas sueltas; el puente de Rust
    la agrupa en `breakdown`. Sin mirar ahi, el documento salia con la
    intensidad y la gravedad a cero, que es la peor forma de equivocarse:
    un cero se lee como una medicion, no como un dato que falta.
    """
    camel = _camel(nombre)
    for clave in (nombre, camel):
        if cluster.get(clave) is not None:
            return cluster[clave]

    desglose = cluster.get("breakdown")
    if isinstance(desglose, Mapping):
        for clave in (nombre, camel):
            if desglose.get(clave) is not None:
                return desglose[clave]

    return defecto


def _lista(cluster: Mapping[str, Any], nombre: str) -> list[str]:
    valor = _campo(cluster, nombre, [])
    if isinstance(valor, str):
        return [valor]
    return [str(v) for v in valor if str(v).strip()]


def _numero(cluster: Mapping[str, Any], nombre: str, defecto: float = 0.0) -> float:
    try:
        return float(_campo(cluster, nombre, defecto))
    except (TypeError, ValueError):
        return defecto


def _citas(cluster: Mapping[str, Any]) -> list[Quote]:
    """Citas deduplicadas.

    El mismo mensaje puede llegar varias veces (un corpus repetido, un enlace
    cruzado, alguien que insiste). Cinco copias de una frase no son cinco
    pruebas, así que solo sobrevive la primera aparición de cada texto.
    """
    vistas: set[str] = set()
    salida: list[Quote] = []
    for cruda in _campo(cluster, "evidence", []) or []:
        if not isinstance(cruda, Mapping):
            continue
        texto = str(cruda.get("quote", "")).strip()
        if not texto:
            continue
        huella = " ".join(texto.lower().split())
        if huella in vistas:
            continue
        vistas.add(huella)
        salida.append(
            Quote(
                quote=texto,
                subreddit=str(cruda.get("subreddit", "") or ""),
                author=str(cruda.get("author", "") or ""),
                url=str(cruda.get("url", "") or ""),
            )
        )
    return salida


# --- Textos ------------------------------------------------------------------

TEXTOS: dict[str, dict[str, str]] = {
    "es": {
        "doc_title": "Especificación de proyecto",
        "h_summary": "Resumen ejecutivo",
        "h_problem": "La problemática real",
        "h_solution": "El software a construir",
        "h_mvp": "Alcance del MVP",
        "h_fail": "Por qué fallan las soluciones actuales",
        "h_money": "Modelo de negocio",
        "h_evidence": "Lo que dice la gente, con sus palabras",
        "phase1": "Fase 1 - Indispensable",
        "phase2": "Fase 2 - Después de validar",
        "value": "Propuesta de valor",
        "no_evidence": "No hay citas guardadas para este problema.",
        "footer": (
            "Documento generado a partir de la evidencia recogida por el radar. "
            "Cada cifra sale de la base de datos; donde no hay dato, se dice."
        ),
    },
    "en": {
        "doc_title": "Project specification",
        "h_summary": "Executive summary",
        "h_problem": "The actual problem",
        "h_solution": "The software to build",
        "h_mvp": "MVP scope",
        "h_fail": "Why current workarounds fail",
        "h_money": "Business model",
        "h_evidence": "What people say, in their own words",
        "phase1": "Phase 1 - Must have",
        "phase2": "Phase 2 - After validation",
        "value": "Value proposition",
        "no_evidence": "No quotes stored for this problem.",
        "footer": (
            "Generated from the evidence the radar collected. Every number comes "
            "from the database; where there is no data, it says so."
        ),
    },
}

# Sufijo del nombre segun lo que la gente venia a hacer.
SUFIJOS = {"complaint": "Rescue", "question": "Guide", "request": "Flow"}
SUFIJO_GENERICO = "Flow"


def _idioma(language: str) -> str:
    return language if language in TEXTOS else IDIOMA_POR_DEFECTO


def _enumerar(nombres: Sequence[str], idioma: str) -> str:
    """Lista legible: 'a, b y c' / 'a, b and c'."""
    if not nombres:
        return ""
    if len(nombres) == 1:
        return nombres[0]
    union = " y " if idioma == "es" else " and "
    return ", ".join(nombres[:-1]) + union + nombres[-1]


# --- Piezas del documento ----------------------------------------------------


def _segun(cantidad: int, singular: str, plural: str) -> str:
    """Concordancia.

    El documento lo lee una persona para decidir si invierte meses de trabajo.
    «1 testimonios independientes» le dice, antes que nada, que lo ha escrito
    una máquina sin cuidado, y eso resta credibilidad a las cifras que sí son
    buenas.
    """
    return singular if cantidad == 1 else plural


def _comunidades(cluster: Mapping[str, Any]) -> list[str]:
    return [f"r/{nombre}" for nombre in _lista(cluster, "subreddits")]


def _tema(cluster: Mapping[str, Any], idioma: str) -> str:
    claves = _lista(cluster, "keywords")
    if claves:
        return _enumerar(claves, idioma)
    etiqueta = str(_campo(cluster, "label", "")).strip()
    if etiqueta:
        return etiqueta
    return "el problema detectado" if idioma == "es" else "the detected problem"


def _nombre_producto(cluster: Mapping[str, Any]) -> str:
    """Nombre provisional, derivado de la palabra que repite la gente.

    Se construye en inglés en los dos idiomas porque las palabras clave salen
    de foros en inglés: traducir solo la mitad daría nombres híbridos.
    """
    claves = _lista(cluster, "keywords")
    semilla = claves[0] if claves else str(_campo(cluster, "label", "Radar"))
    partes = semilla.split()
    base = partes[0] if partes else "Radar"
    intento = str(_campo(cluster, "intent_type", "")).lower()
    return f"{base.capitalize()} {SUFIJOS.get(intento, SUFIJO_GENERICO)}"


def _una_frase(cluster: Mapping[str, Any], idioma: str, citas: int) -> str:
    tema = _tema(cluster, idioma)
    foros = len(_comunidades(cluster))

    if idioma == "es":
        quien = _segun(citas, "una persona describe", f"{citas} personas describen")
        donde = _segun(foros, "una sola comunidad", f"{foros} comunidades distintas")
        return (
            f"Una herramienta centrada en «{tema}»: el problema que {quien} con "
            f"sus propias palabras en {donde}."
        )

    quien = _segun(citas, "one person describes", f"{citas} people describe")
    donde = _segun(foros, "a single forum", f"{foros} separate forums")
    return f"A tool focused on «{tema}»: the problem {quien} in their own words across {donde}."


def _resumen(cluster: Mapping[str, Any], idioma: str, nombre: str) -> str:
    tema = _tema(cluster, idioma)
    comunidades = _comunidades(cluster)
    foros = len(comunidades)
    menciones = int(_numero(cluster, "mention_count"))
    puntuacion = _numero(cluster, "final_score")
    urgencia = str(_campo(cluster, "urgency_tier", ""))
    lista = _enumerar(comunidades, idioma)

    if idioma == "es":
        veces = _segun(menciones, "una vez", f"{menciones} veces")
        donde = _segun(foros, "una comunidad", f"{foros} comunidades")
        return (
            f"{nombre} atiende un problema concreto: «{tema}». El radar lo ha "
            f"visto {veces} en {donde} ({lista}), con una intensidad de "
            f"{puntuacion:.0f} sobre 100 y urgencia {urgencia}. Va dirigido a "
            f"quien trabaja en esos foros y hoy resuelve esto por su cuenta."
        )

    veces = _segun(menciones, "once", f"{menciones} times")
    donde = _segun(foros, "one forum", f"{foros} forums")
    return (
        f"{nombre} tackles one concrete problem: «{tema}». The radar saw it "
        f"{veces} across {donde} ({lista}), scoring {puntuacion:.0f} out of 100 "
        f"with {urgencia} urgency. It targets the people in those forums who "
        f"deal with this on their own today."
    )


def _problema(cluster: Mapping[str, Any], idioma: str, citas: int) -> str:
    """El apartado que sostiene todo lo demás, así que no infla el volumen.

    Cinco menciones del mismo texto copiado no son cinco pruebas, y la
    diferencia se dice aquí, que es donde alguien decidiría invertir. Cuando
    no hay repeticion no se menciona: «se sostiene sobre 5 testimonios, no
    sobre 5» no significa nada y hace dudar del resto de las cifras.
    """
    comunidades = _comunidades(cluster)
    foros = len(comunidades)
    menciones = int(_numero(cluster, "mention_count"))
    gravedad = _numero(cluster, "severity_factor") * 100
    novedad = _numero(cluster, "recency_factor") * 100
    lista = _enumerar(comunidades, idioma)
    hay_repeticion = citas < menciones

    if idioma == "es":
        cuantas = _segun(menciones, "una mención", f"{menciones} menciones")
        donde = _segun(foros, "una sola comunidad", f"{foros} comunidades distintas")
        cabecera = (
            f"Se ha detectado {cuantas} en {donde} ({lista}). "
            if menciones == 1
            else f"Se han detectado {cuantas} en {donde} ({lista}). "
        )

        if hay_repeticion:
            textos = _segun(
                citas, "una es un texto distinto", f"{citas} son textos distintos entre sí"
            )
            apoyo = _segun(
                citas,
                "un solo testimonio independiente",
                f"{citas} testimonios independientes",
            )
            cuerpo = (
                f"De esas menciones, {textos}: el resto repite el mismo mensaje, "
                f"así que el caso se sostiene sobre {apoyo}, no sobre {menciones}. "
            )
        else:
            cuerpo = (
                f"Cada una es un testimonio distinto, así que el caso se apoya en "
                f"{_segun(citas, 'una voz', f'{citas} voces')} independientes. "
            )

        return (
            f"{cabecera}{cuerpo}La gravedad media que mide el motor es del "
            f"{gravedad:.0f} % y lo reciente de las quejas, del {novedad:.0f} %."
        )

    cuantas = _segun(menciones, "One mention was", f"{menciones} mentions were")
    donde = _segun(foros, "a single forum", f"{foros} separate forums")
    cabecera = f"{cuantas} detected across {donde} ({lista}). "

    if hay_repeticion:
        textos = _segun(citas, "one is a distinct text", f"{citas} are distinct texts")
        apoyo = _segun(
            citas, "a single independent account", f"{citas} independent accounts"
        )
        cuerpo = (
            f"Of those, {textos}: the rest repeat the same message, so the case "
            f"rests on {apoyo}, not on {menciones}. "
        )
    else:
        cuerpo = (
            f"Each one is a separate account, so the case rests on "
            f"{_segun(citas, 'one independent voice', f'{citas} independent voices')}. "
        )

    return (
        f"{cabecera}{cuerpo}Average severity measured by the engine is "
        f"{gravedad:.0f} %, and recency is {novedad:.0f} %."
    )


def _solucion(cluster: Mapping[str, Any], idioma: str, nombre: str) -> str:
    tema = _tema(cluster, idioma)
    trabajo = str(_campo(cluster, "job_statement", "")).strip()

    if idioma == "es":
        texto = (
            f"Construir {nombre}: un producto que se ocupe de «{tema}» de punta "
            f"a punta, en vez de dejarlo repartido entre pasos sueltos que cada "
            f"cual repite a su manera."
        )
        if trabajo:
            texto += f" El motor resume el trabajo por hacer así: «{trabajo}»."
    else:
        texto = (
            f"Build {nombre}: a product that owns «{tema}» end to end, instead of "
            f"leaving it spread across loose steps that everyone repeats their "
            f"own way."
        )
        if trabajo:
            texto += f" The engine words the job to be done like this: «{trabajo}»."
    return texto


def _mvp(cluster: Mapping[str, Any], idioma: str, pago: float) -> list[Phase]:
    claves = _lista(cluster, "keywords")
    foros = len(_comunidades(cluster))
    textos = TEXTOS[idioma]
    fase1: list[str] = []

    if claves:
        principal = claves[0]
        if idioma == "es":
            fase1.append(
                f"Resolver «{principal}» de principio a fin: es la palabra que "
                f"aparece en todas las quejas del grupo."
            )
            fase1 += [
                f"Cubrir también «{clave}», que acompaña siempre a la anterior."
                for clave in claves[1:]
            ]
        else:
            fase1.append(
                f"Solve «{principal}» end to end: it is the word present in every "
                f"complaint in this group."
            )
            fase1 += [
                f"Cover «{clave}» too, since it always travels with it."
                for clave in claves[1:]
            ]

    if idioma == "es":
        perfil = _segun(
            foros, "la comunidad detectada", f"las {foros} comunidades detectadas"
        )
        fase1.append(
            f"Funcionar para el perfil de {perfil}, sin pedir configuración previa."
        )
        fase1.append(
            "Avisar cuando el proceso falle, que es justo lo que hoy no ocurre."
        )
        fase2 = [
            "Informe del tiempo ahorrado, para justificar la suscripción.",
            "Integraciones con las herramientas que ya se usan en esos foros.",
            "Ampliar a las comunidades vecinas donde el mismo dolor aparece más flojo.",
        ]
        if pago >= PAGO_EXPLICITO:
            fase1.append(
                "Cobrar desde el primer día: la disposición a pagar ya es explícita."
            )
        else:
            fase2.append(
                "Probar el cobro solo después de confirmar que alguien pagaría."
            )
    else:
        perfil = _segun(foros, "the single forum detected", f"the {foros} forums detected")
        fase1.append(
            f"Work out of the box for the profile of {perfil}, with no setup required."
        )
        fase1.append(
            "Warn when the process fails, which is exactly what is missing today."
        )
        fase2 = [
            "Time-saved report, to justify the subscription.",
            "Integrations with the tools those forums already use.",
            "Expand to neighbouring forums where the same pain shows up weaker.",
        ]
        if pago >= PAGO_EXPLICITO:
            fase1.append("Charge from day one: willingness to pay is already explicit.")
        else:
            fase2.append("Only test pricing after confirming somebody would pay.")

    return [Phase(textos["phase1"], fase1), Phase(textos["phase2"], fase2)]


def _fallos(cluster: Mapping[str, Any], idioma: str) -> str:
    """Por qué no sirve lo que ya usan.

    Cuando el motor no ha encontrado ninguna herramienta citada, lo dice. Es la
    sección donde más tienta rellenar con nombres conocidos, y justo donde un
    nombre inventado llevaría a tomar la decisión equivocada.
    """
    apanos = _lista(cluster, "current_solutions")
    menciones = int(_numero(cluster, "mention_count"))

    if not apanos:
        if idioma == "es":
            cuantas = _segun(
                menciones, "la única mención analizada", f"las {menciones} menciones analizadas"
            )
            return (
                f"Nadie ha nombrado una herramienta concreta en {cuantas}. Eso no "
                f"significa que no existan alternativas: significa que el motor no "
                f"ha encontrado ninguna citada. Conviene buscarlas a mano antes de "
                f"construir, porque este apartado es el que decide si hay hueco de "
                f"verdad."
            )
        cuantas = _segun(
            menciones, "the single mention analysed", f"the {menciones} mentions analysed"
        )
        return (
            f"Nobody named a specific tool across {cuantas}. That does not mean "
            f"alternatives do not exist: it means the engine found none quoted. "
            f"Worth checking by hand before building, because this section is the "
            f"one that decides whether there is a real gap."
        )

    lista = _enumerar(apanos, idioma)
    if idioma == "es":
        return (
            f"La gente ya se apaña con: {lista}. Y aun así sigue quejándose, de "
            f"modo que esos apaños no cierran el problema: marcan el listón que "
            f"hay que superar, no el techo."
        )
    return (
        f"People already get by with: {lista}. And they still complain, so those "
        f"workarounds do not close the problem: they set the bar to beat, not the "
        f"ceiling."
    )


def _monetizacion(cluster: Mapping[str, Any], idioma: str) -> str:
    """Modelo sugerido según la señal de pago detectada.

    Ningún caso propone una cifra: la evidencia dice si alguien pagaría, no
    cuánto. Un precio inventado aquí se leería como un dato medido.
    """
    pago = _numero(cluster, "paid_signal_factor")

    if pago >= PAGO_EXPLICITO:
        if idioma == "es":
            return (
                "Hay disposición a pagar explícita: en las citas se dice con "
                "todas las letras. Encaja una suscripción mensual por puesto, con "
                "prueba corta y sin capa gratuita indefinida. La cifra concreta "
                "sale de preguntar a quien escribió esas frases, no de aquí."
            )
        return (
            "Willingness to pay is explicit: people say it in plain words in the "
            "quotes. A monthly per-seat subscription fits, with a short trial and "
            "no open-ended free tier. The actual figure comes from asking the "
            "people who wrote those lines, not from this document."
        )

    if pago >= PAGO_IMPLICITO:
        if idioma == "es":
            return (
                "La disposición a pagar es implícita: se habla de tiempo perdido "
                "y de trabajo repetido, pero no de dinero. El paso siguiente es "
                "medir cuánto cuesta ese tiempo y llevar esa cifra a la "
                "conversación de precio."
            )
        return (
            "Willingness to pay is implicit: people talk about wasted time and "
            "repeated work, but not about money. The next step is measuring what "
            "that time costs and taking that figure into the pricing conversation."
        )

    if idioma == "es":
        return (
            "No hay ninguna señal de pago en la evidencia recogida. Poner precio "
            "ahora sería inventárselo. El paso siguiente es hablar con quien se "
            "quejó y preguntarlo, antes de escribir una sola línea de código."
        )
    return (
        "There is no payment signal at all in the evidence collected. Pricing now "
        "would be making it up. The next step is talking to the people who "
        "complained and asking them, before writing a single line of code."
    )


# --- Montaje -----------------------------------------------------------------


def _bloque_cita(cita: Quote) -> list[str]:
    """Una cita como blockquote.

    Las quejas traen saltos de línea (título y cuerpo, o varios párrafos). Sin
    prefijar cada línea, Markdown cierra la cita en el primer salto y el resto
    del testimonio se pinta como texto normal, indistinguible de lo que escribe
    el documento.
    """
    lineas = [f"> {linea}" if linea.strip() else ">" for linea in cita.quote.splitlines()]
    firma = ", ".join(
        parte
        for parte in (
            f"r/{cita.subreddit}" if cita.subreddit else "",
            cita.author if cita.author else "",
        )
        if parte
    )
    if firma:
        lineas += [">", f"> — {firma}"]
    return lineas


def _markdown(
    idioma: str,
    nombre: str,
    frase: str,
    resumen: str,
    problema: str,
    solucion: str,
    fases: list[Phase],
    fallos: str,
    monetizacion: str,
    citas: list[Quote],
) -> str:
    textos = TEXTOS[idioma]
    lineas: list[str] = [
        f"# {nombre}",
        "",
        f"**{textos['value']}:** {frase}",
        "",
        f"## {textos['h_summary']}",
        "",
        resumen,
        "",
        f"## {textos['h_problem']}",
        "",
        problema,
        "",
        f"## {textos['h_solution']}",
        "",
        solucion,
        "",
        f"## {textos['h_mvp']}",
        "",
    ]

    for fase in fases:
        lineas += [f"### {fase.name}", ""]
        lineas += [f"- {item}" for item in fase.items]
        lineas.append("")

    lineas += [
        f"## {textos['h_fail']}",
        "",
        fallos,
        "",
        f"## {textos['h_money']}",
        "",
        monetizacion,
        "",
        f"## {textos['h_evidence']}",
        "",
    ]

    if citas:
        for cita in citas:
            lineas += _bloque_cita(cita)
            lineas.append("")
    else:
        lineas += [textos["no_evidence"], ""]

    lineas += ["---", "", f"_{textos['footer']}_"]
    return "\n".join(lineas)


def build_blueprint(
    cluster: Mapping[str, Any], language: str = IDIOMA_POR_DEFECTO
) -> Blueprint:
    """Sintetiza el documento de un cluster.

    `cluster` es la fila tal como la devuelve la base de datos o el puente de
    Rust; se aceptan las dos grafías de los nombres de campo.
    """
    idioma = _idioma(language)
    citas = _citas(cluster)
    distintas = len(citas)

    nombre = _nombre_producto(cluster)
    frase = _una_frase(cluster, idioma, distintas)
    resumen = _resumen(cluster, idioma, nombre)
    problema = _problema(cluster, idioma, distintas)
    solucion = _solucion(cluster, idioma, nombre)
    fases = _mvp(cluster, idioma, _numero(cluster, "paid_signal_factor"))
    fallos = _fallos(cluster, idioma)
    monetizacion = _monetizacion(cluster, idioma)

    return Blueprint(
        product_name=nombre,
        one_liner=frase,
        executive_summary=resumen,
        problem=problema,
        solution=solucion,
        mvp=fases,
        why_existing_fail=fallos,
        monetisation=monetizacion,
        evidence=citas,
        distinct_quotes=distintas,
        markdown=_markdown(
            idioma,
            nombre,
            frase,
            resumen,
            problema,
            solucion,
            fases,
            fallos,
            monetizacion,
            citas,
        ),
    )
