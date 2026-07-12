from __future__ import annotations

import warnings

from crawler_machine.sink.config import PostgresConfig
from crawler_machine.sink.run_store import RunStore


class PostgresSink(RunStore):
    """Destino Postgres legado.

    Mantido como alias para :class:`RunStore` para compatibilidade com
    chamadores existentes. Novo código deve usar :class:`RunStore`.
    """

    def __init__(self, config: PostgresConfig):
        warnings.warn(
            "PostgresSink is deprecated; use RunStore instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(config)
