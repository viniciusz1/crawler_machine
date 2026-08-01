from tests.database_safety import is_test_database_name


def test_database_safety_only_accepts_explicit_test_database_names() -> None:
    assert is_test_database_name("ia_imob_test") is True
    assert is_test_database_name("ia-imob-test") is True
    assert is_test_database_name("ia_imob") is False
    assert is_test_database_name(None) is False
