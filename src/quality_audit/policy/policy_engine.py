"""
Policy Engine — Motor de decisão de política.

Classifica cada registro em uma das decisões operacionais:
  - APPROVED: registro válido, pronto para a camada Silver.
  - AUTO_CORRECT: correção determinística ou heurística segura aplicada.
  - REVIEW_PENDING: caso ambíguo enviado para revisão humana.
  - QUARANTINED: inconsistência crítica, registro bloqueado.

A política garante que nenhuma correção arriscada seja aplicada
sem controle e rastreabilidade.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Decision(str, Enum):
    """Decisão operacional do Policy Engine."""

    APPROVED = "approved"
    AUTO_CORRECT = "auto_correct"
    REVIEW_PENDING = "review_pending"
    QUARANTINED = "quarantined"


@dataclass
class PolicyResult:
    """Resultado da avaliação de política para um registro."""

    decision: Decision
    record_id: Optional[str] = None
    original_record: Optional[Dict[str, Any]] = None
    corrected_record: Optional[Dict[str, Any]] = None
    corrections_applied: List[Dict[str, Any]] = field(default_factory=list)
    review_reasons: List[str] = field(default_factory=list)
    quarantine_reasons: List[str] = field(default_factory=list)
    confidence_score: Optional[float] = None
    policy_version: Optional[str] = None
    policy_hash: Optional[str] = None
    policy_owner: Optional[str] = None
    lineage: List[Dict[str, Any]] = field(default_factory=list)
    field_ownerships: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "record_id": self.record_id,
            "corrections_applied": self.corrections_applied,
            "review_reasons": self.review_reasons,
            "quarantine_reasons": self.quarantine_reasons,
            "confidence_score": self.confidence_score,
            "policy_version": self.policy_version,
            "policy_hash": self.policy_hash,
            "policy_owner": self.policy_owner,
            "lineage": self.lineage,
            "field_ownerships": self.field_ownerships,
        }


class PolicyEngine:
    """
    Motor de decisão de política.

    Avalia os resultados das etapas anteriores (validação, regras, heurísticas)
    e decide a ação operacional para cada registro.
    """

    def __init__(
        self,
        max_corrections_per_record: int = 3,
        quarantine_on_missing_required: bool = True,
        quarantine_on_schema_violation: bool = True,
        min_heuristic_confidence: float = 0.85,
    ) -> None:
        self.max_corrections_per_record = max_corrections_per_record
        self.quarantine_on_missing_required = quarantine_on_missing_required
        self.quarantine_on_schema_violation = quarantine_on_schema_violation
        self.min_heuristic_confidence = min_heuristic_confidence

    def evaluate(
        self,
        record_id: str,
        original_record: Dict[str, Any],
        schema_errors: List[Dict[str, Any]],
        required_errors: Dict[str, Any],
        domain_violations: List[Dict[str, Any]],
        deterministic_corrections: List[Dict[str, Any]],
        heuristic_high: List[Dict[str, Any]],
        heuristic_low: List[Dict[str, Any]],
        corrected_record: Optional[Dict[str, Any]] = None,
    ) -> PolicyResult:
        """
        Avalia política e decide a ação para o registro.

        Ordem de prioridade:
        1. Quarentena — erros críticos intratáveis.
        2. Review Pending — ambiguidades ou heurísticas de baixa confiança.
        3. Auto Correct — correções determinísticas + heurísticas seguras.
        4. Approved — registro sem problemas.
        """
        quarantine_reasons: List[str] = []
        review_reasons: List[str] = []

        # ----- Quarentena -----
        if self.quarantine_on_schema_violation and schema_errors:
            quarantine_reasons.append(
                f"{len(schema_errors)} violação(ões) de schema detectada(s)."
            )

        missing = required_errors.get("missing_fields", [])
        null = required_errors.get("null_fields", [])
        if self.quarantine_on_missing_required and missing:
            quarantine_reasons.append(
                f"Campos obrigatórios ausentes: {missing}"
            )

        # Muitas correções = risco alto
        total_corrections = len(deterministic_corrections) + len(heuristic_high)
        if total_corrections > self.max_corrections_per_record:
            quarantine_reasons.append(
                f"Total de correções ({total_corrections}) excede o limite "
                f"({self.max_corrections_per_record})."
            )

        if quarantine_reasons:
            return PolicyResult(
                decision=Decision.QUARANTINED,
                record_id=record_id,
                original_record=original_record,
                quarantine_reasons=quarantine_reasons,
            )

        # ----- Review Pending -----
        if heuristic_low:
            review_reasons.append(
                f"{len(heuristic_low)} sugestão(ões) heurística(s) com confiança "
                f"abaixo de {self.min_heuristic_confidence}."
            )

        if null:
            review_reasons.append(
                f"Campos obrigatórios com valor nulo: {null}"
            )

        if domain_violations:
            review_reasons.append(
                f"{len(domain_violations)} violação(ões) de domínio detectada(s)."
            )

        if review_reasons:
            return PolicyResult(
                decision=Decision.REVIEW_PENDING,
                record_id=record_id,
                original_record=original_record,
                corrected_record=corrected_record,
                corrections_applied=[c for c in deterministic_corrections],
                review_reasons=review_reasons,
            )

        # ----- Auto Correct -----
        if deterministic_corrections or heuristic_high:
            return PolicyResult(
                decision=Decision.AUTO_CORRECT,
                record_id=record_id,
                original_record=original_record,
                corrected_record=corrected_record,
                corrections_applied=(
                    [c for c in deterministic_corrections]
                    + [h for h in heuristic_high]
                ),
            )

        # ----- Approved -----
        return PolicyResult(
            decision=Decision.APPROVED,
            record_id=record_id,
            original_record=original_record,
        )
