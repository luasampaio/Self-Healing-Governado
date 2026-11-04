"""
Policy Registry — Registro central de políticas/contratos de dados.

Garante o rastreamento das versões das políticas de dados ativas e calcula a
assinatura criptográfica (hash SHA256) do arquivo YAML do contrato para fins de não-repúdio.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from ..contracts.contract_loader import ContractLoader, EntityContract


@dataclass
class PolicyMetadata:
    """Metadados de governança para uma política registrada."""

    entity_name: str
    version: str
    owner: str
    sha256: str
    file_path: str
    active_rules_count: int
    fields_count: int
    raw_metadata: Dict[str, Any]


class PolicyRegistry:
    """
    Registro e gerenciador de políticas (contratos).
    Mantém o histórico de versões ativas e as assinaturas de integridade.
    """

    def __init__(self, contracts_dir: str | Path) -> None:
        self.contracts_dir = Path(contracts_dir)
        self.loader = ContractLoader(self.contracts_dir)
        self._registry: Dict[str, EntityContract] = {}
        self._metadata: Dict[str, PolicyMetadata] = {}
        self._load_all_policies()

    def _load_all_policies(self) -> None:
        """Carrega e registra todos os arquivos de contrato do diretório."""
        if not self.contracts_dir.exists():
            return

        for path in self.contracts_dir.glob("*.yaml"):
            try:
                entity_name = path.stem
                contract = self.loader.load(entity_name)
                sha256 = self._calculate_sha256(path)
                
                # Conta regras ativas baseando-se nas configurações do contrato
                rules_count = 0
                for field in contract.fields:
                    if field.required:
                        rules_count += 1
                    if field.allowed_values:
                        rules_count += 1
                    if field.regex:
                        rules_count += 1
                    if field.min_value is not None or field.max_value is not None:
                        rules_count += 1

                self._registry[entity_name] = contract
                
                owner = contract.metadata.get("owner", "desconhecido")
                self._metadata[entity_name] = PolicyMetadata(
                    entity_name=entity_name,
                    version=contract.version,
                    owner=owner,
                    sha256=sha256,
                    file_path=str(path.resolve()),
                    active_rules_count=rules_count,
                    fields_count=len(contract.fields),
                    raw_metadata=contract.metadata,
                )
            except Exception as e:
                # Log do erro de carregamento (em ambiente real usaria logging)
                print(f"Erro ao registrar política {path.name}: {e}")

    def _calculate_sha256(self, file_path: Path) -> str:
        """Calcula hash SHA256 do arquivo para auditoria."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as fh:
            buf = fh.read()
            hasher.update(buf)
        return hasher.hexdigest()

    def get_contract(self, entity_name: str) -> Optional[EntityContract]:
        """Recupera o contrato de qualidade de uma entidade."""
        return self._registry.get(entity_name)

    def get_metadata(self, entity_name: str) -> Optional[PolicyMetadata]:
        """Recupera os metadados de governança da política."""
        return self._metadata.get(entity_name)

    def list_policies(self) -> List[Dict[str, Any]]:
        """Lista todas as políticas ativas registradas."""
        policies = []
        for name, meta in self._metadata.items():
            policies.append({
                "entity_name": meta.entity_name,
                "version": meta.version,
                "owner": meta.owner,
                "sha256": meta.sha256,
                "fields_count": meta.fields_count,
                "rules_count": meta.active_rules_count,
            })
        return policies
