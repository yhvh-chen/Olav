"""JSON utilities for handling LLM responses with markdown formatting.

This module provides functions to clean and parse JSON from LLM responses,
which often wrap JSON in markdown code blocks.

Also provides robust_structured_output() for reliable structured output
with OpenRouter and other providers that don't fully support JSON mode.
"""

import json
import logging
import re
from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSerializable
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def strip_markdown_json(content: str) -> str:
    """Strip markdown code block markers from JSON content.

    Handles various markdown formats:
    - ```json ... ```
    - ``` ... ```
    - Plain JSON

    Args:
        content: Raw LLM response content

    Returns:
        Cleaned JSON string without markdown markers
    """
    content = content.strip()

    # Pattern 1: ```json\n{...}\n```
    if content.startswith("```json"):
        content = content[7:]  # Remove ```json
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()

    # Pattern 2: ```\n{...}\n```
    if content.startswith("```"):
        content = content[3:]  # Remove ```
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()

    # Pattern 3: Look for JSON object/array within the content
    # This handles cases where markdown is embedded in other text
    json_match = re.search(r"```json\s*([\s\S]*?)\s*```", content)
    if json_match:
        return json_match.group(1).strip()

    json_match = re.search(r"```\s*([\s\S]*?)\s*```", content)
    if json_match:
        return json_match.group(1).strip()

    return content


def parse_json_response(content: str) -> dict[str, Any]:
    """Parse JSON from LLM response, handling markdown formatting.

    Args:
        content: Raw LLM response content

    Returns:
        Parsed JSON as dict

    Raises:
        json.JSONDecodeError: If content cannot be parsed as JSON
    """
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try stripping markdown
        cleaned = strip_markdown_json(content)
        return json.loads(cleaned)


def parse_pydantic_response(content: str, model_class: type[T]) -> T:
    """Parse and validate JSON response into a Pydantic model.

    Handles markdown formatting and validates against the model schema.

    Args:
        content: Raw LLM response content
        model_class: Pydantic model class to validate against

    Returns:
        Validated Pydantic model instance

    Raises:
        ValidationError: If content doesn't match model schema
        json.JSONDecodeError: If content cannot be parsed as JSON
    """
    try:
        # Try direct parsing first
        return model_class.model_validate_json(content)
    except Exception as e1:
        # Try stripping markdown and re-parsing
        cleaned = strip_markdown_json(content)
        try:
            return model_class.model_validate_json(cleaned)
        except Exception as e2:
            # Log the actual content for debugging
            logger.debug(f"Original content (first 500 chars): {content[:500]}")
            logger.debug(f"Cleaned content (first 500 chars): {cleaned[:500]}")
            logger.warning(f"Failed to parse {model_class.__name__}: direct={e1}, cleaned={e2}")
            raise


