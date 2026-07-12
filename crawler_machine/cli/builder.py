from __future__ import annotations

from pathlib import Path
from typing import Any

from tqdm import tqdm

from crawler_machine.batch import build_default_runner
from crawler_machine.config import DomainConfig
from crawler_machine.output import OutputPath
from crawler_machine.pipeline import build_pipeline as build_pipeline_core


def build_pipeline(
    config: DomainConfig,
    output: OutputPath,
    progress_bar: tqdm[Any] | None = None,
    verbose: bool = False,
    sink: Any | None = None,
    source_name: str | None = None,
    enable_llm_fallback: bool | None = None,
) -> Any:
    def _progress_callback(step: str, percent: int, message: str) -> None:
        import logging

        logging.info(f"[{percent:3d}%] [{step}] {message}")
        if progress_bar is not None:
            progress_bar.set_description(f"{step}: {message}")
            progress_bar.n = percent
            progress_bar.refresh()

    return build_pipeline_core(
        config=config,
        output=output,
        source_name=source_name,
        sink=sink,
        progress_callback=_progress_callback,
        enable_llm_fallback=enable_llm_fallback,
        verbose=verbose,
    )


def build_batch_runner(
    config: DomainConfig,
    output_dir: Path,
    verbose: bool = False,
    sink: Any | None = None,
) -> Any:
    return build_default_runner(
        config=config,
        output_dir=output_dir,
        verbose=verbose,
        sink=sink,
    )
