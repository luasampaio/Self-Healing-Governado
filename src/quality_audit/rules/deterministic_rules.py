"""
Deterministic Rules — Regras de correção determinísticas.

Regras de remediação que têm resultado garantido e seguro:
normalização de caixa, remoção de espaços, formatação de CPF, etc.
Nunca alteram semântica — apenas padronizam.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..contracts.contract_loader import EntityContract


class CorrectionResult:
    """Resultado de uma tentativa de correção determinística."""

    def __init__(
        self,
        field: str,
        original_value: Any,
        corrected_value: Any,
        rule_name: str,
        applied: bool,
    ) -> None:
        self.field = field
        self.original_value = original_value
        self.corrected_value = corrected_value
        self.rule_name = rule_name
        self.applied = applied

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "original_value": self.original_value,
            "corrected_value": self.corrected_value,
            "rule_name": self.rule_name,
            "applied": self.applied,
        }


class DeterministicRules:
    """
    Motor de regras determinísticas de correção.

    Cada regra recebe (campo, valor) e retorna (valor_corrigido, bool_aplicado).
    Regras são registradas por nome de campo ou por tipo de dado.
    """

    def __init__(self, contract: EntityContract) -> None:
        self.contract = contract
        self._field_rules: Dict[str, List[Callable]] = {}
        self._global_rules: List[Callable] = []

        # Registra regras padrão
        self._register_defaults()

    def apply(self, record: Dict[str, Any]) -> Tuple[Dict[str, Any], List[CorrectionResult]]:
        """
        Aplica regras determinísticas ao registro.

        Retorna:
            - Registro corrigido (novo dict).
            - Lista de correções aplicadas.
        """
        corrected = dict(record)
        corrections: List[CorrectionResult] = []

        for fc in self.contract.fields:
            value = corrected.get(fc.name)
            if value is None:
                continue

            # Regras específicas do campo
            for rule_fn in self._field_rules.get(fc.name, []):
                new_value, applied, rule_name = rule_fn(value)
                if applied:
                    corrections.append(
                        CorrectionResult(
                            field=fc.name,
                            original_value=value,
                            corrected_value=new_value,
                            rule_name=rule_name,
                            applied=True,
                        )
                    )
                    corrected[fc.name] = new_value
                    value = new_value  # encadeia regras

            # Regras globais (por tipo)
            for rule_fn in self._global_rules:
                new_value, applied, rule_name = rule_fn(fc, value)
                if applied:
                    corrections.append(
                        CorrectionResult(
                            field=fc.name,
                            original_value=value,
                            corrected_value=new_value,
                            rule_name=rule_name,
                            applied=True,
                        )
                    )
                    corrected[fc.name] = new_value
                    value = new_value

        return corrected, corrections

    def register_field_rule(self, field_name: str, rule_fn: Callable) -> None:
        """Registra uma regra para um campo específico."""
        self._field_rules.setdefault(field_name, []).append(rule_fn)

    def register_global_rule(self, rule_fn: Callable) -> None:
        """Registra uma regra global aplicada a todos os campos."""
        self._global_rules.append(rule_fn)

    # ------------------------------------------------------------------
    # Regras padrão
    # ------------------------------------------------------------------

    def _register_defaults(self) -> None:
        """Registra regras determinísticas padrão."""

        # Trim de espaços para todos os campos string
        def trim_strings(fc, value):
            if fc.dtype == "string" and isinstance(value, str):
                trimmed = value.strip()
                if trimmed != value:
                    return trimmed, True, "trim_whitespace"
            return value, False, ""

        self.register_global_rule(trim_strings)

        # Normalização de caixa para UF → UPPER
        def normalize_uf(value):
            if isinstance(value, str) and value != value.upper():
                return value.upper(), True, "uf_uppercase"
            return value, False, ""

        if self.contract.get_field("uf"):
            self.register_field_rule("uf", normalize_uf)

        # Normalização de CPF — remove pontuação
        def normalize_cpf(value):
            if isinstance(value, str) and ("." in value or "-" in value):
                cleaned = value.replace(".", "").replace("-", "")
                if len(cleaned) == 11 and cleaned.isdigit():
                    return cleaned, True, "cpf_remove_punctuation"
            return value, False, ""

        if self.contract.get_field("cpf"):
            self.register_field_rule("cpf", normalize_cpf)

        # Normalização de e-mail → lowercase
        def normalize_email(value):
            if isinstance(value, str) and value != value.lower():
                return value.lower(), True, "email_lowercase"
            return value, False, ""

        if self.contract.get_field("email"):
            self.register_field_rule("email", normalize_email)
