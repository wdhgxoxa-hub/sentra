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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# Por encima de este factor (0.0-1.0) la gente dice de forma explícita que
# pagaría; por debajo del bajo, nadie ha hablado de dinero.
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
    #: De dónde salen los datos; primera línea del documento (AUD-009).
    source_notice: str = ""
    #: "demo", "reddit" o None si la ejecución no lo registró.
    data_source: str | None = None

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
            "sourceNotice": self.source_notice,
            "dataSource": self.data_source,
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


def _stats(cluster: Mapping[str, Any]) -> Mapping[str, Any]:
    """Cifras exactas del problema (aggregation.cluster_stats), o vacío."""
    valor = _campo(cluster, "cluster_stats", {})
    return valor if isinstance(valor, Mapping) else {}


def _recuento_palabras(cluster: Mapping[str, Any]) -> list[tuple[str, int]]:
    """[(palabra, en cuántas quejas aparece)], de más a menos frecuente."""
    return [
        (str(k.get("keyword", "")), int(k.get("count", 0)))
        for k in _stats(cluster).get("keywords") or []
        if isinstance(k, Mapping) and k.get("keyword")
    ]


def _juntas(cluster: Mapping[str, Any], a: str, b: str) -> int | None:
    """En cuántas quejas aparecen `a` y `b` a la vez, si se contó."""
    for par in _stats(cluster).get("pairs") or []:
        if isinstance(par, Mapping) and {par.get("a"), par.get("b")} == {a, b}:
            return int(par.get("count", 0))
    return None


def _de(k: int, n: int, idioma: str) -> str:
    """«7 de 9 quejas» / «las 9 de 9 quejas»: la cifra, nunca «todas»."""
    if idioma == "es":
        return f"las {k} de {n} quejas" if k == n else f"{k} de {n} quejas"
    return f"{k} of {n} complaints"


def _fuente(cluster: Mapping[str, Any]) -> str | None:
    fuente = _campo(cluster, "data_source")
    return fuente if fuente in ("demo", "reddit") else None


def _aviso_fuente(cluster: Mapping[str, Any], idioma: str) -> str:
    fuente = _fuente(cluster)
    textos = TEXTOS[idioma]
    if fuente == "demo":
        return textos["source_demo"]
    if fuente == "reddit":
        return textos["source_reddit"]
    return textos["source_unknown"]


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
            "Menciones, comunidades, puntuación, recuentos por palabra y citas "
            "salen del problema guardado en la base de datos. Las etiquetas de "
            "gravedad e intención las asigna un clasificador automático y pueden "
            "quedar indeterminadas. Donde no hay dato, se dice."
        ),
        "source_demo": (
            "⚠️ DATOS DE DEMOSTRACIÓN: corpus fabricado, no procede de Reddit. "
            "No sirve para decidir."
        ),
        "source_reddit": "Fuente de los datos: Reddit.",
        "source_unknown": (
            "Fuente de los datos: no registrada; no se puede afirmar que sean reales."
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
            "Mentions, communities, score, per-keyword counts and quotes come "
            "from the problem stored in the database. Severity and intent labels "
            "are assigned by an automatic classifier and may be undetermined. "
            "Where there is no data, it says so."
        ),
        "source_demo": (
            "⚠️ DEMO DATA: fabricated corpus, not from Reddit. Not fit for decisions."
        ),
        "source_reddit": "Data source: Reddit.",
        "source_unknown": (
            "Data source: not recorded; the data cannot be claimed to be real."
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
        quien = _segun(citas, "una cita textual", f"{citas} citas textuales")
        donde = _segun(foros, "una sola comunidad", f"{foros} comunidades distintas")
        return (
            f"Una herramienta centrada en «{tema}»: el problema que recogen "
            f"{quien} de {donde}."
        )

    quien = _segun(citas, "one verbatim quote", f"{citas} verbatim quotes")
    donde = _segun(foros, "a single forum", f"{foros} separate forums")
    return f"A tool focused on «{tema}»: the problem captured by {quien} from {donde}."


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
            f"quien participa en esos foros."
        )

    veces = _segun(menciones, "once", f"{menciones} times")
    donde = _segun(foros, "one forum", f"{foros} forums")
    return (
        f"{nombre} tackles one concrete problem: «{tema}». The radar saw it "
        f"{veces} across {donde} ({lista}), scoring {puntuacion:.0f} out of 100 "
        f"with {urgencia} urgency. It targets the people in those forums."
    )


