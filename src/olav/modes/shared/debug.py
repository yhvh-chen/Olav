"""Debug Mode - Comprehensive debugging and instrumentation.

Provides detailed output for:
- LLM calls (prompt, response, tokens, duration)
- Tool calls (input, output, duration)
- Graph states (LangGraph node transitions)
- Stream chunks (streaming latency)

Usage:
    from olav.modes.shared.debug import DebugContext
    
    async with DebugContext(enabled=True) as debug:
        result = await workflow.run(query)
        
    # Access debug output
    print(debug.output.to_json())
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class LLMCallDetail:
    """LLM call detailed information."""
    
    call_id: str
    model: str = ""
    prompt: str = ""
    response: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    temperature: float = 0.0
    
    # Thinking mode analysis (for Ollama qwen3/deepseek-r1)
    thinking_content: str | None = None
    thinking_tokens: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ToolCallDetail:
    """Tool call detailed information."""
    
    tool_name: str
    input_args: dict = field(default_factory=dict)
    output: str = ""
    output_size: int = 0
    duration_ms: float = 0.0
    success: bool = True
    error: str | None = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GraphStateSnapshot:
    """LangGraph state snapshot."""
    
    node: str
    state: dict = field(default_factory=dict)
    timestamp: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StreamChunk:
    """Streaming chunk information."""
    
    chunk_id: int
    content: str
    timestamp: str
    latency_from_start_ms: float
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DebugOutput:
    """Complete debug output structure."""
    
    # Basic information
    query: str = ""
    mode: str = ""  # standard/expert/inspection
    timestamp: str = ""
    duration_ms: float = 0.0
    
    # LLM calls
    llm_calls: list[LLMCallDetail] = field(default_factory=list)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    
    # Tool calls
    tool_calls: list[ToolCallDetail] = field(default_factory=list)
    
    # Graph states
    graph_states: list[GraphStateSnapshot] = field(default_factory=list)
    transitions: list[str] = field(default_factory=list)  # ["node1 -> node2"]
    
    # Stream chunks
    stream_chunks: list[StreamChunk] = field(default_factory=list)
    stream_latency_ms: float = 0.0  # First chunk latency
    
    # Time breakdown
    time_breakdown: dict[str, float] = field(default_factory=dict)
    
    def add_llm_call(self, call: LLMCallDetail) -> None:
        """Add LLM call and update totals."""
        self.llm_calls.append(call)
        self.total_prompt_tokens += call.prompt_tokens
        self.total_completion_tokens += call.completion_tokens
        self.total_tokens += call.total_tokens
    
    def add_tool_call(self, call: ToolCallDetail) -> None:
        """Add tool call."""
        self.tool_calls.append(call)
    
    def add_graph_state(self, node: str, state: dict) -> None:
        """Add graph state snapshot."""
        snapshot = GraphStateSnapshot(
            node=node,
            state=state,
            timestamp=datetime.now().isoformat(),
        )
        
        # Track transitions
        if self.graph_states:
            prev_node = self.graph_states[-1].node
            self.transitions.append(f"{prev_node} -> {node}")
        
        self.graph_states.append(snapshot)
    
    def add_stream_chunk(self, content: str, start_time: float) -> None:
        """Add stream chunk."""
        chunk = StreamChunk(
            chunk_id=len(self.stream_chunks),
            content=content,
            timestamp=datetime.now().isoformat(),
            latency_from_start_ms=(time.perf_counter() - start_time) * 1000,
        )
        
        # Track first chunk latency
        if len(self.stream_chunks) == 0:
            self.stream_latency_ms = chunk.latency_from_start_ms
        
        self.stream_chunks.append(chunk)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "query": self.query,
            "mode": self.mode,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "llm_calls": [c.to_dict() for c in self.llm_calls],
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "tool_calls": [c.to_dict() for c in self.tool_calls],
            "graph_states": [s.to_dict() for s in self.graph_states],
            "transitions": self.transitions,
            "stream_chunks": [c.to_dict() for c in self.stream_chunks],
            "stream_latency_ms": self.stream_latency_ms,
            "time_breakdown": self.time_breakdown,
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
    
    def save(self, path: Path | str) -> None:
        """Save debug output to file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        logger.info(f"Debug output saved to: {path}")
    
    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"=== Debug Summary ===",
            f"Query: {self.query[:50]}...",
            f"Mode: {self.mode}",
            f"Duration: {self.duration_ms:.2f}ms",
            f"",
            f"LLM Calls: {len(self.llm_calls)}",
            f"  Total Tokens: {self.total_tokens} ({self.total_prompt_tokens}p + {self.total_completion_tokens}c)",
        ]
        
        for call in self.llm_calls:
            lines.append(f"  - {call.call_id}: {call.prompt_tokens}+{call.completion_tokens} tokens, {call.duration_ms:.0f}ms")
        
        lines.extend([
            f"",
            f"Tool Calls: {len(self.tool_calls)}",
        ])
        
        for call in self.tool_calls:
            status = "✓" if call.success else "✗"
            lines.append(f"  - {status} {call.tool_name}: {call.duration_ms:.0f}ms")
        
        if self.transitions:
            lines.extend([
                f"",
                f"Graph Flow: {' → '.join([t.split(' -> ')[0] for t in self.transitions] + [self.transitions[-1].split(' -> ')[1]])}",
            ])
        
        if self.stream_latency_ms > 0:
            lines.extend([
                f"",
                f"Stream: {len(self.stream_chunks)} chunks, first chunk at {self.stream_latency_ms:.0f}ms",
            ])
        
        return "\n".join(lines)


