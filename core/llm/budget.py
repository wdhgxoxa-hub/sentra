"""Presupuesto de tokens del motor de IA por escaneo (F1.5, D-M4)."""

from __future__ import annotations

from .base import LLMBudgetExhausted, UsageRecord

#: Tokens por escaneo (entrada + salida + razonamiento), decisión D-M4.
DEFAULT_MAX_TOKENS = 1_000_000


class LLMBudget:
    """Cuenta los tokens gastados y corta cuando se agotan.

    Se comprueba ANTES de cada llamada: la que ya salió se cobra aunque se
    pase del tope (no se puede deshacer), pero la siguiente no sale.
    """

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS) -> None:
        self.max_tokens = max_tokens
        self.spent_tokens = 0

    def check(self) -> None:
        if self.spent_tokens >= self.max_tokens:
            raise LLMBudgetExhausted(
                f"Presupuesto del motor de IA agotado: {self.spent_tokens} de "
                f"{self.max_tokens} tokens."
            )

    def charge(self, record: UsageRecord) -> None:
        self.spent_tokens += record.total_tokens
