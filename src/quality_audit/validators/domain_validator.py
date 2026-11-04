"""
Domain Validator — Validações de regras de domínio.

Aplica regras de domínio específicas: valores permitidos, faixas numéricas,
e validações de negócio como CPF, CNPJ, UF, etc.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..contracts.contract_loader import EntityContract, FieldContract

# UFs válidas do Brasil
_UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
    "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


class DomainViolation:
    """Uma violação de regra de domínio."""

    def __init__(self, field: str, rule: str, value: Any, message: str) -> None:
        self.field = field
        self.rule = rule
        self.value = value
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "rule": self.rule,
            "value": self.value,
            "message": self.message,
        }


class DomainValidationResult:
    """Resultado consolidado de validação de domínio."""

    def __init__(self) -> None:
        self.violations: List[DomainViolation] = []

    @property
    def is_valid(self) -> bool:
        return len(self.violations) == 0

    def add(self, field: str, rule: str, value: Any, message: str) -> None:
        self.violations.append(DomainViolation(field, rule, value, message))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "violations": [v.to_dict() for v in self.violations],
        }


class DomainValidator:
    """Aplica validações de domínio com base no contrato e regras de negócio."""

    def __init__(self, contract: EntityContract) -> None:
        self.contract = contract

    def validate(self, record: Dict[str, Any]) -> DomainValidationResult:
        """Valida regras de domínio para um registro."""
        result = DomainValidationResult()

        for fc in self.contract.fields:
            value = record.get(fc.name)
            if value is None:
                continue

            # Allowed values
            if fc.allowed_values and value not in fc.allowed_values:
                result.add(
                    field=fc.name,
                    rule="allowed_values",
                    value=value,
                    message=(
                        f"Valor '{value}' não está na lista permitida "
                        f"para '{fc.name}': {fc.allowed_values}"
                    ),
                )

            # Range numérico
            if fc.min_value is not None and isinstance(value, (int, float)):
                if value < fc.min_value:
                    result.add(
                        field=fc.name,
                        rule="min_value",
                        value=value,
                        message=(
                            f"Valor {value} abaixo do mínimo permitido "
                            f"({fc.min_value}) para '{fc.name}'."
                        ),
                    )

            if fc.max_value is not None and isinstance(value, (int, float)):
                if value > fc.max_value:
                    result.add(
                        field=fc.name,
                        rule="max_value",
                        value=value,
                        message=(
                            f"Valor {value} acima do máximo permitido "
                            f"({fc.max_value}) para '{fc.name}'."
                        ),
                    )

        # Validações de domínio específicas (UF, CPF, etc.)
        self._validate_uf(record, result)
        self._validate_cpf(record, result)

        return result

    # ------------------------------------------------------------------
    # Validações específicas de domínio brasileiro
    # ------------------------------------------------------------------

    def _validate_uf(self, record: Dict[str, Any], result: DomainValidationResult) -> None:
        """Valida UF se o campo existir no registro."""
        uf_field = self.contract.get_field("uf")
        if uf_field is None:
            return

        uf = record.get("uf")
        if uf and isinstance(uf, str) and uf.upper() not in _UFS_VALIDAS:
            result.add(
                field="uf",
                rule="uf_valida",
                value=uf,
                message=f"UF '{uf}' não é uma UF válida do Brasil.",
            )

    def _validate_cpf(self, record: Dict[str, Any], result: DomainValidationResult) -> None:
        """Valida dígito verificador de CPF se o campo existir."""
        cpf_field = self.contract.get_field("cpf")
        if cpf_field is None:
            return

        cpf = record.get("cpf")
        if cpf and isinstance(cpf, str):
            digits = cpf.replace(".", "").replace("-", "")
            if len(digits) != 11 or not digits.isdigit():
                result.add(
                    field="cpf",
                    rule="cpf_formato",
                    value=cpf,
                    message=f"CPF '{cpf}' não tem formato válido (11 dígitos).",
                )
            elif digits == digits[0] * 11:
                result.add(
                    field="cpf",
                    rule="cpf_digitos_iguais",
                    value=cpf,
                    message=f"CPF '{cpf}' possui todos os dígitos iguais.",
                )
            elif not self._cpf_check_digits(digits):
                result.add(
                    field="cpf",
                    rule="cpf_digito_verificador",
                    value=cpf,
                    message=f"CPF '{cpf}' possui dígito verificador inválido.",
                )

    @staticmethod
    def _cpf_check_digits(digits: str) -> bool:
        """Verifica dígitos verificadores do CPF."""
        def _calc(digits_slice: str, weights: List[int]) -> int:
            total = sum(int(d) * w for d, w in zip(digits_slice, weights))
            remainder = total % 11
            return 0 if remainder < 2 else 11 - remainder

        d1 = _calc(digits[:9], list(range(10, 1, -1)))
        d2 = _calc(digits[:10], list(range(11, 1, -1)))
        return int(digits[9]) == d1 and int(digits[10]) == d2
