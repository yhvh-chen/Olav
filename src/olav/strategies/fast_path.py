"""
Fast Path Strategy - Single-shot function calling for simple queries.

This strategy bypasses agent loops and multi-step reasoning for queries
that can be answered with a single tool invocation. Optimizes for:
- Low latency (< 2 seconds)
- High accuracy (no iterative hallucination)
- Simple queries (status checks, single-device lookups)

Execution Flow:
1. Parameter Extraction: LLM extracts structured params from query
2. Tool Selection: Priority queue (SuzieQ > NetBox > CLI)
3. Single Invocation: Call tool once, no loops (with optional caching)
4. Strict Formatting: Force LLM to use tool output only (no speculation)

Example Queries:
- "查询 R1 的 BGP 邻居状态" → suzieq_query(table="bgp", hostname="R1")
- "Switch-A 的管理 IP 是什么？" → netbox_api_call(endpoint="/dcim/devices/", name="Switch-A")
- "检查接口 Gi0/1 状态" → suzieq_query(table="interfaces", ifname="Gi0/1")

Key Difference from Agent Loop:
- Agent: Query → Think → Tool → Think → Tool → Think → Answer (slow, may drift)
- Fast Path: Query → Extract Params → Tool → Format Answer (fast, deterministic)

Caching (Phase B.2):
- Tool results cached using FilesystemMiddleware
- Cache key: SHA256 hash of (tool_name + parameters)
- Reduces duplicate LLM calls by 10-20%
- Cache TTL: 300 seconds (configurable)
"""

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Literal, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from olav.core.memory_writer import MemoryWriter
from olav.core.middleware import FilesystemMiddleware
from olav.tools.base import ToolOutput, ToolRegistry
from olav.tools.opensearch_tool_refactored import EpisodicMemoryTool

logger = logging.getLogger(__name__)


