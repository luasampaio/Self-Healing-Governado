"""
Required Fields Validator — Verifica campos obrigatórios.

Garante que todos os campos marcados como required=True no contrato
estejam presentes e não-nulos no registro.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..contracts.contract_loader import EntityContract


class RequiredFieldsResult:
    """Resultado da validação de campos obrigatórios."""

    def __init__(self) -> None:
        self.missing_fields: List[str] = []
        self.null_fields: List[str] = []

    @property
    def is_valid(self) -> bool:
        return len(self.missing_fields) == 0 and len(self.null_fields) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "missing_fields": self.missing_fields,
            "null_fields": self.null_fields,
        }


class RequiredFieldsValidator:
    """Valida presença e não-nulidade de campos obrigatórios."""

    def __init__(self, contract: EntityContract) -> None:
        self.contract = contract

    def validate(self, record: Dict[str, Any]) -> RequiredFieldsResult:
        """Valida um registro contra os campos obrigatórios do contrato."""
        result = RequiredFieldsResult()

        for field_name in self.contract.required_fields:
            if field_name not in record:
                result.missing_fields.append(field_name)
            elif record[field_name] is None:
                result.null_fields.append(field_name)

        return result
