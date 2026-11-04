"""
Audit Logger — Camada de auditoria e rastreabilidade.

Registra todas as decisões, correções e classificações com timestamp,
garantindo evidência completa para compliance e governança.
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..policy.policy_engine import Decision, PolicyResult

logger = logging.getLogger(__name__)


class AuditEntry:
    """Uma entrada individual no log de auditoria."""

    def __init__(
        self,
        record_id: str,
        decision: Decision,
        corrections: List[Dict[str, Any]],
        review_reasons: List[str],
        quarantine_reasons: List[str],
        original_record: Optional[Dict[str, Any]] = None,
        corrected_record: Optional[Dict[str, Any]] = None,
        policy_version: Optional[str] = None,
        policy_hash: Optional[str] = None,
        policy_owner: Optional[str] = None,
        lineage: Optional[List[Dict[str, Any]]] = None,
        field_ownerships: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.record_id = record_id
        self.decision = decision
        self.corrections = corrections
        self.review_reasons = review_reasons
        self.quarantine_reasons = quarantine_reasons
        self.original_record = original_record
        self.corrected_record = corrected_record
        self.policy_version = policy_version
        self.policy_hash = policy_hash
        self.policy_owner = policy_owner
        self.lineage = lineage or []
        self.field_ownerships = field_ownerships or {}
        
        # Enriquecimento com contexto de sistema/execução
        self.metadata = metadata or {}
        self.metadata.update({
            "runner_user": getpass.getuser(),
            "runner_host": socket.gethostname(),
            "env_environment": os.environ.get("ENVIRONMENT", "development"),
        })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "record_id": self.record_id,
            "decision": self.decision.value,
            "corrections": self.corrections,
            "review_reasons": self.review_reasons,
            "quarantine_reasons": self.quarantine_reasons,
            "original_record": self.original_record,
            "corrected_record": self.corrected_record,
            "policy_version": self.policy_version,
            "policy_hash": self.policy_hash,
            "policy_owner": self.policy_owner,
            "lineage": self.lineage,
            "field_ownerships": self.field_ownerships,
            "metadata": self.metadata,
        }


class AuditLogger:
    """
    Logger de auditoria operacional.

    Suporta múltiplos backends:
    - In-memory (para testes e notebooks)
    - JSON Lines file (para persistência local)
    - Extensível para Delta Tables no Databricks
    """

    def __init__(self, output_path: Optional[str | Path] = None) -> None:
        self._entries: List[AuditEntry] = []
        self._output_path = Path(output_path) if output_path else None

    def log(self, policy_result: PolicyResult) -> AuditEntry:
        """Registra uma decisão de política no audit log."""
        entry = AuditEntry(
            record_id=policy_result.record_id or "unknown",
            decision=policy_result.decision,
            corrections=policy_result.corrections_applied,
            review_reasons=policy_result.review_reasons,
            quarantine_reasons=policy_result.quarantine_reasons,
            original_record=policy_result.original_record,
            corrected_record=policy_result.corrected_record,
            policy_version=getattr(policy_result, "policy_version", None),
            policy_hash=getattr(policy_result, "policy_hash", None),
            policy_owner=getattr(policy_result, "policy_owner", None),
            lineage=getattr(policy_result, "lineage", None),
            field_ownerships=getattr(policy_result, "field_ownerships", None),
        )

        self._entries.append(entry)
        logger.info(
            "Audit | %s | %s | %s",
            entry.record_id,
            entry.decision.value,
            entry.timestamp,
        )

        # Persistência em JSON Lines
        if self._output_path:
            self._append_to_file(entry)

        return entry

    def get_entries(self) -> List[AuditEntry]:
        """Retorna todas as entradas do log."""
        return list(self._entries)

    def get_summary(self) -> Dict[str, int]:
        """Retorna resumo quantitativo das decisões."""
        summary: Dict[str, int] = {
            d.value: 0 for d in Decision
        }
        for entry in self._entries:
            summary[entry.decision.value] += 1
        return summary

    def to_records(self) -> List[Dict[str, Any]]:
        """Exporta o log como lista de dicts (compatível com DataFrame)."""
        return [e.to_dict() for e in self._entries]

    def clear(self) -> None:
        """Limpa o log in-memory."""
        self._entries.clear()

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    def _append_to_file(self, entry: AuditEntry) -> None:
        """Appenda uma entrada em arquivo JSON Lines."""
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._output_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict(), ensure_ascii=False, default=str))
            fh.write("\n")