def _problema(cluster: Mapping[str, Any], idioma: str, citas: int) -> str:
    """El apartado que sostiene todo lo demás, así que no infla el volumen.

    Las repeticiones se cuentan sobre TODAS las quejas (`distinct_texts`), no
    sobre las citas guardadas, que se limitan a unas pocas: confundir el
    límite con repetición afirmaba algo falso. Una gravedad indeterminada se
    dice como tal; presentarla como 0 % la haría pasar por medida.
    """
    stats = _stats(cluster)
    comunidades = _comunidades(cluster)
    foros = len(comunidades)
    menciones = int(_numero(cluster, "mention_count"))
    gravedad = _numero(cluster, "severity_factor") * 100
    novedad = _numero(cluster, "recency_factor") * 100
    lista = _enumerar(comunidades, idioma)
    distintos = stats.get("distinct_texts")
    indeterminadas = stats.get("severity_undetermined")
    # Sin cifras guardadas, contar textos sobre las citas solo es exacto si
    # las citas cubren todas las menciones; si hay más menciones que citas,
    # de las demás no se sabe nada y no se afirma.
    guardadas_n = sum(
        1 for e in _campo(cluster, "evidence", []) or []
        if isinstance(e, Mapping) and str(e.get("quote", "")).strip()
    )
    if distintos is None and guardadas_n and guardadas_n == menciones:
        distintos = citas

    if idioma == "es":
        cuantas = _segun(menciones, "una mención", f"{menciones} menciones")
        donde = _segun(foros, "una sola comunidad", f"{foros} comunidades distintas")
        verbo = "Se ha detectado" if menciones == 1 else "Se han detectado"
        partes = [f"{verbo} {cuantas} en {donde} ({lista})."]

        if distintos is None:
            guardadas = _segun(
                citas, "Se guardó una cita textual", f"Se guardaron {citas} citas textuales"
            )
            partes.append(
                f"{guardadas}; no hay recuento de textos distintos para este problema."
            )
        elif int(distintos) == menciones:
            partes.append(f"Son {menciones} textos distintos.")
        else:
            repetidas = menciones - int(distintos)
            partes.append(
                f"Hay {distintos} textos distintos: las otras {repetidas} menciones "
                f"repiten un texto ya contado, así que el caso se apoya en "
                f"{distintos} testimonios, no en {menciones}."
            )

        if indeterminadas is not None and int(indeterminadas) > 0:
            partes.append(
                f"El motor dejó la gravedad indeterminada en "
                f"{_de(int(indeterminadas), menciones, idioma)}, que no suman a la "
                f"puntuación; el factor de gravedad resultante es del {gravedad:.0f} %."
            )
        else:
            partes.append(
                f"El factor de gravedad que calcula el motor es del {gravedad:.0f} %."
            )
        partes.append(f"El factor de novedad de las quejas es del {novedad:.0f} %.")
        return " ".join(partes)

    cuantas = _segun(menciones, "One mention was", f"{menciones} mentions were")
    donde = _segun(foros, "a single forum", f"{foros} separate forums")
    partes = [f"{cuantas} detected across {donde} ({lista})."]

    if distintos is None:
        guardadas = _segun(citas, "One verbatim quote was", f"{citas} verbatim quotes were")
        partes.append(
            f"{guardadas} stored; there is no count of distinct texts for this problem."
        )
    elif int(distintos) == menciones:
        partes.append(f"They are {menciones} distinct texts.")
    else:
        repetidas = menciones - int(distintos)
        partes.append(
            f"There are {distintos} distinct texts: the other {repetidas} mentions "
            f"repeat a text already counted, so the case rests on {distintos} "
            f"accounts, not on {menciones}."
        )

    if indeterminadas is not None and int(indeterminadas) > 0:
        partes.append(
            f"The engine left severity undetermined in "
            f"{_de(int(indeterminadas), menciones, idioma)}, which add nothing to "
            f"the score; the resulting severity factor is {gravedad:.0f} %."
        )
    else:
        partes.append(f"The severity factor computed by the engine is {gravedad:.0f} %.")
    partes.append(f"The recency factor of the complaints is {novedad:.0f} %.")
    return " ".join(partes)


