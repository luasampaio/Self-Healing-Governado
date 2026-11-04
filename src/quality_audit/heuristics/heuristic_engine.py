"""
Heuristic Engine — Motor de heurísticas seguras.

Aplica correções baseadas em heurísticas (ex: inferência de UF por cidade,
preenchimento por moda estatística, etc.) com score de confiança.
A LLM pode ser usada como camada complementar, nunca como autoridade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class HeuristicSuggestion:
    """Uma sugestão de correção produzida por heurística."""

    field: str
    original_value: Any
    suggested_value: Any
    confidence: float  # 0.0 a 1.0
    heuristic_name: str
    reasoning: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "original_value": self.original_value,
            "suggested_value": self.suggested_value,
            "confidence": self.confidence,
            "heuristic_name": self.heuristic_name,
            "reasoning": self.reasoning,
        }


class HeuristicEngine:
    """
    Motor de heurísticas seguras.

    Cada heurística produz sugestões com score de confiança.
    Sugestões com confiança >= threshold são candidatas a auto-correção.
    Sugestões abaixo vão para revisão humana.
    """

    def __init__(self, confidence_threshold: float = 0.85) -> None:
        self.confidence_threshold = confidence_threshold
        self._heuristics: List[Callable] = []

    def register(self, heuristic_fn: Callable) -> None:
        """
        Registra uma heurística.

        A heurística deve ter a assinatura:
            fn(record: dict, field: str, value: Any) -> Optional[HeuristicSuggestion]
        """
        self._heuristics.append(heuristic_fn)

    def evaluate(
        self, record: Dict[str, Any], fields_with_issues: List[str]
    ) -> Tuple[List[HeuristicSuggestion], List[HeuristicSuggestion]]:
        """
        Avalia heurísticas para campos com problemas.

        Retorna:
            - high_confidence: sugestões acima do threshold (candidatas a auto-correct).
            - low_confidence: sugestões abaixo do threshold (review pending).
        """
        high_confidence: List[HeuristicSuggestion] = []
        low_confidence: List[HeuristicSuggestion] = []

        for field in fields_with_issues:
            value = record.get(field)

            for heuristic_fn in self._heuristics:
                suggestion = heuristic_fn(record, field, value)
                if suggestion is None:
                    continue

                if suggestion.confidence >= self.confidence_threshold:
                    high_confidence.append(suggestion)
                else:
                    low_confidence.append(suggestion)

        return high_confidence, low_confidence

    # ------------------------------------------------------------------
    # Heurísticas built-in de exemplo
    # ------------------------------------------------------------------

    @staticmethod
    def uf_from_known_cities() -> Callable:
        """
        Heurística: infere UF a partir de cidade conhecida.

        Exemplo simplificado com lookup table.
        """
        _CITY_TO_UF = {
            "são paulo": "SP",
            "rio de janeiro": "RJ",
            "belo horizonte": "MG",
            "curitiba": "PR",
            "porto alegre": "RS",
            "salvador": "BA",
            "brasília": "DF",
            "fortaleza": "CE",
            "recife": "PE",
            "manaus": "AM",
        }

        def _infer(record: Dict[str, Any], field: str, value: Any) -> Optional[HeuristicSuggestion]:
            if field != "uf" or value is not None:
                return None

            city = record.get("cidade", "")
            if not isinstance(city, str):
                return None

            inferred = _CITY_TO_UF.get(city.strip().lower())
            if inferred:
                return HeuristicSuggestion(
                    field="uf",
                    original_value=value,
                    suggested_value=inferred,
                    confidence=0.90,
                    heuristic_name="uf_from_known_cities",
                    reasoning=f"UF inferida a partir da cidade '{city}'.",
                )
            return None

        return _infer
