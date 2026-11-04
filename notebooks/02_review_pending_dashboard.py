"""
02 — Review Pending Dashboard

Notebook para revisão de registros classificados como REVIEW_PENDING.
Exibe registros pendentes de revisão humana com detalhes das sugestões
heurísticas e violações de domínio.

Uso:
    Executar periodicamente para triagem manual de exceções.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def load_audit_log(audit_path: Path) -> list:
    """Carrega entradas do audit log (JSON Lines)."""
    entries = []
    if not audit_path.exists():
        print(f"Arquivo de audit não encontrado: {audit_path}")
        return entries

    with open(audit_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def main():
    audit_path = PROJECT_ROOT / "output" / "audit_log.jsonl"

    print("=" * 60)
    print("Self-Healing Governado — Review Pending Dashboard")
    print("=" * 60)
    print()

    entries = load_audit_log(audit_path)

    if not entries:
        print("Nenhuma entrada no audit log.")
        return

    # Filtrar review_pending
    review_pending = [e for e in entries if e.get("decision") == "review_pending"]

    if not review_pending:
        print("Nenhum registro pendente de revisão.")
        return

    print(f"Total de registros pendentes: {len(review_pending)}")
    print()

    for i, entry in enumerate(review_pending, 1):
        print(f"{'-' * 50}")
        print(f"  [{i}] Record ID: {entry.get('record_id', 'N/A')}")
        print(f"      Timestamp:  {entry.get('timestamp', 'N/A')}")
        print(f"      Motivos:")
        for reason in entry.get("review_reasons", []):
            print(f"        - {reason}")

        corrections = entry.get("corrections", [])
        if corrections:
            print(f"      Correções já aplicadas: {len(corrections)}")
            for c in corrections:
                print(f"        - {c.get('field', '?')}: "
                    f"{c.get('original_value', '?')} -> {c.get('corrected_value', '?')} "
                    f"({c.get('rule_name', '?')})")

        original = entry.get("original_record", {})
        if original:
            print(f"      Registro original: {json.dumps(original, ensure_ascii=False, default=str)}")
        print()

    # ---------------------------------------------------------------
    # Em produção com Databricks:
    # - Exibir como tabela interativa (displayHTML ou Databricks SQL)
    # - Permitir aprovar/rejeitar diretamente
    # - Atualizar status no Delta Table
    # ---------------------------------------------------------------
    print(f"{'=' * 60}")
    print("Para aprovar ou rejeitar registros, use o fluxo de revisão.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