class ParameterExtraction(BaseModel):
    """
    Structured parameters extracted from user query.
    
    LLM converts natural language to tool-compatible parameters.
    """
    tool: Literal["suzieq_query", "netbox_api_call", "cli_tool", "netconf_tool"]
    parameters: Dict[str, Any] = Field(description="Tool-specific parameters")
    confidence: float = Field(
        description="Confidence that Fast Path is appropriate (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    reasoning: str = Field(description="Why this tool and parameters were chosen")


class FormattedAnswer(BaseModel):
    """
    Structured answer based strictly on tool output.
    
    LLM formats tool data into human-readable response without speculation.
    """
    answer: str = Field(description="Human-readable answer derived from tool data")
    data_used: List[str] = Field(
        description="List of fields from tool output used in answer"
    )
    confidence: float = Field(
        description="Confidence in answer accuracy (0.0-1.0)",
        ge=0.0,
        le=1.0
    )


class FastPathStrategy:
    """
    Fast Path execution strategy for simple, single-tool queries.
    
    Implements a three-step process:
    1. Extract parameters from natural language
    2. Execute single tool call (priority: SuzieQ > NetBox > CLI) with caching
    3. Format answer in strict mode (no hallucination beyond tool data)
    
    Attributes:
        llm: Language model for parameter extraction and formatting
        tool_registry: Registry of available tools
        priority_order: Default tool selection priority
        confidence_threshold: Minimum confidence to use Fast Path (default: 0.7)
        filesystem: FilesystemMiddleware for tool result caching (optional)
        cache_ttl: Cache time-to-live in seconds (default: 300)
        enable_cache: Whether to enable tool result caching (default: True)
    """
    
    def __init__(
        self,
        llm: BaseChatModel,
        tool_registry: "ToolRegistry",
        confidence_threshold: float = 0.7,
        memory_writer: MemoryWriter | None = None,
        enable_memory_rag: bool = True,
        episodic_memory_tool: EpisodicMemoryTool | None = None,
        filesystem: FilesystemMiddleware | None = None,
        enable_cache: bool = True,
        cache_ttl: int = 300,
    ):
        """
        Initialize Fast Path strategy.
        
        Args:
            llm: Language model (should support JSON mode)
            tool_registry: ToolRegistry instance (required for tool discovery)
            confidence_threshold: Min confidence to proceed (default: 0.7)
            memory_writer: MemoryWriter for capturing successes (optional)
            enable_memory_rag: Enable episodic memory RAG optimization (default: True)
            episodic_memory_tool: Tool for searching historical patterns (optional)
            filesystem: FilesystemMiddleware for caching (optional, auto-created if None)
            enable_cache: Enable tool result caching (default: True)
            cache_ttl: Cache time-to-live in seconds (default: 300)
        """
        self.llm = llm
        self.tool_registry = tool_registry
        self.confidence_threshold = confidence_threshold
        self.memory_writer = memory_writer or MemoryWriter()
        self.enable_memory_rag = enable_memory_rag
        self.episodic_memory_tool = episodic_memory_tool or EpisodicMemoryTool()
        self.priority_order = ["suzieq_query", "netbox_api_call", "cli_tool", "netconf_tool"]
        
        # Caching configuration (Phase B.2)
        self.enable_cache = enable_cache
        self.cache_ttl = cache_ttl
        self.filesystem = filesystem  # Will be created on-demand if None
        
        # Validate tool registry
        if not self.tool_registry:
            raise ValueError("ToolRegistry is required for FastPathStrategy")
        
        logger.info(
            f"FastPathStrategy initialized with confidence threshold: {confidence_threshold}, "
            f"available tools: {len(self.tool_registry.list_tools())}, "
            f"caching: {enable_cache} (TTL: {cache_ttl}s)"
        )
    
    async def execute(
        self,
        user_query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute Fast Path strategy for a user query.
        
        Args:
            user_query: Natural language query
            context: Optional context (device list, network topology, etc.)
            
        Returns:
            Dict with 'success', 'answer', 'tool_output', 'metadata'
        """
        try:
            # Step 0: Search episodic memory (RAG optimization)
            memory_pattern = None
            if self.enable_memory_rag:
                memory_pattern = await self._search_episodic_memory(user_query)
            
            # Step 1: Extract parameters (use memory pattern if available)
            if memory_pattern and memory_pattern.get("confidence", 0) > 0.8:
                # Use historical pattern directly
                extraction = ParameterExtraction(
                    tool=memory_pattern["tool"],
                    parameters=memory_pattern["parameters"],
                    confidence=memory_pattern["confidence"],
                    reasoning=f"From episodic memory: {memory_pattern.get('intent', 'historical pattern')}"
                )
                logger.info(
                    f"Using episodic memory pattern: {memory_pattern['tool']} "
                    f"(confidence: {memory_pattern['confidence']:.2f})"
                )
            else:
                # Fallback to LLM parameter extraction
                extraction = await self._extract_parameters(user_query, context)
            
            # Check confidence threshold
            if extraction.confidence < self.confidence_threshold:
                logger.info(
                    f"Fast Path confidence {extraction.confidence:.2f} below threshold "
                    f"{self.confidence_threshold}, falling back to standard workflow"
                )
                return {
                    "success": False,
                    "reason": "low_confidence",
                    "confidence": extraction.confidence,
                    "fallback_required": True
                }
            
            logger.info(
                f"Fast Path selected tool: {extraction.tool} "
                f"(confidence: {extraction.confidence:.2f})"
            )
            
            # Step 2: Execute tool
            tool_output = await self._execute_tool(extraction.tool, extraction.parameters)
            
            if tool_output.error:
                logger.error(f"Tool execution failed: {tool_output.error}")
                return {
                    "success": False,
                    "reason": "tool_error",
                    "error": tool_output.error,
                    "tool_output": tool_output
                }
            
            # Step 3: Format answer (strict mode)
            formatted = await self._format_answer(user_query, tool_output, extraction)
            
            # Step 4: Capture success to episodic memory
            execution_time_ms = tool_output.metadata.get("elapsed_ms", 0)
            await self.memory_writer.capture_success(
                intent=user_query,
                tool_used=extraction.tool,
                parameters=extraction.parameters,
                tool_output=tool_output,
                strategy_used="fast_path",
                execution_time_ms=execution_time_ms,
            )
            
            return {
                "success": True,
                "answer": formatted.answer,
                "tool_output": tool_output,
                "metadata": {
                    "strategy": "fast_path",
                    "tool": extraction.tool,
                    "confidence": extraction.confidence,
                    "data_fields_used": formatted.data_used,
                    "answer_confidence": formatted.confidence
                }
            }
        
        except Exception as e:
            logger.exception(f"Fast Path execution failed: {e}")
            return {
                "success": False,
                "reason": "exception",
                "error": str(e),
                "fallback_required": True
            }
    
    async def _extract_parameters(
        self,
        user_query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ParameterExtraction:
        """
        Extract structured parameters from natural language query.
        
        Args:
            user_query: User's query
            context: Optional context for parameter extraction
            
        Returns:
            ParameterExtraction with tool and parameters
        """
        tool_descriptions = {
            "suzieq_query": "Query SuzieQ Parquet database (network state: BGP, OSPF, interfaces, routes). Fast, read-only. Parameters: table (bgp|ospf|interfaces|routes|...), hostname, namespace, etc.",
            "netbox_api_call": "Query NetBox SSOT (device inventory, IPs, sites, racks). Parameters: endpoint (/dcim/devices/), filters (name, role, site).",
            "cli_tool": "Execute CLI command on device (fallback, slower). Parameters: device, command.",
            "netconf_tool": "Execute NETCONF get-config (OpenConfig paths). Parameters: device, xpath."
        }
        
        tools_desc = "\n".join([f"- **{k}**: {v}" for k, v in tool_descriptions.items()])
        
        context_str = ""
        if context:
            context_str = f"\n\n## 可用上下文\n{context}"
        
        prompt = f"""你是 OLAV 参数提取专家。从用户查询中提取结构化参数，用于单次工具调用（Fast Path）。

## 用户查询
{user_query}
{context_str}

## 可用工具（优先级顺序）
{tools_desc}

## 提取要求
1. 选择最合适的工具（优先 SuzieQ，其次 NetBox，最后 CLI/NETCONF）
2. 提取工具所需的精确参数（如 table, hostname, endpoint 等）
3. 评估该查询是否适合 Fast Path（简单查询 confidence 高，复杂诊断 confidence 低）
4. 如果需要多次调用或复杂推理，降低 confidence

返回 JSON：
{{{{
    "tool": "suzieq_query",
    "parameters": {{"table": "bgp", "hostname": "R1"}},
    "confidence": 0.95,
    "reasoning": "简单的 BGP 状态查询，SuzieQ 可直接回答"
}}}}
"""
        
        response = await self.llm.ainvoke([SystemMessage(content=prompt)])
        
        try:
            extraction = ParameterExtraction.model_validate_json(response.content)
        except Exception as e:
            logger.error(f"Failed to parse parameter extraction: {e}")
            # Fallback extraction
            extraction = ParameterExtraction(
                tool="suzieq_query",
                parameters={},
                confidence=0.3,
                reasoning=f"Parse error: {e}"
            )
        
        logger.debug(f"Extracted: {extraction.tool} with params {extraction.parameters}")
        return extraction
    
    async def _execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> ToolOutput:
        """
        Execute the selected tool with extracted parameters.
        
        Implements caching layer (Phase B.2):
        1. Check cache for recent result (cache_key = hash(tool + params))
        2. If cache hit: deserialize and return (no tool execution)
        3. If cache miss: execute tool, serialize result, cache, return
        
        Args:
            tool_name: Tool identifier (must be registered in ToolRegistry)
            parameters: Tool parameters
            
        Returns:
            ToolOutput from tool execution or cache
        """
        # Step 1: Check cache (if enabled)
        if self.enable_cache:
            cache_result = await self._check_cache(tool_name, parameters)
            if cache_result:
                logger.info(f"Cache HIT for {tool_name} (params: {parameters})")
                return cache_result
            else:
                logger.debug(f"Cache MISS for {tool_name} (params: {parameters})")
        
        # Step 2: Validate tool registry
        if not self.tool_registry:
            logger.error("ToolRegistry not configured in FastPathStrategy")
            return ToolOutput(
                source=tool_name,
                device="unknown",
                data=[],
                error="ToolRegistry not configured - cannot execute tools"
            )
        
        # Step 3: Get tool from registry
        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            logger.error(f"Tool '{tool_name}' not found in ToolRegistry")
            available_tools = [t.name for t in self.tool_registry.list_tools()]
            return ToolOutput(
                source=tool_name,
                device="unknown",
                data=[],
                error=f"Tool '{tool_name}' not registered. Available: {', '.join(available_tools)}"
            )
        
        # Step 4: Execute tool
        logger.debug(f"Executing tool '{tool_name}' with parameters: {parameters}")
        start_time = time.time()
        tool_output = await tool.execute(**parameters)
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        # Add execution time to metadata
        if tool_output.metadata is None:
            tool_output.metadata = {}
        tool_output.metadata["elapsed_ms"] = elapsed_ms
        
        # Step 5: Cache result (if enabled and successful)
        if self.enable_cache and not tool_output.error:
            await self._write_cache(tool_name, parameters, tool_output)
        
        return tool_output
    
    def _get_cache_key(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """
        Generate cache key from tool name and parameters.
        
        Uses SHA256 hash of canonical JSON representation for consistency.
        
        Args:
            tool_name: Tool identifier
            parameters: Tool parameters (will be sorted for consistency)
        
        Returns:
            Cache key (e.g., "tool_results/suzieq_query_abc123def456.json")
        
        Examples:
            >>> strategy._get_cache_key("suzieq_query", {"table": "bgp", "hostname": "R1"})
            "tool_results/suzieq_query_3f2a1b9c8d7e6f5a.json"
        """
        # Create canonical JSON (sorted keys)
        canonical = json.dumps(
            {"tool": tool_name, "params": parameters},
            sort_keys=True,
            ensure_ascii=False
        )
        
        # Hash to get cache key
        hash_obj = hashlib.sha256(canonical.encode("utf-8"))
        cache_hash = hash_obj.hexdigest()[:16]  # First 16 chars
        
        return f"tool_results/{tool_name}_{cache_hash}.json"
    
    async def _check_cache(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> ToolOutput | None:
        """
        Check cache for existing tool result.
        
        Args:
            tool_name: Tool identifier
            parameters: Tool parameters
        
        Returns:
            Cached ToolOutput if exists and not expired, None otherwise
        """
        try:
            # Lazy-initialize filesystem if needed
            if self.filesystem is None:
                from langgraph.checkpoint.memory import MemorySaver
                checkpointer = MemorySaver()
                self.filesystem = FilesystemMiddleware(
                    checkpointer=checkpointer,
                    workspace_root="./data/cache",
                    audit_enabled=False,
                    hitl_enabled=False
                )
            
            cache_key = self._get_cache_key(tool_name, parameters)
            
            # Read from cache
            cached_content = await self.filesystem.read_file(cache_key)
            if not cached_content or cached_content == "System reminder: File exists but has empty contents":
                return None
            
            # Deserialize cached result
            cached_data = json.loads(cached_content)
            
            # Check cache expiration (TTL)
            cache_time = cached_data.get("cached_at", 0)
            age_seconds = time.time() - cache_time
            
            if age_seconds > self.cache_ttl:
                logger.debug(f"Cache expired for {tool_name} (age: {age_seconds:.1f}s > TTL: {self.cache_ttl}s)")
                # Clean up expired cache
                await self.filesystem.delete_file(cache_key)
                return None
            
            # Deserialize ToolOutput
            tool_output_data = cached_data.get("tool_output", {})
            tool_output = ToolOutput(
                source=tool_output_data.get("source", tool_name),
                device=tool_output_data.get("device", "unknown"),
                data=tool_output_data.get("data", []),
                error=tool_output_data.get("error"),
                metadata=tool_output_data.get("metadata", {})
            )
            
            # Add cache metadata
            tool_output.metadata["cache_hit"] = True
            tool_output.metadata["cache_age_seconds"] = age_seconds
            
            return tool_output
        
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.warning(f"Cache read error for {tool_name}: {e}")
            return None
    
    async def _write_cache(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        tool_output: ToolOutput
    ) -> None:
        """
        Write tool result to cache.
        
        Args:
            tool_name: Tool identifier
            parameters: Tool parameters
            tool_output: Tool execution result
        """
        try:
            # Lazy-initialize filesystem if needed
            if self.filesystem is None:
                from langgraph.checkpoint.memory import MemorySaver
                checkpointer = MemorySaver()
                self.filesystem = FilesystemMiddleware(
                    checkpointer=checkpointer,
                    workspace_root="./data/cache",
                    audit_enabled=False,
                    hitl_enabled=False
                )
            
            cache_key = self._get_cache_key(tool_name, parameters)
            
            # Serialize ToolOutput
            cache_data = {
                "tool": tool_name,
                "parameters": parameters,
                "cached_at": time.time(),
                "cache_ttl": self.cache_ttl,
                "tool_output": {
                    "source": tool_output.source,
                    "device": tool_output.device,
                    "data": tool_output.data,
                    "error": tool_output.error,
                    "metadata": tool_output.metadata
                }
            }
            
            # Write to cache
            await self.filesystem.write_file(
                cache_key,
                json.dumps(cache_data, ensure_ascii=False, indent=2)
            )
            
            logger.debug(f"Cached result for {tool_name} (key: {cache_key}, TTL: {self.cache_ttl}s)")
        
        except Exception as e:
            logger.warning(f"Cache write error for {tool_name}: {e}")
    
    async def _format_answer(
        self,
        user_query: str,
        tool_output: ToolOutput,
        extraction: ParameterExtraction
    ) -> FormattedAnswer:
        """
        Format tool output into human-readable answer (strict mode).
        
        LLM is forced to only use data from tool_output, no speculation.
        
        Args:
            user_query: Original user query
            tool_output: Tool execution result
            extraction: Parameter extraction context
            
        Returns:
            FormattedAnswer with human-readable text
        """
        import json
        
        # Serialize tool data for LLM
        data_json = json.dumps(tool_output.data, ensure_ascii=False, indent=2)
        
        prompt = f"""你是 OLAV 答案格式化专家。基于工具返回的数据，回答用户问题。

## 严格规则
1. **仅使用工具数据**：答案必须完全基于下方的工具输出，不得推测或添加未验证信息
2. **引用字段**：在 `data_used` 中列出使用的数据字段
3. **承认限制**：如果数据不足以完全回答问题，明确说明

## 用户问题
{user_query}

## 工具输出
来源: {tool_output.source}
设备: {tool_output.device}
数据:
{data_json}

元数据: {tool_output.metadata}

## 格式要求
返回 JSON：
{{{{
    "answer": "基于数据的简洁答案（2-3 句话）",
    "data_used": ["使用的字段名列表"],
    "confidence": 0.95
}}}}
"""
        
        response = await self.llm.ainvoke([SystemMessage(content=prompt)])
        
        try:
            formatted = FormattedAnswer.model_validate_json(response.content)
        except Exception as e:
            logger.error(f"Failed to parse formatted answer: {e}")
            # Fallback formatting
            formatted = FormattedAnswer(
                answer=f"工具返回了 {len(tool_output.data)} 条记录。",
                data_used=[],
                confidence=0.5
            )
        
        return formatted
    
    def is_suitable(self, user_query: str) -> bool:
        """
        Quick heuristic to check if query is suitable for Fast Path.
        
        Args:
            user_query: User's query
            
        Returns:
            True if likely suitable, False otherwise
        """
        # Fast Path suitable for:
        # - Single device queries
        # - Status checks
        # - Simple lookups
        
        # Not suitable for:
        # - "为什么" (why) questions
        # - Multi-step diagnostics
        # - Batch operations
        
        unsuitable_patterns = [
            "为什么", "why", "诊断", "diagnose", "排查", "troubleshoot",
            "所有设备", "all device", "批量", "batch", "审计", "audit"
        ]
        
        query_lower = user_query.lower()
        for pattern in unsuitable_patterns:
            if pattern in query_lower:
                return False
        
        return True
    
    async def _search_episodic_memory(
        self,
        user_query: str,
        max_results: int = 3,
        confidence_threshold: float = 0.8,
    ) -> Optional[Dict[str, Any]]:
        """
        Search episodic memory for historical success patterns.
        
        This implements RAG optimization: if we've successfully handled
        a similar query before, reuse the same tool + parameters.
        
        Args:
            user_query: User's natural language query
            max_results: Max historical patterns to retrieve
            confidence_threshold: Min confidence to use memory pattern
            
        Returns:
            Dict with tool, parameters, confidence if match found, else None
            
        Example:
            >>> pattern = await strategy._search_episodic_memory("查询 R1 BGP 状态")
            >>> pattern
            {
                "tool": "suzieq_query",
                "parameters": {"table": "bgp", "hostname": "R1", "method": "get"},
                "confidence": 0.95,
                "intent": "查询 R1 BGP 状态"
            }
        """
        try:
            # Search episodic memory
            result = await self.episodic_memory_tool.execute(
                intent=user_query,
                max_results=max_results,
                only_successful=True,
            )
            
            if result.error or not result.data:
                logger.debug(f"No episodic memory patterns found for: {user_query}")
                return None
            
            # Get best match (first result, highest relevance)
            best_match = result.data[0]
            
            # Calculate semantic similarity confidence (simple heuristic)
            # In production, use embedding similarity
            historical_intent = best_match.get("intent", "")
            query_words = set(user_query.lower().split())
            historical_words = set(historical_intent.lower().split())
            
            # Jaccard similarity
            if query_words and historical_words:
                intersection = query_words & historical_words
                union = query_words | historical_words
                similarity = len(intersection) / len(union)
            else:
                similarity = 0.0
            
            # Boost confidence if exact match
            if user_query.lower() == historical_intent.lower():
                similarity = 1.0
            
            logger.info(
                f"Found episodic memory pattern: '{historical_intent}' "
                f"(similarity: {similarity:.2f})"
            )
            
            # Only use if confidence above threshold
            if similarity < confidence_threshold:
                logger.debug(
                    f"Similarity {similarity:.2f} below threshold {confidence_threshold}, "
                    "falling back to LLM extraction"
                )
                return None
            
            # Extract tool and parameters from memory
            tool_used = best_match.get("tool_used")
            parameters = best_match.get("parameters", {})
            
            if not tool_used or not parameters:
                logger.warning("Episodic memory pattern missing tool or parameters")
                return None
            
            return {
                "tool": tool_used,
                "parameters": parameters,
                "confidence": similarity,
                "intent": historical_intent,
                "execution_time_ms": best_match.get("execution_time_ms", 0),
            }
        
        except Exception as e:
            logger.error(f"Episodic memory search failed: {e}")
            return None
