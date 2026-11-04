"""Fixtures compartilhadas dos testes do Self-Healing Governado."""

from __future__ import annotations

from pathlib import Path

import pytest

from quality_audit.contracts.contract_loader import ContractLoader, EntityContract

CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "src" / "quality_audit" / "contracts"


@pytest.fixture(scope="session")
def pessoa_fisica_contract() -> EntityContract:
    """Carrega o contrato real `pessoa_fisica.yaml` usado em produção."""
    loader = ContractLoader(CONTRACTS_DIR)
    return loader.load("pessoa_fisica")


def make_valid_record(**overrides):
    """Registro de pessoa física válido, com overrides pontuais para os testes."""
    record = {
        "id": "001",
        "nome": "Maria da Silva",
        "cpf": "11144477735",
        "data_nascimento": "1990-05-15",
        "email": "maria@email.com",
        "cidade": "São Paulo",
        "uf": "SP",
        "status": "ativo",
        "renda_mensal": 5500.0,
    }
    record.update(overrides)
    return record
