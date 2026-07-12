from __future__ import annotations

import asyncio
import inspect
import logging
import os
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import litellm
from crawl4ai import LLMConfig as Crawl4AILLMConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

from crawler_machine.config import FieldConfig, LLMConfig

logger = logging.getLogger(__name__)

SchemaGeneratorFunc = Callable[..., dict[str, Any] | Awaitable[dict[str, Any]]]


class SchemaGenerator:
    """Gera um schema de extração (XPath/CSS) a partir de uma URL de exemplo."""

    def __init__(
        self,
        llm_config: LLMConfig,
        fields: list[FieldConfig],
        schema_type: str = "CSS",
        generator: SchemaGeneratorFunc | None = None,
        verbose: bool = False,
    ):
        self._llm_config = llm_config
        self._fields = fields
        self._schema_type = schema_type
        self._verbose = verbose
        self._generator = generator or self._default_generate

    def _build_query(self) -> str:
        """Monta a instrução natural a partir dos campos do domínio."""
        field_descriptions = [
            f"{field.name} ({field.description})" for field in self._fields
        ]
        return "Extraia: " + ", ".join(field_descriptions)

    async def generate(self, sample_url: str) -> dict[str, Any]:
        """Gera os schemas XPath e CSS para a URL de exemplo."""
        query = self._build_query()
        llm_config = self._build_crawl4ai_llm_config()

        previous_verbose = litellm.set_verbose
        if self._verbose:
            litellm.set_verbose = True
            logger.debug("Modo verbose ativado para chamadas LLM.")

        schemas: dict[str, dict[str, Any]] = {}
        try:
            for schema_type in ("XPATH", "CSS"):
                result = self._generator(
                    url=sample_url,
                    schema_type=schema_type,
                    query=query,
                    llm_config=llm_config,
                    validate=True,
                )
                schemas[schema_type.lower()] = (
                    await result if inspect.isawaitable(result) else result
                )
        except Exception as exc:
            if self._verbose:
                logger.error(
                    "Falha ao gerar schema. URL=%s provider=%s base_url=%s query=%s",
                    sample_url,
                    self._llm_config.provider,
                    self._llm_config.base_url,
                    query,
                )
            raise Exception(
                f"Erro ao gerar schema para {sample_url}: {exc}"
            ) from exc
        finally:
            litellm.set_verbose = previous_verbose

        return {
            "metadata": {
                "sample_url": sample_url,
                "generated_at": self._now_iso(),
            },
            "schemas": schemas,
        }

    def generate_sync(self, sample_url: str) -> dict[str, Any]:
        """Versão síncrona de ``generate``."""
        return asyncio.run(self.generate(sample_url))

    def validate_api_key(self) -> None:
        """Verifica se a chave de API está configurada."""
        api_key = os.environ.get(self._llm_config.api_key_env)
        if not api_key:
            raise RuntimeError(
                f"Variável de ambiente {self._llm_config.api_key_env} não definida. "
                "Crie um arquivo .env na raiz do projeto."
            )

    def _build_crawl4ai_llm_config(self) -> Crawl4AILLMConfig:
        """Monta a configuração de LLM do Crawl4AI."""
        return Crawl4AILLMConfig(
            provider=self._llm_config.provider,
            api_token=os.environ.get(self._llm_config.api_key_env, ""),
            base_url=self._llm_config.base_url,
            temperature=0.1,
            max_tokens=2000,
        )

    @staticmethod
    def _now_iso() -> str:
        """Retorna o instante atual no formato ISO 8601 (UTC)."""
        return datetime.now(timezone.utc).isoformat()

    def _default_generate(self, **kwargs: Any) -> dict[str, Any]:
        """Geração real usando Crawl4AI."""
        self.validate_api_key()
        if self._verbose:
            logger.debug(
                "Chamando JsonCssExtractionStrategy.generate_schema "
                "url=%s schema_type=%s validate=%s",
                kwargs.get("url"),
                kwargs.get("schema_type"),
                kwargs.get("validate"),
            )
        return JsonCssExtractionStrategy.generate_schema(**kwargs)
