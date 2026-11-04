"""
Ownership Module — Resolução de responsabilidade (ownership) para regras e campos.

Mapeia violações de qualidade de dados para os proprietários responsáveis,
permitindo roteamento de alertas e responsabilização nas correções.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from ..contracts.contract_loader import EntityContract


class OwnershipResolver:
    """
    Resolve o time ou indivíduo proprietário de uma violação ou remediação.

    Prioridade de resolução:
    1. Propriedade explícita configurada no campo do contrato (ex: field.owner).
    2. Propriedade mapeada por tipo de regra.
    3. Proprietário geral da entidade (metadata.owner).
    4. Fallback padrão ('governança_dados').
    """

    def __init__(
        self,
        contract: EntityContract,
        default_owner: str = "governança_dados",
        rule_owner_overrides: Optional[Dict[str, str]] = None,
    ) -> None:
        self.contract = contract
        self.default_owner = default_owner
        self.rule_owner_overrides = rule_owner_overrides or {}

        # Cache de owners dos campos
        self.field_owners: Dict[str, str] = {}
        self._init_field_owners()

    def _init_field_owners(self) -> None:
        """Carrega os owners definidos nos campos do contrato."""
        contract_default_owner = self.contract.metadata.get("owner")
        entity_fallback = contract_default_owner or self.default_owner

        for field in self.contract.fields:
            # Pega o owner diretamente do objeto do campo (se configurado)
            # ou via dicionário de metadados do campo se presente
            owner = getattr(field, "owner", None)
            if not owner:
                # Caso venha dos metadados internos (caso tenhamos custom_attributes no futuro)
                owner = entity_fallback
            self.field_owners[field.name] = owner

    def resolve_field_owner(self, field_name: str) -> str:
        """Resolve o owner de um campo específico."""
        fallback = self.contract.metadata.get("owner") or self.default_owner
        return self.field_owners.get(field_name, fallback)

    def resolve_rule_owner(self, rule_name: str, fields_involved: Optional[List[str]] = None) -> str:
        """
        Resolve o owner de uma regra específica.
        Se a regra estiver associada a campos, tenta mapear para o owner dos campos.
        """
        if rule_name in self.rule_owner_overrides:
            return self.rule_owner_overrides[rule_name]

        if fields_involved:
            # Se múltiplos campos estão envolvidos, tenta pegar o owner do primeiro campo
            # que possui owner diferente do fallback padrão, ou apenas o primeiro campo.
            for field in fields_involved:
                owner = self.resolve_field_owner(field)
                if owner != self.default_owner:
                    return owner
            return self.resolve_field_owner(fields_involved[0])

        return self.contract.metadata.get("owner") or self.default_owner

    def get_ownership_summary(self) -> Dict[str, Any]:
        """Retorna mapeamento de propriedade atual do contrato."""
        return {
            "entity_name": self.contract.entity_name,
            "entity_owner": self.contract.metadata.get("owner") or self.default_owner,
            "field_owners": self.field_owners,
        }
