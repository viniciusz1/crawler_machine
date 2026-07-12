from crawler_machine.cli.app import app
from crawler_machine.cli.commands import (
    clone_das_sombras,
    crawl,
    discover,
    normalize,
    prospecting,
    run,
    schema,
)

app.add_typer(prospecting.prospecting_app, name="prospecting")

__all__ = ["app"]
