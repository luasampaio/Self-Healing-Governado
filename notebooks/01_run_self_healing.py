"""
01 - Run Self-Healing Pipeline

Notebook principal para executar o pipeline de remediação.
Processa um lote de registros e exibe resultados por decisão.

Uso:
    Executar em Databricks como Job ou localmente para desenvolvimento.
"""

import sys
from pathlib import Path

# Ajuste de path para execução local
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quality_audit.orchestrator import SelfHealingOrchestrator


def main():
    # ---------------------------------------------------------------
    # 1. Configuração
    # ---------------------------------------------------------------
    contracts_dir = PROJECT_ROOT / "src" / "quality_audit" / "contracts"
    audit_output = PROJECT_ROOT / "output" / "audit_log.jsonl"

    orchestrator = SelfHealingOrchestrator.from_config(
        contracts_dir=contracts_dir,
        entity_name="pessoa_fisica",
        audit_output=audit_output,
        max_corrections_per_record=3,
        quarantine_on_missing_required=True,
        quarantine_on_schema_violation=False,
    )

    # ---------------------------------------------------------------
    # 2. Dados de exemplo (em produção: leitura de Delta Table)
    # ---------------------------------------------------------------
    sample_records = [
        {
            "id": "001",
            "nome": "Maria da Silva",
            "cpf": "123.456.789-09",
            "data_nascimento": "1990-05-15",
            "email": "Maria.Silva@Email.COM",
            "cidade": "São Paulo",
            "uf": "sp",
            "status": "ativo",
            "renda_mensal": 5500.0,
        },
        {
            "id": "002",
            "nome": "João Oliveira",
            "cpf": "98765432100",
            "data_nascimento": "1985-03-20",
            "email": "joao@teste.com",
            "cidade": "Rio de Janeiro",
            "uf": "RJ",
            "status": "ativo",
            "renda_mensal": 8000.0,
        },
        {
            "id": "003",
            "nome": "  Ana Costa  ",
            "cpf": "11111111111",
            "data_nascimento": "2000-12-01",
            "email": "ana@teste.com",
            "cidade": "Curitiba",
            "uf": "PR",
            "status": "pendente",  # valor inválido
            "renda_mensal": -500.0,  # valor negativo
        },
        {
            "id": "004",
            "nome": None,  # campo obrigatório nulo
            "cpf": "12345",  # CPF inválido
            "data_nascimento": "1995-07-10",
            "cidade": "Manaus",
            "uf": "AM",
            "status": "ativo",
        },
    ]

    # ---------------------------------------------------------------
    # 3. Processamento
    # ---------------------------------------------------------------
    print("=" * 60)
    print("Self-Healing Governado - Pipeline de Remediação")
    print("=" * 60)
    print()

    results = orchestrator.process_batch(sample_records)

    # ---------------------------------------------------------------
    # 4. Resultados
    # ---------------------------------------------------------------
    for decision, records in results.items():
        print(f"\n{'-' * 40}")
        print(f"  {decision.upper()} - {len(records)} registro(s)")
        print(f"{'-' * 40}")
        for r in records:
            print(f"  ID: {r.record_id}")
            if r.corrections_applied:
                print(f"    Correções: {len(r.corrections_applied)}")
            if r.review_reasons:
                print(f"    Motivos revisão: {r.review_reasons}")
            if r.quarantine_reasons:
                print(f"    Motivos quarentena: {r.quarantine_reasons}")

    # ---------------------------------------------------------------
    # 5. Resumo
    # ---------------------------------------------------------------
    summary = orchestrator.get_audit_summary()
    print("\n" + "=" * 60)
    print("Resumo do Audit Log")
    print(f"{'=' * 60}")
    for decision, count in summary.items():
        print(f"  {decision:20s} -> {count}")
    print()


if __name__ == "__main__":
    main()