def safe_parse_json(content: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Safely parse JSON from LLM response, returning default on failure.

    Args:
        content: Raw LLM response content
        default: Default value to return on parse failure

    Returns:
        Parsed JSON dict or default value
    """
    if default is None:
        default = {}

    try:
        return parse_json_response(content)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse JSON: {e}")
        return default


def safe_parse_pydantic(
    content: str, model_class: type[T], default_factory: callable = None
) -> T | None:
    """Safely parse and validate JSON response into a Pydantic model.

    Args:
        content: Raw LLM response content
        model_class: Pydantic model class to validate against
        default_factory: Optional callable to create default model on failure

    Returns:
        Validated Pydantic model instance or None/default on failure
    """
    try:
        return parse_pydantic_response(content, model_class)
    except Exception as e:
        logger.warning(f"Failed to parse Pydantic model {model_class.__name__}: {e}")
        if default_factory:
            return default_factory()
        return None


# ============================================
# Robust Structured Output (LangChain 1.10)
# ============================================


class RobustStructuredOutputChain(RunnableSerializable[dict, T]):
    """A chain that reliably extracts structured output from LLM responses.

    This chain uses a multi-strategy approach to ensure structured output:
    1. First tries with_structured_output() (native JSON mode/function calling)
    2. Falls back to PydanticOutputParser with format instructions in prompt
    3. Final fallback: parse raw text with markdown stripping

    Works with OpenRouter and other providers that don't fully support JSON mode.

    Example:
        >>> class MyOutput(BaseModel):
        ...     answer: str
        ...     confidence: float
        >>> chain = RobustStructuredOutputChain(llm, MyOutput)
        >>> result = await chain.ainvoke({"question": "What is 2+2?"})
        >>> result.answer  # "4"
    """

    llm: BaseChatModel
    output_class: type[T]
    prompt_template: str | None = None
    use_tool_strategy: bool = True  # Use tool calling instead of JSON mode

    class Config:
        arbitrary_types_allowed = True

    def __init__(
        self,
        llm: BaseChatModel,
        output_class: type[T],
        prompt_template: str | None = None,
        use_tool_strategy: bool = True,
    ):
        """Initialize the chain.

        Args:
            llm: The language model to use
            output_class: Pydantic model class for structured output
            prompt_template: Optional custom prompt template
            use_tool_strategy: Use tool calling for structured output (more reliable)
        """
        super().__init__(
            llm=llm,
            output_class=output_class,
            prompt_template=prompt_template,
            use_tool_strategy=use_tool_strategy,
        )

    async def ainvoke(self, input_data: dict, config: dict | None = None) -> T:
        """Invoke the chain asynchronously with robust error handling.

        Args:
            input_data: Input dict with variables for the prompt
            config: Optional config dict

        Returns:
            Validated Pydantic model instance
        """
        # Strategy 1: Try with_structured_output (tool calling)
        if self.use_tool_strategy:
            try:
                structured_llm = self.llm.with_structured_output(
                    self.output_class,
                    method="function_calling",  # More reliable than json_schema
                )
                result = await self._invoke_with_prompt(structured_llm, input_data, config)
                if isinstance(result, self.output_class):
                    logger.debug(f"Strategy 1 (tool calling) succeeded for {self.output_class.__name__}")
                    return result
            except Exception as e:
                logger.debug(f"Strategy 1 (tool calling) failed: {e}")

        # Strategy 2: Try with PydanticOutputParser (format instructions)
        try:
            parser = PydanticOutputParser(pydantic_object=self.output_class)
            result = await self._invoke_with_parser(parser, input_data, config)
            logger.debug(f"Strategy 2 (parser) succeeded for {self.output_class.__name__}")
            return result
        except Exception as e:
            logger.debug(f"Strategy 2 (parser) failed: {e}")

        # Strategy 3: Raw invoke + manual parsing with markdown stripping
        try:
            result = await self._invoke_raw_and_parse(input_data, config)
            logger.debug(f"Strategy 3 (raw + parse) succeeded for {self.output_class.__name__}")
            return result
        except Exception as e:
            logger.error(f"All strategies failed for {self.output_class.__name__}: {e}")
            raise

    async def _invoke_with_prompt(
        self,
        llm: BaseChatModel,
        input_data: dict,
        config: dict | None,
    ) -> T:
        """Invoke with structured LLM."""
        prompt = self._build_prompt(input_data)
        return await llm.ainvoke(prompt, config=config)

    async def _invoke_with_parser(
        self,
        parser: PydanticOutputParser,
        input_data: dict,
        config: dict | None,
    ) -> T:
        """Invoke with parser format instructions."""
        format_instructions = parser.get_format_instructions()
        prompt_with_format = self._build_prompt(input_data, format_instructions)
        response = await self.llm.ainvoke(prompt_with_format, config=config)
        return parser.parse(response.content)

    async def _invoke_raw_and_parse(
        self,
        input_data: dict,
        config: dict | None,
    ) -> T:
        """Invoke raw and parse with markdown stripping."""
        # Add JSON format hint to prompt
        json_hint = f"\n\nRespond ONLY with valid JSON matching this schema:\n{self.output_class.model_json_schema()}"
        prompt = self._build_prompt(input_data, json_hint)
        response = await self.llm.ainvoke(prompt, config=config)
        return parse_pydantic_response(response.content, self.output_class)

    def _build_prompt(self, input_data: dict, extra_instructions: str = "") -> str:
        """Build the prompt from template and input data."""
        if self.prompt_template:
            base_prompt = self.prompt_template.format(**input_data)
        else:
            # Default: just use the input as is
            base_prompt = str(input_data.get("query", input_data.get("input", str(input_data))))
        return base_prompt + extra_instructions


def create_robust_structured_chain(
    llm: BaseChatModel,
    output_class: type[T],
    prompt_template: str | None = None,
) -> RobustStructuredOutputChain[T]:
    """Factory function to create a robust structured output chain.

    This is the recommended way to get structured output from LLMs when using
    OpenRouter or other providers that don't fully support JSON mode.

    Args:
        llm: The language model to use
        output_class: Pydantic model class for structured output
        prompt_template: Optional custom prompt template

    Returns:
        Configured RobustStructuredOutputChain

    Example:
        >>> from olav.core.llm import LLMFactory
        >>> from pydantic import BaseModel, Field
        >>>
        >>> class RouteDecision(BaseModel):
        ...     strategy: str = Field(description="Selected strategy")
        ...     confidence: float = Field(description="Confidence 0-1")
        >>>
        >>> llm = LLMFactory.get_chat_model()
        >>> chain = create_robust_structured_chain(llm, RouteDecision)
        >>> result = await chain.ainvoke({"query": "查询 R1 BGP 状态"})
    """
    return RobustStructuredOutputChain(
        llm=llm,
        output_class=output_class,
        prompt_template=prompt_template,
        use_tool_strategy=True,
    )


async def robust_structured_output(
    llm: BaseChatModel,
    output_class: type[T],
    prompt: str | list,
    config: dict | None = None,
) -> T:
    """One-shot function for robust structured output extraction.

    Convenience function when you don't need a reusable chain.

    Args:
        llm: The language model to use
        output_class: Pydantic model class for structured output
        prompt: The prompt string or message list
        config: Optional config dict

    Returns:
        Validated Pydantic model instance

    Example:
        >>> result = await robust_structured_output(
        ...     llm=LLMFactory.get_chat_model(),
        ...     output_class=RouteDecision,
        ...     prompt="Classify this query: 查询 R1 BGP 状态"
        ... )
    """
    # Strategy 1: Try with_structured_output (function calling)
    try:
        structured_llm = llm.with_structured_output(
            output_class,
            method="function_calling",
        )
        result = await structured_llm.ainvoke(prompt, config=config)
        if isinstance(result, output_class):
            logger.debug(f"robust_structured_output: function_calling succeeded for {output_class.__name__}")
            return result
    except Exception as e:
        logger.debug(f"robust_structured_output: function_calling failed: {e}")

    # Strategy 2: Try with PydanticOutputParser
    try:
        parser = PydanticOutputParser(pydantic_object=output_class)
        format_instructions = parser.get_format_instructions()
        if isinstance(prompt, str):
            full_prompt = f"{prompt}\n\n{format_instructions}"
        else:
            # Add format instructions to last message
            full_prompt = prompt.copy()
            if full_prompt and hasattr(full_prompt[-1], "content"):
                full_prompt[-1].content += f"\n\n{format_instructions}"
            else:
                full_prompt.append({"role": "user", "content": format_instructions})

        response = await llm.ainvoke(full_prompt, config=config)
        return parser.parse(response.content)
    except Exception as e:
        logger.debug(f"robust_structured_output: parser failed: {e}")

    # Strategy 3: Raw invoke + manual parsing
    json_schema = output_class.model_json_schema()
    json_hint = f"\n\nRespond ONLY with valid JSON (no markdown). Schema:\n{json.dumps(json_schema, indent=2)}"
    if isinstance(prompt, str):
        full_prompt = prompt + json_hint
    else:
        full_prompt = prompt.copy()
        if full_prompt and hasattr(full_prompt[-1], "content"):
            full_prompt[-1].content += json_hint
        else:
            full_prompt.append({"role": "user", "content": json_hint})

    response = await llm.ainvoke(full_prompt, config=config)
    return parse_pydantic_response(response.content, output_class)
