import pytest
from typer.testing import CliRunner

from crawler_machine.cli import app

runner = CliRunner()


def test_worker_help_exposes_observability_identity_without_process_api():
    result = runner.invoke(app, ["worker", "--help"])

    assert result.exit_code == 0
    assert "--worker-key" in result.output
    assert "--version" in result.output


@pytest.mark.parametrize(
    "command",
    ["discover", "schema", "crawl", "normalize", "run", "clone-das-sombras", "prospecting"],
)
def test_legacy_terminal_commands_are_not_available(command: str):
    """Apenas o worker executa operações; os comandos de terminal foram removidos."""
    result = runner.invoke(app, [command, "--help"])

    assert result.exit_code != 0
    assert "No such command" in result.output