def _solucion(cluster: Mapping[str, Any], idioma: str, nombre: str) -> str:
    tema = _tema(cluster, idioma)
    trabajo = str(_campo(cluster, "job_statement", "")).strip()

    if idioma == "es":
        texto = f"Construir {nombre}: un producto que se ocupe de «{tema}» de punta a punta."
        if trabajo:
            texto += f" El motor resume el trabajo por hacer así: «{trabajo}»."
    else:
        texto = f"Build {nombre}: a product that owns «{tema}» end to end."
        if trabajo:
            texto += f" The engine words the job to be done like this: «{trabajo}»."
    return texto


def _mvp(cluster: Mapping[str, Any], idioma: str, pago: float) -> list[Phase]:
    """Alcance del MVP.

    Cada afirmación sobre una palabra lleva su cifra exacta («aparece en 7 de
    9 quejas»): `keywords` es la unión de términos del problema, no algo que
    compartan todas sus quejas.
    """
    recuento = _recuento_palabras(cluster)
    menciones = int(_numero(cluster, "mention_count"))
    foros = len(_comunidades(cluster))
    textos = TEXTOS[idioma]
    fase1: list[str] = []

    if recuento:
        principal, veces = recuento[0]
        if idioma == "es":
            fase1.append(
                f"Resolver «{principal}» de principio a fin: «{principal}» aparece en "
                f"{_de(veces, menciones, idioma)}."
            )
        else:
            fase1.append(
                f"Solve «{principal}» end to end: «{principal}» appears in "
                f"{_de(veces, menciones, idioma)}."
            )
        for clave, cuenta in recuento[1:3]:
            juntas = _juntas(cluster, principal, clave)
            if idioma == "es":
                frase = (
                    f"Cubrir también «{clave}»: «{clave}» aparece en "
                    f"{_de(cuenta, menciones, idioma)}"
                )
                if juntas is not None:
                    frase += f" y coincide con «{principal}» en {juntas} de ellas"
            else:
                frase = (
                    f"Also cover «{clave}»: «{clave}» appears in "
                    f"{_de(cuenta, menciones, idioma)}"
                )
                if juntas is not None:
                    frase += f" and co-occurs with «{principal}» in {juntas} of them"
            fase1.append(frase + ".")
    else:
        claves = _lista(cluster, "keywords")
        if claves:
            if idioma == "es":
                fase1.append(
                    f"Resolver «{claves[0]}» de principio a fin (no hay recuento por "
                    f"palabra para este problema, así que no se afirma con qué "
                    f"frecuencia aparece)."
                )
                fase1 += [f"Cubrir también «{clave}»." for clave in claves[1:3]]
            else:
                fase1.append(
                    f"Solve «{claves[0]}» end to end (no per-keyword count is stored "
                    f"for this problem, so its frequency is not claimed)."
                )
                fase1 += [f"Also cover «{clave}»." for clave in claves[1:3]]

    if idioma == "es":
        perfil = _segun(
            foros, "la comunidad detectada", f"las {foros} comunidades detectadas"
        )
        fase1.append(
            f"Funcionar para el perfil de {perfil}, sin pedir configuración previa."
        )
        fase1.append("Avisar cuando el proceso falle.")
        fase2 = [
            "Informe del tiempo ahorrado, para justificar la suscripción.",
            "Integraciones con las herramientas que se citen en esos foros.",
            "Ampliar a comunidades vecinas donde aparezca el mismo problema.",
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
        fase1.append("Warn when the process fails.")
        fase2 = [
            "Time-saved report, to justify the subscription.",
            "Integrations with the tools quoted in those forums.",
            "Expand to neighbouring forums where the same problem shows up.",
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
                "Hay disposición a pagar explícita: en las citas se dice de forma "
                "expresa. Encaja una suscripción mensual por puesto, con "
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
        "There is no payment signal in the evidence collected. Pricing now "
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
    # Sin autor (R9): se guarda como hash, que no se muestra a nadie.
    if cita.subreddit:
        lineas += [">", f"> — r/{cita.subreddit}"]
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
    aviso_fuente: str,
) -> str:
    textos = TEXTOS[idioma]
    lineas: list[str] = [
        f"> {aviso_fuente}",
        "",
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
    aviso = _aviso_fuente(cluster, idioma)

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
            aviso,
        ),
        source_notice=aviso,
        data_source=_fuente(cluster),
    )
