"""
Unit tests for FastPathStrategy fallback mechanism.

Tests the Schema-Aware Router pattern that triggers CLI/NETCONF
fallback when SuzieQ/OpenConfig schemas don't match the query.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from olav.strategies.fast_path import (
    FastPathStrategy,
    FALLBACK_TOOL_CHAIN,
    INTENT_PATTERNS_FALLBACK,
)


class TestIntentPatternsExtension:
    """Test that CLI keywords are properly extended."""

    def test_syslog_keywords_in_cli_patterns(self):
        """Syslog-related keywords should route to CLI."""
        cli_patterns = INTENT_PATTERNS_FALLBACK.get("cli", [])
        syslog_keywords = ["syslog", "logging", "日志服务", "日志配置"]
        for kw in syslog_keywords:
            assert kw in cli_patterns, f"Missing CLI keyword: {kw}"

    def test_ntp_keywords_in_cli_patterns(self):
        """NTP-related keywords should route to CLI."""
        cli_patterns = INTENT_PATTERNS_FALLBACK.get("cli", [])
        ntp_keywords = ["ntp", "时间同步", "clock"]
        for kw in ntp_keywords:
            assert kw in cli_patterns, f"Missing CLI keyword: {kw}"

    def test_snmp_keywords_in_cli_patterns(self):
        """SNMP-related keywords should route to CLI."""
        cli_patterns = INTENT_PATTERNS_FALLBACK.get("cli", [])
        snmp_keywords = ["snmp", "snmp-server", "监控配置"]
        for kw in snmp_keywords:
            assert kw in cli_patterns, f"Missing CLI keyword: {kw}"

    def test_security_keywords_in_cli_patterns(self):
        """Security-related keywords should route to CLI."""
        cli_patterns = INTENT_PATTERNS_FALLBACK.get("cli", [])
        security_keywords = ["aaa", "tacacs", "radius", "认证"]
        for kw in security_keywords:
            assert kw in cli_patterns, f"Missing CLI keyword: {kw}"


class TestFallbackToolChain:
    """Test FALLBACK_TOOL_CHAIN constant structure."""

    def test_suzieq_fallback_chain(self):
        """SuzieQ should fallback to CLI and NETCONF tools."""
        chain = FALLBACK_TOOL_CHAIN.get("suzieq", [])
        assert "cli_tool" in chain
        assert "netconf_tool" in chain

    def test_netbox_fallback_chain(self):
        """NetBox should fallback to SuzieQ and CLI."""
        chain = FALLBACK_TOOL_CHAIN.get("netbox", [])
        assert "suzieq_query" in chain
        assert "cli_tool" in chain

    def test_openconfig_fallback_chain(self):
        """OpenConfig should fallback to CLI and NETCONF."""
        chain = FALLBACK_TOOL_CHAIN.get("openconfig", [])
        assert "cli_tool" in chain
        assert "netconf_tool" in chain

    def test_cli_no_fallback(self):
        """CLI should have no fallback (it's the last resort)."""
        chain = FALLBACK_TOOL_CHAIN.get("cli", [])
        assert chain == []


def create_mock_strategy():
    """Create FastPathStrategy with mocked dependencies."""
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"answer": "test"}'))

    mock_registry = MagicMock()
    mock_registry.list_tools.return_value = [
        "suzieq_query",
        "cli_tool",
        "netconf_tool",
        "netbox_api_call",
    ]
    mock_registry.get_tool_descriptions.return_value = {}
    # Ensure get_device_list returns None (not configured) so __ALL_DEVICES__ is used
    mock_registry.get_device_list.return_value = None

    # Mock at the source module level (where it's imported from)
    with patch("olav.strategies.fast_path.MemoryWriter"):
        with patch("olav.strategies.fast_path.EpisodicMemoryTool"):
            with patch("olav.core.prompt_manager.prompt_manager") as mock_pm:
                mock_pm.load_tool_capability_guide.return_value = None
                strategy = FastPathStrategy(
                    llm=mock_llm,
                    tool_registry=mock_registry,
                )
    return strategy


