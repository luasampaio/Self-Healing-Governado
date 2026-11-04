"""
Schema Validator — Valida tipos de dados contra o contrato.

Verifica se cada campo do registro está no tipo esperado pelo contrato
(string, int, float, date, bool, etc.).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List

from ..contracts.contract_loader import EntityContract, FieldContract


# Mapeamento de dtype do contrato → funções de checagem
_TYPE_CHECKERS = {
    "string": lambda v: isinstance(v, str),
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "bool": lambda v: isinstance(v, bool),
    "date": lambda v: isinstance(v, (date, datetime)),
}


class SchemaValidationResult:
    """Resultado da validação de schema de um registro."""

    def __init__(self) -> None:
        self.errors: List[Dict[str, Any]] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, field: str, expected: str, actual: Any, message: str) -> None:
        self.errors.append({
            "field": field,
            "expected_type": expected,
            "actual_value": actual,
            "actual_type": type(actual).__name__,
            "message": message,
        })

    def to_dict(self) -> Dict[str, Any]:
        return {"is_valid": self.is_valid, "errors": self.errors}


class SchemaValidator:
    """Valida o schema de registros individuais contra um EntityContract."""

    def __init__(self, contract: EntityContract) -> None:
        self.contract = contract

    def validate(self, record: Dict[str, Any]) -> SchemaValidationResult:
        """Valida um registro (dict) contra o schema do contrato."""
        result = SchemaValidationResult()

        # Campos desconhecidos (não previstos no contrato)
        known = set(self.contract.field_names)
        for key in record:
            if key not in known:
                result.add_error(
                    field=key,
                    expected="campo_previsto_no_contrato",
                    actual=record[key],
                    message=f"Campo '{key}' não está definido no contrato.",
                )

        # Validação de tipo para cada campo definido no contrato
        for fc in self.contract.fields:
            value = record.get(fc.name)

            # Campo ausente é tratado pelo RequiredFieldsValidator
            if value is None:
                continue

            # Checagem de tipo
            checker = _TYPE_CHECKERS.get(fc.dtype)
            if checker and not checker(value):
                result.add_error(
                    field=fc.name,
                    expected=fc.dtype,
                    actual=value,
                    message=(
                        f"Tipo inválido para '{fc.name}': "
                        f"esperado {fc.dtype}, recebido {type(value).__name__}."
                    ),
                )

            # Checagem de regex (apenas para strings)
            if fc.regex and isinstance(value, str):
                if not re.fullmatch(fc.regex, value):
                    result.add_error(
                        field=fc.name,
                        expected=f"regex({fc.regex})",
                        actual=value,
                        message=(
                            f"Valor '{value}' não corresponde ao padrão "
                            f"'{fc.regex}' para o campo '{fc.name}'."
                        ),
                    )

        return result
