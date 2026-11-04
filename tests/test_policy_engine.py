"""Testes do PolicyEngine — motor de decisão operacional.

Cobre a ordem de prioridade documentada em PolicyEngine.evaluate:
Quarentena > Review Pending > Auto Correct > Approved.
"""

from __future__ import annotations

from quality_audit.policy.policy_engine import Decision, PolicyEngine


def _base_kwargs(**overrides):
    kwargs = dict(
        record_id="001",
        original_record={"id": "001"},
        schema_errors=[],
        required_errors={"missing_fields": [], "null_fields": []},
        domain_violations=[],
        deterministic_corrections=[],
        heuristic_high=[],
        heuristic_low=[],
        corrected_record={"id": "001"},
    )
    kwargs.update(overrides)
    return kwargs


class TestApproved:
    def test_registro_limpo_e_aprovado(self):
        engine = PolicyEngine()
        result = engine.evaluate(**_base_kwargs())
        assert result.decision == Decision.APPROVED


class TestAutoCorrect:
    def test_correcoes_deterministicas_geram_auto_correct(self):
        engine = PolicyEngine()
        result = engine.evaluate(
            **_base_kwargs(
                deterministic_corrections=[{"field": "uf", "rule_name": "uf_uppercase"}]
            )
        )
        assert result.decision == Decision.AUTO_CORRECT
        assert len(result.corrections_applied) == 1

    def test_heuristica_alta_confianca_gera_auto_correct(self):
        engine = PolicyEngine()
        result = engine.evaluate(
            **_base_kwargs(
                heuristic_high=[{"field": "uf", "heuristic_name": "uf_from_known_cities"}]
            )
        )
        assert result.decision == Decision.AUTO_CORRECT


class TestReviewPending:
    def test_heuristica_baixa_confianca_gera_review(self):
        engine = PolicyEngine()
        result = engine.evaluate(
            **_base_kwargs(heuristic_low=[{"field": "uf", "confidence": 0.5}])
        )
        assert result.decision == Decision.REVIEW_PENDING

    def test_campo_obrigatorio_nulo_gera_review(self):
        engine = PolicyEngine()
        result = engine.evaluate(
            **_base_kwargs(required_errors={"missing_fields": [], "null_fields": ["nome"]})
        )
        assert result.decision == Decision.REVIEW_PENDING

    def test_violacao_de_dominio_gera_review(self):
        engine = PolicyEngine()
        result = engine.evaluate(
            **_base_kwargs(domain_violations=[{"field": "renda_mensal", "rule": "min_value"}])
        )
        assert result.decision == Decision.REVIEW_PENDING

    def test_review_tem_prioridade_sobre_auto_correct(self):
        """Mesmo com correções determinísticas aplicadas, uma violação de domínio
        pendente deve mandar o registro para revisão, não para auto-correct."""
        engine = PolicyEngine()
        result = engine.evaluate(
            **_base_kwargs(
                deterministic_corrections=[{"field": "cpf", "rule_name": "cpf_remove_punctuation"}],
                domain_violations=[{"field": "renda_mensal", "rule": "min_value"}],
            )
        )
        assert result.decision == Decision.REVIEW_PENDING


class TestQuarantine:
    def test_campo_obrigatorio_ausente_gera_quarentena(self):
        engine = PolicyEngine(quarantine_on_missing_required=True)
        result = engine.evaluate(
            **_base_kwargs(required_errors={"missing_fields": ["nome"], "null_fields": []})
        )
        assert result.decision == Decision.QUARANTINED

    def test_violacao_de_schema_gera_quarentena_quando_configurado(self):
        engine = PolicyEngine(quarantine_on_schema_violation=True)
        result = engine.evaluate(
            **_base_kwargs(schema_errors=[{"field": "renda_mensal", "message": "tipo inválido"}])
        )
        assert result.decision == Decision.QUARANTINED

    def test_violacao_de_schema_nao_quarentena_quando_desabilitado(self):
        engine = PolicyEngine(quarantine_on_schema_violation=False)
        result = engine.evaluate(
            **_base_kwargs(schema_errors=[{"field": "renda_mensal", "message": "tipo inválido"}])
        )
        assert result.decision != Decision.QUARANTINED

    def test_excesso_de_correcoes_gera_quarentena(self):
        engine = PolicyEngine(max_corrections_per_record=1)
        result = engine.evaluate(
            **_base_kwargs(
                deterministic_corrections=[
                    {"field": "uf", "rule_name": "uf_uppercase"},
                    {"field": "cpf", "rule_name": "cpf_remove_punctuation"},
                ]
            )
        )
        assert result.decision == Decision.QUARANTINED

    def test_quarentena_tem_prioridade_sobre_tudo(self):
        """Campo obrigatório ausente deve quarentenar mesmo havendo também
        heurísticas de baixa confiança (que isoladamente geram review_pending)."""
        engine = PolicyEngine()
        result = engine.evaluate(
            **_base_kwargs(
                required_errors={"missing_fields": ["nome"], "null_fields": []},
                heuristic_low=[{"field": "uf", "confidence": 0.5}],
            )
        )
        assert result.decision == Decision.QUARANTINED