class TestSchemaRelevanceCheck:
    """Test _check_schema_relevance method."""

    @pytest.fixture
    def strategy(self):
        """Create FastPathStrategy with mocked dependencies."""
        return create_mock_strategy()

    def test_no_schema_returns_not_relevant(self, strategy):
        """Empty schema should trigger fallback."""
        is_relevant, reason = strategy._check_schema_relevance(
            user_query="查询 syslog 配置",
            schema_context=None,
            intent_category="suzieq",
        )
        assert is_relevant is False
        assert "No schema" in reason

    def test_direct_match_returns_relevant(self, strategy):
        """Schema with matching table name should be relevant."""
        schema_context = {"bgp": {"fields": ["state", "peer"]}}
        is_relevant, reason = strategy._check_schema_relevance(
            user_query="查询 bgp 邻居状态",
            schema_context=schema_context,
            intent_category="suzieq",
        )
        assert is_relevant is True
        assert reason is None

    def test_syslog_query_with_bgp_schema_not_relevant(self, strategy):
        """Syslog query with BGP schema should NOT be relevant."""
        schema_context = {
            "bgp": {"fields": ["state", "peer"]},
            "interfaces": {"fields": ["state", "mtu"]},
        }
        is_relevant, reason = strategy._check_schema_relevance(
            user_query="查询设备的 syslog 配置",
            schema_context=schema_context,
            intent_category="suzieq",
        )
        assert is_relevant is False
        assert "syslog" in reason.lower()

    def test_interface_query_with_interface_schema_relevant(self, strategy):
        """Interface query with interface schema should be relevant."""
        schema_context = {"interfaces": {"fields": ["state", "mtu", "speed"]}}
        is_relevant, reason = strategy._check_schema_relevance(
            user_query="查询接口状态",
            schema_context=schema_context,
            intent_category="suzieq",
        )
        assert is_relevant is True

    def test_chinese_keyword_semantic_match(self, strategy):
        """Chinese keywords should match via semantic mapping."""
        schema_context = {"routes": {"fields": ["prefix", "nexthop"]}}
        is_relevant, reason = strategy._check_schema_relevance(
            user_query="检查路由表",
            schema_context=schema_context,
            intent_category="suzieq",
        )
        assert is_relevant is True


class TestGetFallbackTool:
    """Test _get_fallback_tool method."""

    @pytest.fixture
    def strategy(self):
        """Create FastPathStrategy with mocked dependencies."""
        return create_mock_strategy()

    def test_suzieq_fallback_uses_cli_tool(self, strategy):
        """SuzieQ fallback should use cli_tool first."""
        tool, params = strategy._get_fallback_tool(
            intent_category="suzieq",
            user_query="查询 R1 的 syslog 配置",
        )
        assert tool == "cli_tool"

    def test_syslog_query_generates_show_logging_command(self, strategy):
        """Syslog query should generate 'show logging' command."""
        tool, params = strategy._get_fallback_tool(
            intent_category="suzieq",
            user_query="检查所有设备的 syslog 服务器配置",
        )
        assert tool == "cli_tool"
        assert params.get("command") == "show logging"

    def test_ntp_query_generates_show_ntp_command(self, strategy):
        """NTP query should generate 'show ntp status' command."""
        tool, params = strategy._get_fallback_tool(
            intent_category="suzieq",
            user_query="查询 NTP 状态",
        )
        assert params.get("command") == "show ntp status"

    def test_snmp_query_generates_show_snmp_command(self, strategy):
        """SNMP query should generate 'show snmp' command."""
        tool, params = strategy._get_fallback_tool(
            intent_category="suzieq",
            user_query="检查 SNMP 配置",
        )
        assert params.get("command") == "show snmp"

    def test_device_name_extraction(self, strategy):
        """Device names should be extracted from query."""
        tool, params = strategy._get_fallback_tool(
            intent_category="suzieq",
            user_query="查询 R1 的 syslog 配置",
        )
        assert params.get("device") == "R1"

    def test_multiple_device_names_takes_first(self, strategy):
        """Multiple device names should take first match."""
        tool, params = strategy._get_fallback_tool(
            intent_category="suzieq",
            user_query="比较 R1 和 R2 的日志配置",
        )
        assert params.get("device") == "R1"

    def test_no_device_defaults_to_all_devices_marker(self, strategy):
        """No device name with 'all devices' query should use __ALL_DEVICES__ marker."""
        tool, params = strategy._get_fallback_tool(
            intent_category="suzieq",
            user_query="检查所有设备的 syslog 配置",
        )
        assert params.get("device") == "__ALL_DEVICES__"
        assert params.get("batch_mode") is True


