from __future__ import annotations

import asyncio
from typing import Any

from crawler_machine.config import DomainConfig
from crawler_machine.output import OutputPath
from crawler_machine.pipeline.persistence import (
    save_discovery_output,
    save_errors_output,
    save_normalized_output,
    save_quality_report,
    save_raw_output,
    save_rejected_output,
    save_schema_output,
)
from crawler_machine.pipeline.protocols import (
    CrawlerFactory,
    Discoverer,
    ProgressCallback,
    SchemaGenerator,
    Sink,
)
from crawler_machine.pipeline.state import ExecutionState, PipelineResult
from crawler_machine.pipeline.steps import (
    build_schema,
    crawl_urls,
    discover_urls,
    exterminate_records,
    make_empty_state,
    normalize_records,
)


class Pipeline:
    """Orquestra as cinco etapas do sistema."""

    def __init__(
        self,
        config: DomainConfig | dict[str, Any],
        output: OutputPath,
        discoverer: Discoverer,
        schema_generator: SchemaGenerator,
        crawler_factory: CrawlerFactory,
        progress_callback: ProgressCallback | None = None,
        sink: Sink | None = None,
        source_name: str | None = None,
        catalog_repository: "CatalogRepository" | None = None,
    ):
        self._config = config
        self._output = output
        self._discoverer = discoverer
        self._schema_generator = schema_generator
        self._crawler_factory = crawler_factory
        self._progress_callback = progress_callback
        self._sink = sink
        self._source_name = source_name
        self._catalog_repository = catalog_repository

    async def run(
        self,
        base_url: str,
        sample_url: str | None = None,
        regenerate_discovery: bool = False,
        regenerate_schema: bool = False,
    ) -> PipelineResult:
        """Executa o pipeline completo.

        Quando um sink Postgres está configurado, reusa resultados de discovery
        e schema de execuções anteriores por padrão. Use ``regenerate_discovery``
        ou ``regenerate_schema`` para forçar nova geração.
        """
        self._ensure_source_name()
        source_name = self._source_name
        run_id = await self._start_sink_run(source_name)

        try:
            state = await self._execute_steps(
                source_name=source_name,
                base_url=base_url,
                sample_url=sample_url,
                regenerate_discovery=regenerate_discovery,
                regenerate_schema=regenerate_schema,
            )
            return await self._finalize(source_name, run_id, state)
        except Exception as exc:
            await self._fail_sink_run(run_id, exc)
            raise

    def run_sync(
        self,
        base_url: str,
        sample_url: str | None = None,
        regenerate_discovery: bool = False,
        regenerate_schema: bool = False,
    ) -> PipelineResult:
        """Versão síncrona de ``run``."""
        return asyncio.run(
            self.run(
                base_url,
                sample_url=sample_url,
                regenerate_discovery=regenerate_discovery,
                regenerate_schema=regenerate_schema,
            )
        )

    def _ensure_source_name(self) -> None:
        if self._source_name is None:
            raise ValueError(
                "source_name é obrigatório. Passe --source-name explicitamente."
            )

    async def _start_sink_run(self, source_name: str) -> int | None:
        if self._sink is None:
            return None
        return await asyncio.to_thread(self._sink.start_run, source_name)

    async def _fail_sink_run(self, run_id: int | None, exc: Exception) -> None:
        if self._sink is None or run_id is None:
            return
        await asyncio.to_thread(self._sink.fail_run, run_id, str(exc))

    async def _execute_steps(
        self,
        source_name: str,
        base_url: str,
        sample_url: str | None,
        regenerate_discovery: bool,
        regenerate_schema: bool,
    ) -> ExecutionState:
        urls, discovery_run_id = await discover_urls(
            source_name,
            base_url,
            regenerate_discovery,
            self._discoverer,
            self._sink,
            self._progress_callback,
        )
        save_discovery_output(self._output, urls, base_url)

        if not urls:
            return make_empty_state()

        schema, schema_run_id = await build_schema(
            source_name,
            sample_url,
            regenerate_schema,
            self._schema_generator,
            self._sink,
            self._progress_callback,
        )
        save_schema_output(self._output, schema, sample_url)

        raw_data, errors = await crawl_urls(
            urls,
            schema,
            self._crawler_factory,
            self._progress_callback,
        )
        survivors, rejected = exterminate_records(
            raw_data, self._progress_callback
        )
        normalized, quality_report = normalize_records(
            survivors,
            self._config,
            self._sink,
            self._progress_callback,
            catalog_repository=self._catalog_repository,
        )

        return ExecutionState(
            urls=urls,
            schema=schema,
            raw_data=raw_data,
            errors=errors,
            survivors=survivors,
            rejected=rejected,
            normalized=normalized,
            quality_report=quality_report,
            discovery_run_id=discovery_run_id,
            schema_run_id=schema_run_id,
        )

    async def _finalize(
        self,
        source_name: str,
        run_id: int | None,
        state: ExecutionState,
    ) -> PipelineResult:
        self._persist_outputs(state)
        final_run_id = await self._save_run_to_sink(source_name, run_id, state)
        self._report("pipeline", 100, "Pipeline concluído")
        return PipelineResult(
            normalized=state.normalized,
            errors=state.errors,
            output=self._output,
            rejected=state.rejected,
            run_id=final_run_id,
        )

    async def _save_run_to_sink(
        self,
        source_name: str,
        run_id: int | None,
        state: ExecutionState,
    ) -> int | None:
        if self._sink is None:
            return None

        if not state.urls:
            return await asyncio.to_thread(
                self._sink.save_run, source_name, [], [], []
            )

        final_run_id = await asyncio.to_thread(
            self._sink.save_run,
            source_name,
            state.raw_data,
            state.normalized,
            state.errors,
        )
        self._report(
            "sink",
            100,
            f"Dados persistidos no Postgres (run {final_run_id})",
        )
        await self._link_runs(final_run_id, state)
        return final_run_id

    async def _link_runs(
        self, run_id: int | None, state: ExecutionState
    ) -> None:
        if self._sink is None or run_id is None:
            return

        if state.discovery_run_id is not None:
            await asyncio.to_thread(
                self._sink.link_discovery_run, state.discovery_run_id, run_id
            )
        if state.schema_run_id is not None:
            await asyncio.to_thread(
                self._sink.link_schema_run, state.schema_run_id, run_id
            )

    def _persist_outputs(self, state: ExecutionState) -> None:
        self._output.prepare()
        save_raw_output(self._output, state.raw_data, state.errors)
        save_normalized_output(self._output, state.normalized)
        save_rejected_output(self._output, state.rejected)
        save_quality_report(self._output, state.rejected, state.quality_report)
        save_errors_output(self._output, state.errors)
        self._report("normalize", 100, "Dados normalizados")

    def _report(self, step: str, percent: int, message: str) -> None:
        if self._progress_callback is not None:
            self._progress_callback(step, percent, message)