class DebugContext:
    """Debug context manager for instrumentation.
    
    Usage:
        async with DebugContext(enabled=True) as debug:
            result = await workflow.run(query)
        
        print(debug.output.summary())
        debug.output.save("debug_output.json")
    """
    
    def __init__(
        self,
        enabled: bool = False,
        query: str = "",
        mode: str = "standard",
        output_path: Path | str | None = None,
    ) -> None:
        """Initialize debug context.
        
        Args:
            enabled: Whether debug mode is active.
            query: User query being processed.
            mode: Execution mode (standard/expert/inspection).
            output_path: Optional path to save debug output.
        """
        self.enabled = enabled
        self.output = DebugOutput(
            query=query,
            mode=mode,
            timestamp=datetime.now().isoformat(),
        )
        self.output_path = Path(output_path) if output_path else None
        self._start_time: float | None = None
        self._step_times: dict[str, float] = {}
    
    def __enter__(self) -> "DebugContext":
        if self.enabled:
            self._start_time = time.perf_counter()
            logger.info(f"Debug mode enabled for: {self.output.query[:50]}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self.enabled and self._start_time:
            self.output.duration_ms = (time.perf_counter() - self._start_time) * 1000
            
            if self.output_path:
                self.output.save(self.output_path)
            
            logger.info(f"Debug completed: {self.output.duration_ms:.0f}ms, {len(self.output.llm_calls)} LLM calls")
        
        return False
    
    async def __aenter__(self) -> "DebugContext":
        return self.__enter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        return self.__exit__(exc_type, exc_val, exc_tb)
    
    def start_step(self, step_name: str) -> None:
        """Start timing a step."""
        if self.enabled:
            self._step_times[step_name] = time.perf_counter()
    
    def end_step(self, step_name: str) -> float:
        """End timing a step and record duration."""
        if self.enabled and step_name in self._step_times:
            duration = (time.perf_counter() - self._step_times[step_name]) * 1000
            self.output.time_breakdown[step_name] = duration
            del self._step_times[step_name]
            return duration
        return 0.0
    
    def log_llm_call(
        self,
        prompt: str,
        response: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        duration_ms: float = 0.0,
        model: str = "",
        thinking_content: str | None = None,
    ) -> None:
        """Log an LLM call."""
        if not self.enabled:
            return
        
        call_id = f"llm-{len(self.output.llm_calls):03d}"
        call = LLMCallDetail(
            call_id=call_id,
            model=model,
            prompt=prompt,
            response=response,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            duration_ms=duration_ms,
            thinking_content=thinking_content,
            thinking_tokens=len(thinking_content.split()) if thinking_content else 0,
        )
        self.output.add_llm_call(call)
    
    def log_tool_call(
        self,
        tool_name: str,
        input_args: dict,
        output: str,
        duration_ms: float,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Log a tool call."""
        if not self.enabled:
            return
        
        call = ToolCallDetail(
            tool_name=tool_name,
            input_args=input_args,
            output=output[:1000],  # Truncate large outputs
            output_size=len(output),
            duration_ms=duration_ms,
            success=success,
            error=error,
        )
        self.output.add_tool_call(call)
    
    def log_graph_state(self, node: str, state: dict) -> None:
        """Log a graph state transition."""
        if not self.enabled:
            return
        
        # Sanitize state (remove non-serializable objects)
        safe_state = {}
        for k, v in state.items():
            try:
                json.dumps(v)
                safe_state[k] = v
            except (TypeError, ValueError):
                safe_state[k] = str(type(v))
        
        self.output.add_graph_state(node, safe_state)
    
    def log_stream_chunk(self, content: str) -> None:
        """Log a stream chunk."""
        if not self.enabled or not self._start_time:
            return
        
        self.output.add_stream_chunk(content, self._start_time)


# Global debug context (thread-local would be better in production)
_current_debug_context: DebugContext | None = None


def get_debug_context() -> DebugContext | None:
    """Get current debug context."""
    return _current_debug_context


def set_debug_context(ctx: DebugContext | None) -> None:
    """Set current debug context."""
    global _current_debug_context
    _current_debug_context = ctx
