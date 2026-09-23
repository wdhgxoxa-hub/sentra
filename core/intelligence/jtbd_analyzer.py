"""
Analizador de Trabajos por Resolver (Jobs-To-Be-Done) y Riesgos
==============================================================
Extraído y adaptado de pain-miner (painminer/analysis.py).

Proporciona:
1. Mapeo formal de intenciones de usuario a requerimientos funcionales JTBD:
   - "complaint" -> "Completar la tarea con menor fricción"
   - "help_request" -> "Desbloquear una tarea detenida"
   - "alternative_search" -> "Reemplazar una solución existente insatisfactoria"
   - "recommendation_request" -> "Elegir una solución idónea para el caso de uso"
   - "workaround_share" -> "Superar la ausencia de una funcionalidad nativa"
   - "switching_story" -> "Migrar fuera de la herramienta actual"
   - "purchase_intent" -> "Evaluar si una solución de pago justifica el retorno de inversión"
2. Detección heurística de parches/workarounds ("escribí un script", "hack manual con hojas de cálculo").
3. Detección de señales comerciales y disposición a pagar (Willingness-To-Pay: explícito vs implícito).
4. Detección de riesgos: enlaces de afiliados/promocionales y astroturfing de competidores.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

# Mapeo canónico de intención a tarea objetivo (Jobs To Be Done) de pain-miner
TASK_BY_INTENT: dict[str, str] = {
    "alternative_search": "Reemplazar una solución insatisfactoria existente",
    "recommendation_request": "Seleccionar una herramienta adecuada para el flujo de trabajo",
    "purchase_intent": "Evaluar la contratación de una solución comercial de pago",
    "switching_story": "Migrar fuera del proveedor actual por problemas de costo o servicio",
    "workaround_share": "Completar la tarea a pesar de la ausencia de un flujo nativo",
    "help_request": "Desbloquear un paso crítico del proceso operativo",
    "complaint": "Ejecutar la tarea con menor fricción y desperdicio de tiempo",
    "general": "Optimizar el flujo de trabajo general"
}

# Heurísticas de detección de intenciones
INTENT_PATTERNS: dict[str, re.Pattern] = {
    "alternative_search": re.compile(
        r"\b(?:alternative to|looking for an alternative|replace|instead of|better than|substitute for)\b",
        re.IGNORECASE
    ),
    "recommendation_request": re.compile(
        r"\b(?:any recommendations|what tool do you recommend|what are you using for|best software for|suggest a tool)\b",
        re.IGNORECASE
    ),
    "purchase_intent": re.compile(
        r"\b(?:willing to pay|i'd pay|budget of|pricing plans|worth the price|cost per month|paying customer|buy a license)\b",
        re.IGNORECASE
    ),
    "switching_story": re.compile(
        r"\b(?:switching from|switched to|migrated from|canceling my|leaving|cancelled my subscription|ditching)\b",
        re.IGNORECASE
    ),
    "workaround_share": re.compile(
        r"\b(?:my workaround|wrote a script|built an internal tool|python script to|custom integration|hack together|manually export|zapier hook)\b",
        re.IGNORECASE
    ),
    "help_request": re.compile(
        r"\b(?:how do i|how can i|stuck on|can't figure out|is there any way to|need help with)\b",
        re.IGNORECASE
    ),
    "complaint": re.compile(
        r"\b(?:hate that|terrible ux|breaks every time|broken|unreliable|frustrating|worst feature|buggy|support was useless)\b",
        re.IGNORECASE
    )
}

# Detección de herramientas comerciales citadas
KNOWN_TOOLS_REGEX = re.compile(
    r"\b(salesforce|hubspot|stripe|notion|airtable|jira|slack|clickup|zapier|make|asana|trello|linear|zendesk|intercom|shopify|quickbooks)\b",
    re.IGNORECASE
)

# Riesgos operativos y spam de afiliados (pain-miner)
AFFILIATE_REGEX = re.compile(
    r"\b(?:affiliate|referral|ref=|utm_[a-z_]+|promo\s*code|discount)\b",
    re.IGNORECASE
)
EVENT_REGEX = re.compile(
    r"\b(?:breaking|announced|launch(?:ed|ing)?|news|press\s*release)\b",
    re.IGNORECASE
)


class JTBDRequirement(BaseModel):
    """Requerimiento de producto formulado según el estándar Jobs-To-Be-Done."""
    id: str
    intent_type: str
    job_statement: str
    target_task: str
    friction_barrier: str
    current_solution: str | None = None
    workaround_detected: bool = False
    workaround_description: str | None = None
    willingness_to_pay: str = "none"  # "explicit" | "implicit" | "none"
    urgency_level: str = "medium"     # "critical" | "high" | "medium" | "low"
    risk_flags: list[str] = Field(default_factory=list)
    source_url: str | None = None


class JTBDAnalyzer:
    """
    Motor determinista de extracción de Jobs-To-Be-Done y evaluación de riesgos comerciales.
    """

    def classify_intent(self, text: str) -> tuple[str, float]:
        """
        Identifica la intención predominante del texto basándose en coincidencia léxica ponderada.
        Retorna (intención, confianza 0.0-1.0).
        """
        scores: dict[str, int] = {}
        for intent, pattern in INTENT_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                scores[intent] = len(matches)

        if not scores:
            return "general", 0.3

        best_intent = max(scores, key=lambda intent: scores[intent])
        confidence = min(0.4 + (scores[best_intent] * 0.2), 1.0)
        return best_intent, round(confidence, 2)

    def extract_current_solution(self, text: str) -> str | None:
        """Extrae herramientas o software mencionado como solución actual."""
        matches = KNOWN_TOOLS_REGEX.findall(text)
        if matches:
            # Retorna el primer nombre capitalizado
            return matches[0].capitalize()
        return None

    def detect_workaround(self, text: str) -> tuple[bool, str | None]:
        """Detecta si el usuario está empleando scripts, hacks o parches manuales."""
        match = INTENT_PATTERNS["workaround_share"].search(text)
        if match:
            # Extrae la ventana contextual del parche
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 60)
            snippet = text[start:end].replace("\n", " ").strip()
            return True, snippet
        return False, None

    def evaluate_willingness_to_pay(self, text: str) -> str:
        """Determina la fuerza de disposición a pagar (WTP)."""
        lower = text.lower()
        if any(k in lower for k in ["willing to pay", "i'd pay", "i would pay", "budget of", "paying customer"]):
            return "explicit"
        if any(k in lower for k in ["costing us hours", "hiring someone", "expensive", "waste of money", "lose revenue"]):
            return "implicit"
        return "none"

    def scan_risks(self, text: str) -> list[str]:
        """Escanea riesgos de astroturfing, enlaces de afiliados y picos de noticias."""
        risks = []
        if AFFILIATE_REGEX.search(text):
            risks.append("affiliate_or_referral_pattern")
        if EVENT_REGEX.search(text):
            risks.append("event_driven_news_spike")
        return risks

    def analyze_post(
        self,
        post_id: str,
        title: str,
        body: str,
        url: str | None = None
    ) -> JTBDRequirement:
        """
        Analiza un post o comentario y genera su declaración formal de JTBD.
        """
        full_text = f"{title}\n{body}".strip()
        intent, _ = self.classify_intent(full_text)
        task = TASK_BY_INTENT.get(intent, "Optimizar el flujo de trabajo")

        curr_sol = self.extract_current_solution(full_text)
        has_workaround, workaround_desc = self.detect_workaround(full_text)
        wtp = self.evaluate_willingness_to_pay(full_text)
        risks = self.scan_risks(full_text)

        # Determinar urgencia
        if wtp == "explicit" or "frustrating" in full_text.lower() or "broken" in full_text.lower() or has_workaround:
            urgency = "high"
        else:
            urgency = "medium"

        # Formular Job Statement estándar JTBD
        barrier = title if len(title) < 100 else f"{title[:95]}..."
        solution_context = f" frente a {curr_sol}" if curr_sol else ""
        job_statement = f"Cuando los profesionales enfrentan '{barrier}', necesitan {task.lower()}{solution_context} para evitar fricción operativa."

        return JTBDRequirement(
            id=f"jtbd_{post_id}",
            intent_type=intent,
            job_statement=job_statement,
            target_task=task,
            friction_barrier=barrier,
            current_solution=curr_sol,
            workaround_detected=has_workaround,
            workaround_description=workaround_desc,
            willingness_to_pay=wtp,
            urgency_level=urgency,
            risk_flags=risks,
            source_url=url
        )
