"""Unit tests for Phase 3: SubAgent Configs.

Tests the subagent configuration generation for macro and micro analyzers.
"""

from olav.core.subagent_configs import get_macro_analyzer, get_micro_analyzer


class TestMacroAnalyzer:
    """Test macro-analyzer subagent configuration."""

    def test_macro_analyzer_returns_dict(self) -> None:
        """Test that get_macro_analyzer returns a dictionary."""
        config = get_macro_analyzer()
        assert isinstance(config, dict)

    def test_macro_analyzer_has_required_keys(self) -> None:
        """Test macro analyzer config has required keys."""
        config = get_macro_analyzer()
        required_keys = ["name", "description", "system_prompt", "tools"]
        for key in required_keys:
            assert key in config, f"Missing required key: {key}"

    def test_macro_analyzer_name(self) -> None:
        """Test macro analyzer has correct name."""
        config = get_macro_analyzer()
        assert config["name"] == "macro-analyzer"

    def test_macro_analyzer_description(self) -> None:
        """Test macro analyzer has meaningful description."""
        config = get_macro_analyzer()
        assert len(config["description"]) > 10
        # Should mention topology or macro-level analysis
        desc_lower = config["description"].lower()
        assert any(
            keyword in desc_lower
            for keyword in ["topology", "path", "network", "macro", "端到端", "拓扑"]
        )

    def test_macro_analyzer_system_prompt(self) -> None:
        """Test macro analyzer has system prompt."""
        config = get_macro_analyzer()
        assert isinstance(config["system_prompt"], str)
        assert len(config["system_prompt"]) > 50

    def test_macro_analyzer_tools(self) -> None:
        """Test macro analyzer has tools list."""
        config = get_macro_analyzer()
        assert isinstance(config["tools"], list)


class TestMicroAnalyzer:
    """Test micro-analyzer subagent configuration."""

    def test_micro_analyzer_returns_dict(self) -> None:
        """Test that get_micro_analyzer returns a dictionary."""
        config = get_micro_analyzer()
        assert isinstance(config, dict)

    def test_micro_analyzer_has_required_keys(self) -> None:
        """Test micro analyzer config has required keys."""
        config = get_micro_analyzer()
        required_keys = ["name", "description", "system_prompt", "tools"]
        for key in required_keys:
            assert key in config, f"Missing required key: {key}"

    def test_micro_analyzer_name(self) -> None:
        """Test micro analyzer has correct name."""
        config = get_micro_analyzer()
        assert config["name"] == "micro-analyzer"

    def test_micro_analyzer_description(self) -> None:
        """Test micro analyzer has meaningful description."""
        config = get_micro_analyzer()
        assert len(config["description"]) > 10
        # Should mention device-level or layer-by-layer analysis
        desc_lower = config["description"].lower()
        assert any(
            keyword in desc_lower for keyword in ["device", "layer", "tcp", "micro", "设备", "逐层"]
        )

    def test_micro_analyzer_system_prompt(self) -> None:
        """Test micro analyzer has system prompt."""
        config = get_micro_analyzer()
        assert isinstance(config["system_prompt"], str)
        assert len(config["system_prompt"]) > 50

    def test_micro_analyzer_tools(self) -> None:
        """Test micro analyzer has tools list."""
        config = get_micro_analyzer()
        assert isinstance(config["tools"], list)


class TestSubAgentConfigsConsistency:
    """Test consistency between subagent configs."""

    def test_different_names(self) -> None:
        """Test that macro and micro have different names."""
        macro = get_macro_analyzer()
        micro = get_micro_analyzer()
        assert macro["name"] != micro["name"]

    def test_different_descriptions(self) -> None:
        """Test that macro and micro have different descriptions."""
        macro = get_macro_analyzer()
        micro = get_micro_analyzer()
        assert macro["description"] != micro["description"]

    def test_different_system_prompts(self) -> None:
        """Test that macro and micro have different system prompts."""
        macro = get_macro_analyzer()
        micro = get_micro_analyzer()
        assert macro["system_prompt"] != micro["system_prompt"]

    def test_both_are_valid_subagent_configs(self) -> None:
        """Test both configs are valid for DeepAgents SubAgent."""
        macro = get_macro_analyzer()
        micro = get_micro_analyzer()

        for config in [macro, micro]:
            # Must have these for SubAgent creation
            assert "name" in config
            assert "description" in config
            assert "system_prompt" in config
            # Tools can be empty but must exist
            assert "tools" in config
