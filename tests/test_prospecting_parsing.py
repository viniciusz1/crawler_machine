import pytest

from crawler_machine.prospecting.models import CityTarget
from crawler_machine.prospecting.parsing import CityParseError, parse_cities


def test_parse_single_city():
    targets = parse_cities("Joinville,SC")
    assert targets == [CityTarget("Joinville", "SC")]


def test_parse_multiple_cities_semicolon_separated():
    targets = parse_cities("Joinville,SC;Blumenau,SC")
    assert targets == [CityTarget("Joinville", "SC"), CityTarget("Blumenau", "SC")]


def test_parse_normalizes_state_to_uppercase():
    targets = parse_cities("jaragua do sul,sc")
    assert targets == [CityTarget("jaragua do sul", "SC")]


def test_parse_tolerates_spaces_around_comma():
    targets = parse_cities("Joinville, SC ; Blumenau , SC")
    assert targets == [CityTarget("Joinville", "SC"), CityTarget("Blumenau", "SC")]


def test_parse_ignores_trailing_separator():
    targets = parse_cities("Joinville,SC;")
    assert targets == [CityTarget("Joinville", "SC")]


def test_parse_empty_string_raises():
    with pytest.raises(CityParseError, match="vazia"):
        parse_cities("")


def test_parse_only_separators_raises():
    with pytest.raises(CityParseError, match="nenhuma cidade"):
        parse_cities(";;")


def test_parse_missing_state_raises():
    with pytest.raises(CityParseError, match="malformada"):
        parse_cities("Joinville")


def test_parse_extra_components_raises():
    with pytest.raises(CityParseError, match="malformada"):
        parse_cities("Joinville,SC,extra")


def test_parse_long_state_name_raises():
    with pytest.raises(CityParseError, match="UF inválida"):
        parse_cities("Joinville,Santa Catarina")


def test_parse_empty_state_raises():
    with pytest.raises(CityParseError, match="UF inválida"):
        parse_cities("Joinville,")


def test_parse_empty_city_raises():
    with pytest.raises(CityParseError, match="nome de cidade vazio"):
        parse_cities(",SC")
