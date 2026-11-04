"""
Orchestrator — Orquestrador principal do Self-Healing Governado.

Coordena o fluxo completo:
Dados de Entrada → Validação → Regras → Heurísticas → Policy → Audit

Produz registros classificados em: approved, auto_correct, review_pending, quarantined.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .contracts.contract_loader import ContractLoader, EntityContract
from .validators.schema_validator import SchemaValidator
from .validators.required_fields_validator import RequiredFieldsValidator
from .validators.domain_validator import DomainValidator
from .rules.deterministic_rules import DeterministicRules
from .heuristics.heuristic_engine import HeuristicEngine
from .policy.policy_engine import Decision, PolicyEngine, PolicyResult
from .audit.audit_logger import AuditLogger
from .governance.ownership import OwnershipResolver
from .governance.policy_registry import PolicyRegistry

logger = logging.getLogger(__name__)


class SelfHealingOrchestrator:
    """
    Orquestrador principal do pipeline de remediação.

    Executa todas as etapas na ordem definida pela arquitetura,
    consolida resultados e registra auditoria.
    """

    def __init__(
        self,
        contract: EntityContract,
        policy_engine: Optional[PolicyEngine] = None,
        heuristic_engine: Optional[HeuristicEngine] = None,
        audit_logger: Optional[AuditLogger] = None,
        record_id_field: str = "id",
        policy_hash: Optional[str] = None,
        policy_version: Optional[str] = None,
        policy_owner: Optional[str] = None,
    ) -> None:
        self.contract = contract
        self.record_id_field = record_id_field
        self.policy_hash = policy_hash or "unknown"
        self.policy_version = policy_version or contract.version
        self.policy_owner = policy_owner or contract.metadata.get("owner", "unknown")

        # Componentes
        self.schema_validator = SchemaValidator(contract)
        self.required_validator = RequiredFieldsValidator(contract)
        self.domain_validator = DomainValidator(contract)
        self.deterministic_rules = DeterministicRules(contract)
        self.heuristic_engine = heuristic_engine or HeuristicEngine()
        self.policy_engine = policy_engine or PolicyEngine()
        self.audit_logger = audit_logger or AuditLogger()
        self.ownership_resolver = OwnershipResolver(contract)

    def process_record(self, record: Dict[str, Any]) -> PolicyResult:
        """
        Processa um único registro pelo pipeline completo.

        Fluxo:
        1. Validação de Schema
        2. Validação de Campos Obrigatórios
        3. Validação de Domínio
        4. Regras Determinísticas (correção)
        5. Heurísticas Seguras
        6. Policy Engine (decisão)
        7. Audit Log
        """
        record_id = str(record.get(self.record_id_field, "unknown"))

        # Setup de Linhagem
        lineage_trace = []
        lineage_trace.append({
            "step": "0_raw",
            "record": dict(record),
            "description": "Dados brutos de entrada",
        })

        # 1. Validação de Schema
        schema_result = self.schema_validator.validate(record)

        # 2. Validação de Campos Obrigatórios
        required_result = self.required_validator.validate(record)

        # 3. Validação de Domínio
        domain_result = self.domain_validator.validate(record)

        # 4. Regras Determinísticas
        corrected_record, det_corrections = self.deterministic_rules.apply(record)

        # Captura estado intermediário pós-regras determinísticas
        state_after_det = dict(corrected_record)
        if det_corrections:
            lineage_trace.append({
                "step": "1_deterministic_corrections",
                "record": state_after_det,
                "description": f"Aplicadas {len(det_corrections)} correções determinísticas",
                "changes": [c.to_dict() for c in det_corrections],
            })

        # 5. Heurísticas — aplicar nos campos que tiveram violação de domínio
        fields_with_issues = [v.field for v in domain_result.violations]
        # Também incluir campos nulos obrigatórios
        fields_with_issues += required_result.null_fields

        heuristic_high, heuristic_low = self.heuristic_engine.evaluate(
            corrected_record, fields_with_issues
        )

        # Aplica sugestões de alta confiança ao registro corrigido
        for suggestion in heuristic_high:
            corrected_record[suggestion.field] = suggestion.suggested_value

        if heuristic_high:
            lineage_trace.append({
                "step": "2_heuristic_corrections",
                "record": dict(corrected_record),
                "description": f"Aplicadas {len(heuristic_high)} correções heurísticas de alta confiança",
                "changes": [s.to_dict() for s in heuristic_high],
            })

        # Validação final de qualidade sobre o registro corrigido
        corrected_schema_result = self.schema_validator.validate(corrected_record)
        corrected_required_result = self.required_validator.validate(corrected_record)
        corrected_domain_result = self.domain_validator.validate(corrected_record)

        # 6. Policy Engine — decisão
        policy_result = self.policy_engine.evaluate(
            record_id=record_id,
            original_record=record,
            schema_errors=corrected_schema_result.errors,
            required_errors=corrected_required_result.to_dict(),
            domain_violations=[v.to_dict() for v in corrected_domain_result.violations],
            deterministic_corrections=[c.to_dict() for c in det_corrections],
            heuristic_high=[s.to_dict() for s in heuristic_high],
            heuristic_low=[s.to_dict() for s in heuristic_low],
            corrected_record=corrected_record,
        )

        # Adiciona estado final na linhagem
        lineage_trace.append({
            "step": "3_final",
            "record": dict(corrected_record) if policy_result.decision != Decision.QUARANTINED else dict(record),
            "description": f"Registro classificado como {policy_result.decision.value.upper()}",
        })

        # Anexa informações de governança e linhagem no resultado
        policy_result.policy_hash = self.policy_hash
        policy_result.policy_version = self.policy_version
        policy_result.policy_owner = self.policy_owner
        policy_result.lineage = lineage_trace

        # Mapeia os owners de cada campo envolvido no contrato
        field_ownerships = {}
        for f in self.contract.field_names:
            field_ownerships[f] = self.ownership_resolver.resolve_field_owner(f)
        policy_result.field_ownerships = field_ownerships

        # 7. Audit Log
        self.audit_logger.log(policy_result)

        return policy_result

    def process_batch(
        self, records: List[Dict[str, Any]]
    ) -> Dict[str, List[PolicyResult]]:
        """
        Processa um lote de registros e agrupa por decisão.

        Retorna dict com chaves: approved, auto_correct, review_pending, quarantined.
        """
        results: Dict[str, List[PolicyResult]] = {
            d.value: [] for d in Decision
        }

        for i, record in enumerate(records):
            try:
                result = self.process_record(record)
                results[result.decision.value].append(result)
            except Exception as e:
                logger.error("Erro ao processar registro %d: %s", i, e)
                # Quarentena por erro inesperado
                error_result = PolicyResult(
                    decision=Decision.QUARANTINED,
                    record_id=str(record.get(self.record_id_field, i)),
                    original_record=record,
                    quarantine_reasons=[f"Erro inesperado: {str(e)}"],
                )
                self.audit_logger.log(error_result)
                results[Decision.QUARANTINED.value].append(error_result)

        return results

    def get_audit_summary(self) -> Dict[str, int]:
        """Retorna resumo quantitativo do audit log."""
        return self.audit_logger.get_summary()

    # ------------------------------------------------------------------
    # Factory method
    # ------------------------------------------------------------------

    @classmethod
    def from_config(
        cls,
        contracts_dir: str | Path,
        entity_name: str,
        audit_output: Optional[str | Path] = None,
        record_id_field: str = "id",
        **policy_kwargs,
    ) -> "SelfHealingOrchestrator":
        """
        Cria um orquestrador a partir de configuração.

        Args:
            contracts_dir: diretório contendo os arquivos YAML de contrato.
            entity_name: nome da entidade (ex: 'pessoa_fisica').
            audit_output: caminho para arquivo de audit log (opcional).
            record_id_field: campo identificador do registro.
            **policy_kwargs: parâmetros para o PolicyEngine.
        """
        registry = PolicyRegistry(contracts_dir)
        contract = registry.get_contract(entity_name)
        
        if not contract:
            loader = ContractLoader(contracts_dir)
            contract = loader.load(entity_name)
            meta = None
        else:
            meta = registry.get_metadata(entity_name)

        heuristic_engine = HeuristicEngine()
        heuristic_engine.register(HeuristicEngine.uf_from_known_cities())

        policy_hash = meta.sha256 if meta else "unknown"
        policy_version = meta.version if meta else contract.version
        policy_owner = meta.owner if meta else contract.metadata.get("owner", "unknown")

        return cls(
            contract=contract,
            policy_engine=PolicyEngine(**policy_kwargs),
            heuristic_engine=heuristic_engine,
            audit_logger=AuditLogger(output_path=audit_output),
            policy_hash=policy_hash,
            policy_version=policy_version,
            policy_owner=policy_owner,
            record_id_field=record_id_field,
        )
