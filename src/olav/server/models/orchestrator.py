from pydantic import BaseModel
from typing import Literal, Any, Dict

class SimpleMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class InvokeInput(BaseModel):
    messages: list[SimpleMessage]

class InvokeConfig(BaseModel):
    configurable: dict[str, Any] | None = None

class WorkflowInvokePayload(BaseModel):
    input: InvokeInput
    config: InvokeConfig | None = None

class StreamEventType:
    """Stream event types for clients."""
    TOKEN = "token"           # Final response token
    THINKING = "thinking"     # LLM reasoning process
    TOOL_START = "tool_start" # Tool invocation started
    TOOL_END = "tool_end"     # Tool invocation completed
    INTERRUPT = "interrupt"   # HITL approval required
    ERROR = "error"           # Error occurred
    DONE = "done"             # Stream completed
