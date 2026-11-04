"""
Contract Loader — Carrega e interpreta contratos de qualidade (YAML).

Cada contrato define o schema esperado, campos obrigatórios, regras de domínio
e thresholds de confiança para um determinado tipo de entidade.
"""

# Desenvolvido por Luciana Sampaio — Data Engineer 

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class FieldContract:
    """Especificação de contrato para um campo individual."""

    name: str
    dtype: str
    required: bool = False
    nullable: bool = True
    allowed_values: Optional[List[Any]] = None
    regex: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    description: str = ""
    owner: Optional[str] = None


@dataclass
class EntityContract:
    """Contrato completo de uma entidade (ex: pessoa_fisica)."""

    entity_name: str
    version: str
    fields: List[FieldContract] = field(default_factory=list)
    required_fields: List[str] = field(default_factory=list)
    unique_keys: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_field(self, name: str) -> Optional[FieldContract]:
        """Retorna a especificação de um campo pelo nome."""
        for f in self.fields:
            if f.name == name:
                return f
        return None

    @property
    def field_names(self) -> List[str]:
        return [f.name for f in self.fields]


class ContractLoader:
    """Carrega contratos YAML e produz objetos EntityContract."""

    def __init__(self, contracts_dir: str | Path) -> None:
        self.contracts_dir = Path(contracts_dir)
        if not self.contracts_dir.exists():
            raise FileNotFoundError(
                f"Diretório de contratos não encontrado: {self.contracts_dir}"
            )

    def load(self, entity_name: str) -> EntityContract:
        """Carrega o contrato YAML de uma entidade pelo nome."""
        yaml_path = self.contracts_dir / f"{entity_name}.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(
                f"Contrato não encontrado: {yaml_path}"
            )

        with open(yaml_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        return self._parse(raw)

    def list_contracts(self) -> List[str]:
        """Lista todos os contratos disponíveis no diretório."""
        return [
            p.stem
            for p in self.contracts_dir.glob("*.yaml")
        ]

    # ------------------------------------------------------------------
    # Parsing interno
    # ------------------------------------------------------------------

    def _parse(self, raw: Dict[str, Any]) -> EntityContract:
        fields = [
            FieldContract(
                name=f["name"],
                dtype=f.get("dtype", "string"),
                required=f.get("required", False),
                nullable=f.get("nullable", True),
                allowed_values=f.get("allowed_values"),
                regex=f.get("regex"),
                min_value=f.get("min_value"),
                max_value=f.get("max_value"),
                description=f.get("description", ""),
                owner=f.get("owner"),
            )
            for f in raw.get("fields", [])
        ]

        required_fields = [f.name for f in fields if f.required]

        return EntityContract(
            entity_name=raw.get("entity_name", "unknown"),
            version=raw.get("version", "0.0.0"),
            fields=fields,
            required_fields=required_fields,
            unique_keys=raw.get("unique_keys", []),
            metadata=raw.get("metadata", {}),
        )
