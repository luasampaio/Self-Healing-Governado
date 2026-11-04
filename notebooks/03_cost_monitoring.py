"""
03 — Cost Monitoring

Notebook para monitoramento de custos operacionais do pipeline.
Calcula métricas de eficiência:
- Taxa de auto-correção vs. revisão manual
- Volume de quarentena.
- Estimativa de economia de horas de trabalho manual.

Uso:
    Executar após cada batch para acompanhamento de KPIs.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# Parâmetros de custo (ajustar conforme a operação)
COST_PER_MANUAL_REVIEW_MIN = 5       # minutos por revisão manual
COST_PER_HOUR_ANALYST_BRL = 80.0     # custo/hora do analista (R$)
COST_LLM_PER_1K_TOKENS_USD = 0.002   # custo LLM (quando utilizada)


def load_audit_log(audit_path: Path) -> list:
    """Carrega entradas do audit log."""
    entries = []
    if not audit_path.exists():
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
    print("Self-Healing Governado — Cost Monitoring")
    print("=" * 60)
    print()

    entries = load_audit_log(audit_path)
    total = len(entries)

    if total == 0:
        print("Nenhuma entrada no audit log para análise.")
        return

    # Contagem por decisão
    counts = {
        "approved": 0,
        "auto_correct": 0,
        "review_pending": 0,
        "quarantined": 0,
    }
    for e in entries:
        decision = e.get("decision", "unknown")
        counts[decision] = counts.get(decision, 0) + 1

    # ---------------------------------------------------------------
    # Métricas
    # ---------------------------------------------------------------

    auto_resolved = counts["approved"] + counts["auto_correct"]
    auto_resolution_rate = (auto_resolved / total * 100) if total > 0 else 0

    manual_needed = counts["review_pending"]
    manual_hours = (manual_needed * COST_PER_MANUAL_REVIEW_MIN) / 60
    manual_cost_brl = manual_hours * COST_PER_HOUR_ANALYST_BRL

    saved_reviews = counts["auto_correct"]
    saved_hours = (saved_reviews * COST_PER_MANUAL_REVIEW_MIN) / 60
    saved_cost_brl = saved_hours * COST_PER_HOUR_ANALYST_BRL

    print(f"  Total de registros processados:   {total}")
    print()
    print(f"  Decisoes:")
    print(f"    [OK] Approved:        {counts['approved']:>5}")
    print(f"    [FX] Auto Correct:    {counts['auto_correct']:>5}")
    print(f"    [RV] Review Pending:  {counts['review_pending']:>5}")
    print(f"    [QT] Quarantined:     {counts['quarantined']:>5}")
    print()
    print(f"  Taxa de resolução automática:   {auto_resolution_rate:.1f}%")
    print()

    print(f"{'-' * 50}")
    print(f"  Estimativa de Custos Operacionais")
    print(f"{'-' * 50}")
    print()
    print(f"  Revisões manuais necessárias:  {manual_needed}")
    print(f"    -> Horas estimadas:           {manual_hours:.1f}h")
    print(f"    -> Custo estimado:            R$ {manual_cost_brl:,.2f}")
    print()
    print(f"  Revisões evitadas (auto-correct): {saved_reviews}")
    print(f"    -> Horas economizadas:        {saved_hours:.1f}h")
    print(f"    -> Economia estimada:         R$ {saved_cost_brl:,.2f}")
    print()

    print(f"{'=' * 60}")
    print(f"  ROI do Self-Healing neste batch:")
    if manual_cost_brl > 0:
        roi = (saved_cost_brl / (manual_cost_brl + saved_cost_brl)) * 100
        print(f"    {roi:.1f}% do esforço manual foi automatizado.")
    else:
        print(f"    100% — nenhuma revisão manual necessária!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
