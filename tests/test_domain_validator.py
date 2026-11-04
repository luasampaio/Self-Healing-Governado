"""Testes do DomainValidator — regras de domínio (CPF, UF, ranges)."""

from __future__ import annotations

from quality_audit.validators.domain_validator import DomainValidator

from .conftest import make_valid_record


def _rules(result):
    return {v.rule for v in result.violations}


class TestCpf:
    def test_cpf_valido_nao_gera_violacao(self, pessoa_fisica_contract):
        validator = DomainValidator(pessoa_fisica_contract)
        record = make_valid_record(cpf="11144477735")

        result = validator.validate(record)

        assert "cpf_formato" not in _rules(result)
        assert "cpf_digito_verificador" not in _rules(result)
        assert "cpf_digitos_iguais" not in _rules(result)

    def test_cpf_com_menos_de_11_digitos_e_invalido(self, pessoa_fisica_contract):
        validator = DomainValidator(pessoa_fisica_contract)
        record = make_valid_record(cpf="12345")

        result = validator.validate(record)

        assert "cpf_formato" in _rules(result)

    def test_cpf_com_todos_digitos_iguais_e_invalido(self, pessoa_fisica_contract):
        validator = DomainValidator(pessoa_fisica_contract)
        record = make_valid_record(cpf="11111111111")

        result = validator.validate(record)

        assert "cpf_digitos_iguais" in _rules(result)

    def test_cpf_com_digito_verificador_errado_e_invalido(self, pessoa_fisica_contract):
        validator = DomainValidator(pessoa_fisica_contract)
        # Mesmos 9 primeiros dígitos de um CPF válido, dígitos verificadores trocados.
        record = make_valid_record(cpf="11144477701")

        result = validator.validate(record)

        assert "cpf_digito_verificador" in _rules(result)

    def test_cpf_com_pontuacao_e_validado_pelos_digitos(self, pessoa_fisica_contract):
        """O DomainValidator não normaliza pontuação — isso é papel do DeterministicRules.
        Aqui garantimos apenas que o CPF pontuado, mas com 11 dígitos válidos
        após a limpeza, não é marcado como formato inválido."""
        validator = DomainValidator(pessoa_fisica_contract)
        record = make_valid_record(cpf="111.444.777-35")

        result = validator.validate(record)

        assert "cpf_formato" not in _rules(result)


class TestUf:
    def test_uf_valida_nao_gera_violacao(self, pessoa_fisica_contract):
        validator = DomainValidator(pessoa_fisica_contract)
        record = make_valid_record(uf="RJ")

        result = validator.validate(record)

        assert "uf_valida" not in _rules(result)

    def test_uf_invalida_gera_violacao(self, pessoa_fisica_contract):
        validator = DomainValidator(pessoa_fisica_contract)
        record = make_valid_record(uf="XX")

        result = validator.validate(record)

        assert "uf_valida" in _rules(result)

    def test_uf_minuscula_e_aceita_por_case_insensitive(self, pessoa_fisica_contract):
        """_validate_uf normaliza para upper antes de comparar com a lista de UFs."""
        validator = DomainValidator(pessoa_fisica_contract)
        record = make_valid_record(uf="sp")

        result = validator.validate(record)

        assert "uf_valida" not in _rules(result)


class TestRangeENominais:
    def test_renda_negativa_viola_min_value(self, pessoa_fisica_contract):
        validator = DomainValidator(pessoa_fisica_contract)
        record = make_valid_record(renda_mensal=-500.0)

        result = validator.validate(record)

        assert "min_value" in _rules(result)

    def test_renda_acima_do_maximo_viola_max_value(self, pessoa_fisica_contract):
        validator = DomainValidator(pessoa_fisica_contract)
        record = make_valid_record(renda_mensal=2_000_000.0)

        result = validator.validate(record)

        assert "max_value" in _rules(result)

    def test_status_fora_dos_permitidos_viola_allowed_values(self, pessoa_fisica_contract):
        validator = DomainValidator(pessoa_fisica_contract)
        record = make_valid_record(status="pendente")

        result = validator.validate(record)

        assert "allowed_values" in _rules(result)
