"""Tool-binding and structured-output assembly for ChatLiteLLM.

[INPUT]
- adapters.schema::normalize_tool_schema (POS: provider-compatible OpenAI tool schemas)
- adapters.model_capability::ModelCapabilityDetector (POS: whether an endpoint accepts a constrained tool-call transport, imported lazily)
- adapters.gateway_normalizer::is_transport_stripped (POS: whether a gateway strips constrained transports, imported lazily)

[OUTPUT]
- tool_bind_kwargs(): the keyword arguments ``bind_tools`` hands to ``bind`` (tool-schema conversion, tool-choice normalization, constrained tool-call transport)
- structured_output_bind_kwargs() / structured_output_chain(): JSON-mode binding arguments and the parser chain behind ``with_structured_output``

[POS]
Pure assembly with no provider call. ``ChatLiteLLM.bind_tools`` / ``with_structured_output`` in ``model.py`` keep the
LangChain-facing signatures and delegate here.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from operator import itemgetter
from typing import Any, cast

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import JsonOutputParser, PydanticOutputParser
from langchain_core.runnables import Runnable, RunnableMap, RunnablePassthrough
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_core.utils.pydantic import is_basemodel_subclass
from pydantic import BaseModel

from myrm_agent_harness.toolkits.llms.adapters.schema import normalize_tool_schema

logger = logging.getLogger(__name__)


def tool_bind_kwargs(
    tools: Sequence[dict[str, Any] | type | BaseTool | Any],
    *,
    model_id: str,
    api_base: str,
    custom_llm_provider: str,
    tool_choice: str | dict[str, Any] | None,
    parallel_tool_calls: bool | None,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """Keyword arguments for ``bind``: OpenAI tool schemas, tool choice and, where supported, a constrained transport."""
    logger.debug(f"bind_tools called with {len(tools) if tools else 0} tools")
    openai_tools: list[dict[str, Any]] = []
    for t in tools:
        if isinstance(t, dict) and "function" in t:
            openai_tools.append(normalize_tool_schema(t, model_name=model_id))
        else:
            try:
                openai_tools.append(normalize_tool_schema(convert_to_openai_tool(t), model_name=model_id))
            except Exception as e:
                logger.warning(
                    "Failed to convert tool %s: %s",
                    getattr(t, "name", t),
                    e,
                )
                continue

    tool_choice_param: str | dict[str, Any] | None = None
    if tool_choice in ("auto", "any"):
        tool_choice_param = "auto"
    elif tool_choice == "none":
        tool_choice_param = "none"
    elif tool_choice == "required":
        tool_choice_param = "required"
    elif isinstance(tool_choice, str):
        # Specific tool name requested
        tool_choice_param = {"type": "function", "function": {"name": tool_choice}}
    elif isinstance(tool_choice, dict):
        tool_choice_param = tool_choice

    bind_kwargs: dict[str, Any] = {"tools": openai_tools}
    if not openai_tools:
        logger.debug(
            "bind_tools produced no OpenAI tools after conversion (input count=%s)",
            len(tools),
        )
    if tool_choice_param:
        bind_kwargs["tool_choice"] = tool_choice_param
    if parallel_tool_calls is not None:
        bind_kwargs["parallel_tool_calls"] = parallel_tool_calls

    # Local weak model grammar / structured output constraint transport
    from myrm_agent_harness.toolkits.llms.adapters.gateway_normalizer import (
        is_transport_stripped,
    )
    from myrm_agent_harness.toolkits.llms.adapters.model_capability import (
        ModelCapabilityDetector,
    )

    detector = ModelCapabilityDetector()
    if (
        openai_tools
        and detector.supports_json_schema_constrained_tool_calls(
            provider=custom_llm_provider,
            model=model_id,
            base_url=api_base,
        )
        and "response_format" not in extra
        and not is_transport_stripped(model=model_id, base_url=api_base)
    ):
        # Inject constrained tool call array schema for local llama-server/ollama/vLLM endpoints
        bind_kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "tool_calls_transport",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "tool_calls": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "arguments": {"type": "object"},
                                },
                                "required": ["name", "arguments"],
                            },
                        }
                    },
                    "required": ["tool_calls"],
                },
            },
        }

    bind_kwargs.update(extra)

    return bind_kwargs


def structured_output_bind_kwargs(
    schema: dict[str, Any] | type | None, *, skip_response_format: bool
) -> dict[str, Any]:
    """Keyword arguments for ``bind`` that put the model in JSON mode for ``schema``."""
    bind_kwargs: dict[str, Any] = {
        "_json_mode_fallback": True,
        "stream": False,
        "ls_structured_output_format": {"kwargs": {}, "schema": schema},
    }
    if not skip_response_format:
        bind_kwargs["response_format"] = {"type": "json_object"}
    return bind_kwargs


def structured_output_chain[BM: BaseModel](
    llm: Runnable[LanguageModelInput, AIMessage],
    schema: dict[str, Any] | type[BM] | type | None,
    *,
    include_raw: bool,
) -> Runnable[LanguageModelInput, dict[str, Any] | BM]:
    """Chain the JSON-mode ``llm`` into the output parser that matches ``schema``."""
    if isinstance(schema, type) and is_basemodel_subclass(schema):
        # schema is guaranteed to be Type[BaseModel] when is_basemodel_subclass holds
        output_parser: PydanticOutputParser[BaseModel] | JsonOutputParser = PydanticOutputParser(
            pydantic_object=cast(type[BaseModel], schema)
        )
    else:
        output_parser = JsonOutputParser()

    if include_raw:
        parser_assign = RunnablePassthrough.assign(
            parsed=itemgetter("raw") | output_parser, parsing_error=lambda _: None
        )
        parser_none = RunnablePassthrough.assign(parsed=lambda _: None)
        parser_with_fallback = parser_assign.with_fallbacks([parser_none], exception_key="parsing_error")
        return RunnableMap(raw=llm) | parser_with_fallback

    return llm | output_parser
