"""Credential redaction at the diagnostic evidence boundary."""

from crawler_machine.diagnostics import safe_message


def test_diagnostic_messages_bound_and_redact_credentials():
    assert safe_message(None) is None
    assert (
        safe_message("api_key=private token=private Bearer private")
        == "api_key=[redacted] token=[redacted] Bearer [redacted]"
    )
    assert len(safe_message("x" * 3000)) == 2000
