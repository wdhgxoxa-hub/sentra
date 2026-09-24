"""
Composición del dossier y del plan (E5)
=======================================

El código monta el `DocumentModel` a partir del veredicto (`verdict_detail`)
y de lo que redactó el modelo (`DossierLLM`, `PlanLLM`):

- secciones fijas y en su orden (spec, Fase E);
- cada afirmación de mercado pasa por `verify_claims`: la que cita evidencia
  que no es de este veredicto se retira y el documento dice cuántas; una
  sección que se queda sin nada dice «Sin afirmaciones verificables»;
- la evidencia citada va con su fecha y su atribución, nunca con autor;
- la viabilidad va etiquetada como estimación del modelo;
- procedencia, franja del plan forzado y marca de agua de demostración los
  pone el código, no el modelo.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from .claims import Claim, DossierLLM, PlanLLM, verify_claims
from .model import Block, DocumentModel, Section

#: Extracto de cada pieza citada en «Evidencia citada».
EXCERPT_CHARS = 280


class PlanNotRecommended(ValueError):
    """Se pidió el plan de un nicho que el juez no manda construir, sin forzarlo."""

    code = "plan_not_recommended"


ROTULOS: dict[str, dict[str, Any]] = {
    "es": {
        "dossier": "Dossier", "plan": "Plan de construcción",
        "dossier_sections": ["Resumen del veredicto", "El problema", "Quién lo sufre",
                             "Cómo lo resuelven hoy", "Por qué ahora", "Compuertas y dimensiones",
                             "Abogado del diablo", "Viabilidad — estimación del modelo", "Riesgos",
                             "Evidencia citada", "Procedencia"],
        "plan_sections": ["Qué se construye y para quién", "Alcance del MVP", "Stack",
                          "Arquitectura", "Modelo de datos", "Pasos", "Validación tras el lanzamiento",
                          "Plan de publicación", "Procedencia"],
        "verdict": "Veredicto", "score": "Puntuación", "rule": "Regla", "missing": "Compuertas que faltan",
        "none": "ninguna", "niche": "Nicho", "run": "Ejecución", "generated": "Generado",
        "model": "Modelo de documentos", "source": "Fuente de los datos", "verdict_id": "Veredicto (id)",
        "versions": "Versiones", "evidence_count": "Evidencia del veredicto",
        "real": "reales (API oficial)", "demo": "de demostración", "unknown": "desconocida",
        "notice_real": "Datos reales: {n} piezas de evidencia de {k} fuentes con API oficial. "
                       "Redactado por {model}; cada afirmación cita su evidencia.",
        "notice_demo": "Datos de demostración: no son quejas reales. Redactado por {model}.",
        "notice_unknown": "Procedencia de los datos desconocida. Redactado por {model}.",
        "retired": "{n} afirmaciones retiradas por citar evidencia que no es de este veredicto.",
        "retired_one": "1 afirmación retirada por citar evidencia que no es de este veredicto.",
        "empty": "Sin afirmaciones verificables.",
        "stripe": "El juez no recomienda construir este nicho: {verdict} — {rule}",
        "viability_note": "Estimación del modelo: no es un dato medido y no cambia el veredicto.",
        "viability_names": {"complejidad_tecnica": "Complejidad técnica",
                            "tiempo_hasta_mvp": "Tiempo hasta un MVP",
                            "dependencias_externas": "Dependencias externas",
                            "coste_de_usuarios": "Coste de conseguir usuarios",
                            "riesgo_legal": "Riesgo legal"},
        "gate_ok": "pasa", "gate_ko": "falla", "gate_sin_datos": "sin datos (no medida)", "value_vs": "{value} (umbral {threshold})",
        "advocate_before": "Veredicto antes y después", "advocate_reason": "Motivo de la bajada",
        "advocate_none": "El abogado del diablo no aportó argumentos.",
        "in": "Dentro", "out": "Fuera", "step": "Paso", "files": "Archivos",
        "tests": "Pruebas de aceptación", "done": "Hecho cuando", "fields": "Campos", "purpose": "Para qué",
    },
    "en": {
        "dossier": "Dossier", "plan": "Build plan",
        "dossier_sections": ["Verdict summary", "The problem", "Who suffers it", "How it is solved today",
                             "Why now", "Gates and dimensions", "Devil's advocate",
                             "Feasibility — model estimate", "Risks", "Cited evidence", "Provenance"],
        "plan_sections": ["What is built and for whom", "MVP scope", "Stack", "Architecture",
                          "Data model", "Steps", "Post-launch validation", "Publication plan",
                          "Provenance"],
        "verdict": "Verdict", "score": "Score", "rule": "Rule", "missing": "Failing gates",
        "none": "none", "niche": "Niche", "run": "Run", "generated": "Generated",
        "model": "Documents model", "source": "Data source", "verdict_id": "Verdict (id)",
        "versions": "Versions", "evidence_count": "Verdict evidence",
        "real": "real (official API)", "demo": "demo", "unknown": "unknown",
        "notice_real": "Real data: {n} evidence items from {k} sources with official APIs. "
                       "Written by {model}; every claim cites its evidence.",
        "notice_demo": "Demo data: these are not real complaints. Written by {model}.",
        "notice_unknown": "Unknown data provenance. Written by {model}.",
        "retired": "{n} claims removed for citing evidence that is not from this verdict.",
        "retired_one": "1 claim removed for citing evidence that is not from this verdict.",
        "empty": "No verifiable claims.",
        "stripe": "The judge does not recommend building this niche: {verdict} — {rule}",
        "viability_note": "Model estimate: not a measured figure and it does not change the verdict.",
        "viability_names": {"complejidad_tecnica": "Technical complexity",
                            "tiempo_hasta_mvp": "Time to an MVP",
                            "dependencias_externas": "External dependencies",
                            "coste_de_usuarios": "Cost of acquiring users",
                            "riesgo_legal": "Legal risk"},
        "gate_ok": "passes", "gate_ko": "fails", "gate_sin_datos": "no data (not measured)", "value_vs": "{value} (threshold {threshold})",
        "advocate_before": "Verdict before and after", "advocate_reason": "Reason for the downgrade",
        "advocate_none": "The devil's advocate raised no arguments.",
        "in": "In", "out": "Out", "step": "Step", "files": "Files",
        "tests": "Acceptance tests", "done": "Done when", "fields": "Fields", "purpose": "Purpose",
    },
}


def _r(language: str) -> dict[str, Any]:
    return ROTULOS.get(language, ROTULOS["es"])


def _procedencia(evidencia: Sequence[Mapping[str, Any]]) -> str | None:
    fuentes = {e.get("data_source") for e in evidencia}
    if "demo" in fuentes:
        return "demo"
    return "real" if fuentes == {"real"} else None


class _Citas:
    """Verifica las afirmaciones contra la evidencia del veredicto y lleva la
    cuenta de lo retirado y de lo citado."""

    def __init__(self, validos: Iterable[str], rotulos: Mapping[str, Any]) -> None:
        self.validos = set(validos)
        self.rotulos = rotulos
        self.retiradas = 0
        self.citados: list[str] = []

    def bloques(self, claims: Sequence[Claim]) -> tuple[Block, ...]:
        quedan, retiradas = verify_claims(claims, self.validos)
        self.retiradas += len(retiradas)
        for claim in quedan:
            self.citados += [i for i in claim.evidence_ids if i not in self.citados]
        if not quedan:
            return (Block("note", self.rotulos["empty"]),)
        return (Block("bullets", items=tuple(
            f"{c.text} [{', '.join(c.evidence_ids)}]" for c in quedan)),)

    def aviso(self) -> tuple[Block, ...]:
        if not self.retiradas:
            return ()
        texto = (self.rotulos["retired_one"] if self.retiradas == 1
                 else self.rotulos["retired"].format(n=self.retiradas))
        return (Block("note", texto),)


def _secciones(ids: Sequence[str], titulos: Sequence[str],
               bloques: Mapping[str, tuple[Block, ...]]) -> tuple[Section, ...]:
    return tuple(Section(i, f"{n}. {titulo}", bloques[i])
                 for n, (i, titulo) in enumerate(zip(ids, titulos, strict=True), start=1))


def _portada_y_aviso(detalle: Mapping[str, Any], r: Mapping[str, Any], model: str,
                     generated_at: datetime) -> tuple[tuple[tuple[str, str], ...], str, str | None]:
    evidencia = detalle.get("evidence") or []
    origen = _procedencia(evidencia)
    fuentes = {e.get("source") for e in evidencia}
    aviso = {"real": r["notice_real"], "demo": r["notice_demo"]}.get(origen or "", r["notice_unknown"])
    portada = (
        (r["niche"], ", ".join(detalle.get("keywords") or [])),
        (r["verdict"], f"{detalle.get('verdict')} · {detalle.get('score')}"),
        (r["run"], str(detalle.get("run_id") or "")),
        (r["generated"], generated_at.isoformat(timespec="minutes")),
        (r["model"], model),
        (r["source"], r[origen or "unknown"]),
    )
    return portada, aviso.format(n=len(evidencia), k=len(fuentes), model=model), origen


def _procedencia_bloques(detalle: Mapping[str, Any], r: Mapping[str, Any], model: str,
                         generated_at: datetime, origen: str | None) -> tuple[Block, ...]:
    return (Block("table", rows=(
        (r["verdict_id"], str(detalle.get("id") or "")),
        (r["run"], str(detalle.get("run_id") or "")),
        (r["versions"], " · ".join(str(v) for v in (
            detalle.get("labeler_version") or "?", detalle.get("clustering_version") or "?",
            detalle.get("weights_version") or "?"))),
        (r["model"], model),
        (r["generated"], generated_at.isoformat(timespec="minutes")),
        (r["source"], r[origen or "unknown"]),
        (r["evidence_count"], str(len(detalle.get("evidence") or []))),
    )),)


def _estado_compuerta(g: Mapping[str, Any], r: Mapping[str, Any]) -> str:
    """Pasa, falla o sin datos: una compuerta que no midió nada no «pasa» (AUD2-005)."""
    if g.get("measured") is False:
        return str(r["gate_sin_datos"])
    return str(r["gate_ok"] if g.get("passed") else r["gate_ko"])


def _titulo(tipo: str, detalle: Mapping[str, Any], r: Mapping[str, Any]) -> str:
    return f"{r[tipo]} · {', '.join((detalle.get('keywords') or [])[:3]) or detalle.get('id')}"


def compose_dossier(detalle: Mapping[str, Any], generado: DossierLLM, language: str, *, model: str,
                    generated_at: datetime) -> DocumentModel:
    """El dossier de cualquier veredicto, con sus once secciones fijas."""
    r = _r(language)
    evidencia = detalle.get("evidence") or []
    citas = _Citas((e["id"] for e in evidencia), r)
    portada, aviso, origen = _portada_y_aviso(detalle, r, model, generated_at)

    problema = citas.bloques(generado.problem)
    quien = citas.bloques(generado.who)
    soluciones = citas.bloques(generado.current_solutions)
    ahora = citas.bloques(generado.why_now)
    riesgos = citas.bloques(generado.risks)

    resumen = (Block("table", rows=(
        (r["verdict"], str(detalle.get("verdict"))),
        (r["score"], str(detalle.get("score"))),
        (r["rule"], str(detalle.get("rule"))),
        (r["missing"], ", ".join(detalle.get("missing") or []) or r["none"]),
    )),) + citas.aviso()
    compuertas = (
        Block("table", rows=tuple(
            (str(g["gate"]), f"{_estado_compuerta(g, r)} · "
             + r["value_vs"].format(value=g.get("value"), threshold=g.get("threshold")))
            for g in detalle.get("gates") or [])),
        Block("table", rows=tuple(
            (str(d["name"]), str(d.get("note") or d.get("value"))) for d in detalle.get("dimensions") or [])),
    )
    abogado = detalle.get("advocate") or {}
    argumentos = abogado.get("arguments") or []
    bloques_abogado: tuple[Block, ...] = (
        Block("table", rows=((r["advocate_before"],
                              f"{abogado.get('verdict_before')} → {abogado.get('verdict_after')}"),)
              + (((r["advocate_reason"], str(abogado["reason"])),) if abogado.get("reason") else ())),
        Block("bullets", items=tuple(
            f"{a.get('severity')}: {a.get('claim')} [{', '.join(a.get('evidence_ids') or [])}]"
            for a in argumentos)) if argumentos else Block("note", r["advocate_none"]),
    )
    viabilidad = (
        Block("note", r["viability_note"]),
        Block("table", rows=tuple(
            (r["viability_names"][c.criterion], f"{c.score}/5 · {c.reason}") for c in generado.viability)),
    )
    por_id = {e["id"]: e for e in evidencia}
    citada = tuple(
        Block("quote", " ".join(str(por_id[i].get("text") or "").split())[:EXCERPT_CHARS],
              signature=_firma(por_id[i]))
        for i in citas.citados if i in por_id
    ) or (Block("note", r["empty"]),)

    bloques = {
        "resumen": resumen, "problema": problema, "quien": quien, "soluciones": soluciones,
        "por_que_ahora": ahora, "compuertas": compuertas, "abogado": bloques_abogado,
        "viabilidad": viabilidad, "riesgos": riesgos, "evidencia": citada,
        "procedencia": _procedencia_bloques(detalle, r, model, generated_at, origen),
    }
    ids = ["resumen", "problema", "quien", "soluciones", "por_que_ahora", "compuertas", "abogado",
           "viabilidad", "riesgos", "evidencia", "procedencia"]
    return DocumentModel(language=language, kind="dossier", title=_titulo("dossier", detalle, r),
                         data_source=origen, cover=portada, source_notice=aviso,
                         sections=_secciones(ids, r["dossier_sections"], bloques))


def _firma(pieza: Mapping[str, Any]) -> str:
    """id · fecha · insignia · sitio · URL (R5); nunca el autor (R9)."""
    fecha = pieza.get("created_at")
    cuando = fecha.date().isoformat() if isinstance(fecha, datetime) else str(fecha or "")
    atribucion = pieza.get("attribution") or {}
    return (f"{pieza['id']} · {cuando} · {atribucion.get('badge')} · {atribucion.get('site')} · "
            f"{atribucion.get('url')}")


def compose_plan(detalle: Mapping[str, Any], generado: PlanLLM, language: str, *, model: str,
                 generated_at: datetime, forced: bool = False) -> DocumentModel:
    """El plan de construcción: solo para CONSTRUIR, salvo que se fuerce; forzado,
    cada página lleva la franja «no recomendado» con la regla del juez."""
    r = _r(language)
    if detalle.get("verdict") != "CONSTRUIR" and not forced:
        raise PlanNotRecommended(
            f"El juez dice {detalle.get('verdict')} ({detalle.get('rule')}): el plan solo se "
            "genera para CONSTRUIR, salvo que se fuerce.")
    franja = (None if detalle.get("verdict") == "CONSTRUIR" else
              r["stripe"].format(verdict=detalle.get("verdict"), rule=detalle.get("rule")))
    evidencia = detalle.get("evidence") or []
    citas = _Citas((e["id"] for e in evidencia), r)
    portada, aviso, origen = _portada_y_aviso(detalle, r, model, generated_at)

    que = citas.bloques(generado.what_and_for_whom)
    mvp = ((Block("subheading", r["in"]),) + citas.bloques(generado.mvp_in)
           + (Block("subheading", r["out"]),) + citas.bloques(generado.mvp_out))
    validacion = citas.bloques(generado.validation)
    publicacion = citas.bloques(generado.publication)
    stack = (Block("table", rows=tuple((s.component, f"{s.choice} · {s.reason}") for s in generado.stack)),)
    arquitectura = (Block("bullets", items=tuple(generado.architecture)),)
    datos = tuple(
        b for e in generado.data_model for b in (
            Block("subheading", e.name),
            Block("table", rows=((r["fields"], ", ".join(e.fields)), (r["purpose"], e.purpose))),
        )
    )
    pasos = tuple(
        b for p in generado.steps for b in (
            Block("subheading", f"{r['step']} {p.number}: {p.objective}"),
            Block("table", rows=((r["files"], ", ".join(p.files)),
                                 (r["tests"], "; ".join(p.acceptance_tests)),
                                 (r["done"], p.done_criterion))),
            Block("code", "\n".join(p.commands)),
        )
    )
    bloques = {
        "que": que + citas.aviso(), "mvp": mvp, "stack": stack, "arquitectura": arquitectura,
        "datos": datos, "pasos": pasos, "validacion": validacion, "publicacion": publicacion,
        "procedencia": _procedencia_bloques(detalle, r, model, generated_at, origen),
    }
    ids = ["que", "mvp", "stack", "arquitectura", "datos", "pasos", "validacion", "publicacion",
           "procedencia"]
    return DocumentModel(language=language, kind="plan", title=_titulo("plan", detalle, r),
                         data_source=origen, cover=portada, source_notice=aviso, stripe=franja,
                         sections=_secciones(ids, r["plan_sections"], bloques))
