import pytest

from crawler_machine.normalization.coercers import coerce_boolean, extract_first_number, parse_number
from crawler_machine.normalization.engine import DataNormalizer


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        (False, False),
        ("sim", True),
        ("não", False),
        ("yes", True),
        ("no", False),
        (1, True),
        (0, False),
        (None, None),
    ],
)
def test_coerce_boolean(value, expected):
    assert coerce_boolean(value) == expected


def test_extract_first_number_from_text_with_parentheses():
    assert extract_first_number("3 (sendo 1 suíte)") == 3.0


def test_extract_first_number_with_brazilian_decimal():
    assert extract_first_number("72 ~ 79 m²") == 72.0


def test_extract_first_number_with_currency():
    assert extract_first_number("R$ 450.000,00") == 450_000.0


def test_extract_first_number_returns_none_for_empty_string():
    assert extract_first_number("") is None


def test_parse_number_with_comma_as_decimal():
    assert parse_number("1,5") == 1.5


def test_parse_number_with_brazilian_thousands_and_decimal():
    assert parse_number("1.234,56") == 1234.56


@pytest.fixture
def fields():
    return [
        {"name": "tipo_imovel", "coerce": "string"},
        {"name": "quartos", "coerce": "int"},
        {"name": "valor", "coerce": "currency"},
        {"name": "area_util", "coerce": "float"},
        {"name": "sem_coercao"},
    ]


def test_normalizer_applies_coercions(fields):
    record = {
        "tipo_imovel": "  Apartamento  ",
        "quartos": "3 (sendo 1 suíte)",
        "valor": "R$ 450.000,00",
        "area_util": "72,5 m²",
        "sem_coercao": "mantém como está",
    }

    normalizer = DataNormalizer()
    result = normalizer.normalize(record, fields)

    assert result["tipo_imovel"] == "Apartamento"
    assert result["quartos"] == 3
    assert result["valor"] == 450_000.0
    assert result["area_util"] == 72.5
    assert result["sem_coercao"] == "mantém como está"
    assert result["_quality"]["valid"] is True


def test_normalizer_omits_fields_not_present_in_record(fields):
    record = {"quartos": "2"}

    normalizer = DataNormalizer()
    result = normalizer.normalize(record, fields)

    assert result["quartos"] == 2
    assert result["_quality"]["valid"] is True


def test_normalizer_normalize_many_records_and_returns_report(fields):
    records = [
        {"quartos": "2", "valor": "R$ 100.000,00"},
        {"quartos": "3", "valor": "R$ 200.000,00"},
    ]

    normalizer = DataNormalizer()
    normalized, report = normalizer.normalize_many(records, fields)

    assert len(normalized) == 2
    assert normalized[0]["quartos"] == 2
    assert normalized[0]["valor"] == 100_000.0
    assert normalized[1]["quartos"] == 3
    assert normalized[1]["valor"] == 200_000.0
    assert report["total_records"] == 2
    assert report["records_with_issues"] == []