class TestExecuteFallbackIntegration:
    """Integration tests for fallback in execute() flow."""

    @pytest.fixture
    def strategy(self):
        """Create FastPathStrategy with mocked dependencies."""
        return create_mock_strategy()

    @pytest.mark.asyncio
    async def test_syslog_query_triggers_fallback_batch_signal(self, strategy):
        """Syslog query with 'all devices' should signal batch execution needed."""
        # Mock classify_intent to return suzieq
        with patch(
            "olav.strategies.fast_path.classify_intent_async",
            new=AsyncMock(return_value=("suzieq", 0.75)),
        ):
            # Mock schema discovery to return unrelated tables
            strategy._discover_schema_for_intent = AsyncMock(
                return_value={"bgp": {}, "interfaces": {}}
            )

            result = await strategy.execute("查询所有设备的 syslog 配置")

            # Should signal batch execution is needed
            assert result["success"] is False
            assert result["reason"] == "batch_execution_required"
            assert result["batch_hint"]["tool"] == "cli_tool"
            assert result["batch_hint"]["command"] == "show logging"
            assert result["batch_hint"]["all_devices"] is True

    @pytest.mark.asyncio
    async def test_syslog_query_specific_device_triggers_fallback(self, strategy):
        """Syslog query with specific device should execute fallback successfully."""
        # Mock classify_intent to return suzieq
        with patch(
            "olav.strategies.fast_path.classify_intent_async",
            new=AsyncMock(return_value=("suzieq", 0.75)),
        ):
            # Mock schema discovery to return unrelated tables
            strategy._discover_schema_for_intent = AsyncMock(
                return_value={"bgp": {}, "interfaces": {}}
            )

            # Mock tool execution
            from olav.tools.base import ToolOutput

            mock_output = ToolOutput(
                source="cli_tool",
                device="R1",
                data=[{"output": "Logging to 192.168.100.10"}],
                metadata={},
            )
            strategy._execute_tool = AsyncMock(return_value=mock_output)

            # Mock answer formatting
            from olav.strategies.fast_path import FormattedAnswer

            strategy._format_answer = AsyncMock(
                return_value=FormattedAnswer(
                    answer="R1 Syslog 已配置为 192.168.100.10",
                    data_used=["output"],
                    confidence=0.85,
                )
            )

            result = await strategy.execute("查询 R1 的 syslog 配置")

            assert result["success"] is True
            assert result["metadata"]["strategy"] == "fast_path_fallback"
            assert result["metadata"]["fallback_tool"] == "cli_tool"

    @pytest.mark.asyncio
    async def test_bgp_query_no_fallback(self, strategy):
        """BGP query with matching schema should NOT trigger fallback."""
        with patch(
            "olav.strategies.fast_path.classify_intent_async",
            new=AsyncMock(return_value=("suzieq", 0.85)),
        ):
            # Mock schema discovery to return matching table
            strategy._discover_schema_for_intent = AsyncMock(
                return_value={"bgp": {"fields": ["state", "peer"]}}
            )

            # Mock memory search (no pattern)
            strategy._search_episodic_memory = AsyncMock(return_value=None)

            # Mock parameter extraction
            from olav.strategies.fast_path import ParameterExtraction

            strategy._extract_parameters = AsyncMock(
                return_value=ParameterExtraction(
                    tool="suzieq_query",
                    parameters={"table": "bgp"},
                    confidence=0.9,
                    reasoning="BGP query",
                )
            )

            # Mock tool execution
            from olav.tools.base import ToolOutput

            mock_output = ToolOutput(
                source="suzieq_query",
                device="all",
                data=[{"state": "Established"}],
                metadata={"elapsed_ms": 100},
            )
            strategy._execute_tool = AsyncMock(return_value=mock_output)

            # Mock memory writer (async)
            strategy.memory_writer.capture_success = AsyncMock()

            # Mock answer formatting
            from olav.strategies.fast_path import FormattedAnswer

            strategy._format_answer = AsyncMock(
                return_value=FormattedAnswer(
                    answer="BGP 状态正常",
                    data_used=["state"],
                    confidence=0.9,
                )
            )

            result = await strategy.execute("查询 BGP 邻居状态")

            assert result["success"] is True
            assert result["metadata"]["strategy"] == "fast_path"
            assert "fallback_tool" not in result["metadata"]
