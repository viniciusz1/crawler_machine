from __future__ import annotations

import typer

app = typer.Typer(
    help="Worker do Crawler Machine que executa operações enfileiradas no Postgres."
)


@app.callback()
def main() -> None:
    """Mantém o modo de subcomandos (``python -m crawler_machine worker``)."""
