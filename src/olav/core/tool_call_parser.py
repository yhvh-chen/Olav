"""Tool call parser for fixing OpenRouter/DeepSeek response format issues."""

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

logger = logging.getLogger(__name__)


def fix_tool_call_args(message: AIMessage) -> AIMessage:
    """Fix tool_calls.args if they are JSON strings instead of dicts.

    OpenRouter/DeepSeek sometimes returns tool_calls with args as JSON strings,
    which causes Pydantic validation errors in LangChain.

    Args:
        message: AI message potentially with malformed tool calls

    Returns:
        Fixed AI message with tool_calls.args as dicts
    """
    if not hasattr(message, "tool_calls") or not message.tool_calls:
        return message

    fixed_tool_calls = []
    needs_fix = False

    for tool_call in message.tool_calls:
        # Check if args is a string (malformed)
        if isinstance(tool_call.get("args"), str):
            needs_fix = True
            try:
                # Parse JSON string to dict
                parsed_args = json.loads(tool_call["args"])
                fixed_call = {**tool_call, "args": parsed_args}
                fixed_tool_calls.append(fixed_call)
                logger.debug(f"Fixed tool call args for {tool_call.get('name')}")
            except json.JSONDecodeError as e:
                logger.warning(
                    f"Failed to parse tool call args as JSON: {tool_call.get('args')}, error: {e}"
                )
                # Keep original if parsing fails
                fixed_tool_calls.append(tool_call)
        else:
            # Args is already a dict, no fix needed
            fixed_tool_calls.append(tool_call)

    if needs_fix:
        # Create new message with fixed tool calls
        return AIMessage(
            content=message.content,
            tool_calls=fixed_tool_calls,
            additional_kwargs=message.additional_kwargs,
            response_metadata=message.response_metadata,
            id=message.id,
        )

    return message


def create_tool_call_fixer() -> RunnableLambda:
    """Create a runnable that fixes tool call formatting issues.

    Returns:
        Runnable that can be chained with LLM
    """
    return RunnableLambda(fix_tool_call_args)


def fix_raw_tool_calls(raw_response: dict[str, Any]) -> dict[str, Any]:
    """Fix tool calls in raw OpenAI API response before LangChain processing.

    This is a pre-processing step that should be applied to the raw API response
    before LangChain converts it to messages.

    Args:
        raw_response: Raw response from OpenAI-compatible API

    Returns:
        Fixed response with tool_calls.function.arguments as dicts
    """
    if "choices" not in raw_response:
        return raw_response

    for choice in raw_response["choices"]:
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls", [])

        for tool_call in tool_calls:
            function = tool_call.get("function", {})
            arguments = function.get("arguments")

            # If arguments is a string, parse it
            if isinstance(arguments, str):
                try:
                    function["arguments"] = json.loads(arguments)
                    logger.debug(f"Pre-parsed tool call arguments for {function.get('name')}")
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to pre-parse arguments: {arguments}, error: {e}")

    return raw_response
