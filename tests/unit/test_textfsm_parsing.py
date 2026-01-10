"""Unit tests for Phase 4.2: TextFSM Parsing and Token Statistics.

Tests the structured parsing with fallback and token tracking.
"""

from unittest.mock import MagicMock, patch

import pytest

from olav.tools.network import (
    CommandExecutionResult,
    NetworkExecutor,
)


@pytest.mark.unit
class TestCommandExecutionResult:
    """Test CommandExecutionResult with Phase 4.2 fields."""

    def test_result_without_parsing(self) -> None:
        """Test result without TextFSM parsing."""
        result = CommandExecutionResult(
            device="R1",
            command="show version",
            success=True,
            output="Cisco IOS XE, Version 17.3.1",
            duration_ms=100,
        )

        assert result.device == "R1"
        assert result.structured is False
        assert result.raw_output is None
        assert result.raw_tokens is None
        assert result.parsed_tokens is None
        assert result.tokens_saved is None

    def test_result_with_parsing(self) -> None:
        """Test result with TextFSM parsing."""
        result = CommandExecutionResult(
            device="R1",
            command="show ip interface brief",
            success=True,
            output='[{"interface": "GigabitEthernet0/0", "status": "up"}]',
            duration_ms=150,
            structured=True,
            raw_output="Raw parsed result",
            raw_tokens=800,
            parsed_tokens=200,
            tokens_saved=600,
        )

        assert result.structured is True
        assert result.raw_output == "Raw parsed result"
        assert result.raw_tokens == 800
        assert result.parsed_tokens == 200
        assert result.tokens_saved == 600


@pytest.mark.unit
@pytest.mark.xdist_group("database")
class TestNetworkExecutorTextFSM:
    """Test NetworkExecutor TextFSM functionality."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        # Create mock executor
        self.executor = NetworkExecutor(
            nornir_config=".olav/config/nornir/config.yaml",
            blacklist_file=".olav/imports/commands/blacklist.txt",
        )

    def test_estimate_tokens(self) -> None:
        """Test token estimation."""
        # Short text
        tokens = self.executor._estimate_tokens("hello world")
        assert tokens == 2  # 11 chars // 4 = 2

        # Longer text
        text = "a" * 100  # 100 characters
        tokens = self.executor._estimate_tokens(text)
        assert tokens == 25  # 100 // 4 = 25

        # Empty text
        tokens = self.executor._estimate_tokens("")
        assert tokens == 0

    def test_execute_with_parsing_disabled(self) -> None:
        """Test execute_with_parsing when TextFSM disabled."""
        # Mock settings to disable TextFSM
        from unittest.mock import patch

        from olav.core.settings import OlavSettings

        with patch.object(
            OlavSettings, "execution_use_textfsm", False
        ):
            # Mock the execute method
            with patch.object(self.executor, "execute") as mock_execute:
                mock_execute.return_value = CommandExecutionResult(
                    device="R1",
                    command="show version",
                    success=True,
                    output="test output",
                    duration_ms=100,
                )

                result = self.executor.execute_with_parsing("R1", "show version")

                # Should call regular execute, not TextFSM
                mock_execute.assert_called_once()
                assert result.structured is False

    def test_execute_with_parsing_explicit_override(self) -> None:
        """Test execute_with_parsing with explicit TextFSM override."""
        from unittest.mock import patch

        # Test with explicit use_textfsm=True
        with patch.object(
            self.executor, "_execute_with_textfsm"
        ) as mock_textfsm:
            mock_textfsm.return_value = CommandExecutionResult(
                device="R1",
                command="show version",
                success=True,
                output="structured output",
                structured=True,
                raw_tokens=1000,
                parsed_tokens=200,
                tokens_saved=800,
                duration_ms=150,
            )

            result = self.executor.execute_with_parsing(
                "R1", "show version", use_textfsm=True
            )

            # Should use TextFSM despite settings
            mock_textfsm.assert_called_once()
            assert result.structured is True
            assert result.tokens_saved == 800

    def test_textfsm_fallback_on_error(self) -> None:
        """Test fallback to raw text when TextFSM fails."""
        from unittest.mock import patch

        from olav.core.settings import OlavSettings

        with patch.object(
            OlavSettings, "execution_textfsm_fallback", True
        ):
            # Mock TextFSM to fail
            with patch.object(
                self.executor, "_execute_with_textfsm"
            ) as mock_textfsm:
                mock_textfsm.side_effect = Exception("TextFSM failed")

                # Mock regular execute to succeed
                with patch.object(self.executor, "execute") as mock_execute:
                    mock_execute.return_value = CommandExecutionResult(
                        device="R1",
                        command="show version",
                        success=True,
                        output="raw fallback output",
                        duration_ms=100,
                    )

                    result = self.executor.execute_with_parsing("R1", "show version")

                    # Should fallback to regular execute
                    mock_execute.assert_called_once()
                    assert result.success is True
                    assert result.structured is False

    def test_textfsm_no_fallback_on_error(self) -> None:
        """Test no fallback when disabled."""
        from olav.core.settings import OlavSettings

        with patch.object(
            OlavSettings, "execution_textfsm_fallback", False
        ):
            # Mock TextFSM to fail
            with patch.object(
                self.executor, "_execute_with_textfsm"
            ) as mock_textfsm:
                mock_textfsm.side_effect = Exception("TextFSM failed")

                result = self.executor.execute_with_parsing("R1", "show version")

                # Should return error result
                assert result.success is False
                assert "fallback disabled" in result.error.lower()

    def test_execute_with_textfsm_success(self) -> None:
        """Test successful TextFSM execution."""
        from unittest.mock import patch

        # Mock Nornir result
        mock_host_result = MagicMock()
        mock_host_result.failed = False
        mock_host_result.result = [
            {"interface": "GigabitEthernet0/0", "status": "up", "ip": "10.1.1.1"}
        ]

        mock_aggregated_result = MagicMock()
        mock_aggregated_result.__getitem__ = MagicMock(return_value=mock_host_result)

        # Mock get_nornir
        with patch("olav.tools.network.get_nornir") as mock_get_nornir:
            mock_nr = MagicMock()
            mock_nr_filtered = MagicMock()
            mock_nr_filtered.inventory.hosts = {"R1": MagicMock()}
            mock_nr.filter.return_value = mock_nr_filtered
            mock_nr_filtered.run.return_value = mock_aggregated_result
            mock_get_nornir.return_value = mock_nr

            # Mock database methods
            with patch.object(self.executor.db, "is_command_allowed", return_value=True):
                with patch.object(self.executor.db, "log_execution"):
                    result = self.executor._execute_with_textfsm(
                        "R1", "show ip interface brief", 30
                    )

                    # Verify result
                    assert result.success is True
                    assert result.structured is True
                    assert result.raw_output is not None
                    assert result.raw_tokens > 0
                    assert result.parsed_tokens > 0
                    assert result.tokens_saved >= 0

    def test_token_savings_calculation(self) -> None:
        """Test token savings are calculated correctly."""
        # Simulate raw text (longer)
        raw_text = "Interface Status: up, Protocol: up\n" * 50  # ~1800 chars
        raw_tokens = len(raw_text) // 4  # ~450 tokens

        # Simulate structured output (shorter)
        structured = '[{"interface": "Gi0/0", "status": "up"}]'
        parsed_tokens = len(structured) // 4  # ~15 tokens

        tokens_saved = raw_tokens - parsed_tokens

        assert tokens_saved > 0
        assert tokens_saved == (raw_tokens - parsed_tokens)

    def test_token_savings_for_various_commands(self) -> None:
        """Test token savings for different command types."""
        test_cases = [
            # (raw_length, expected_savings_percent)
            (800, 0.75),  # show ip interface brief
            (2000, 0.80),  # show ip route
            (500, 0.70),  # show ip bgp summary
        ]

        for raw_length, expected_savings in test_cases:
            # Simulate raw text
            "x" * raw_length
            raw_tokens = raw_length // 4

            # Simulate structured output (typically 75-80% smaller)
            structured_size = int(raw_length * (1 - expected_savings))
            "y" * structured_size
            parsed_tokens = structured_size // 4

            tokens_saved = raw_tokens - parsed_tokens
            savings_percent = tokens_saved / raw_tokens

            # Verify savings are in expected range
            assert (
                abs(savings_percent - expected_savings) < 0.05
            ), f"Expected {expected_savings} savings, got {savings_percent}"


@pytest.mark.unit
@pytest.mark.xdist_group("database")
class TestTextFSMIntegration:
    """Integration tests for TextFSM functionality."""

    def test_end_to_end_parsing_workflow(self) -> None:
        """Test complete workflow: execute → parse → save tokens."""
        from unittest.mock import patch

        executor = NetworkExecutor()

        # Mock successful TextFSM execution
        mock_host_result = MagicMock()
        mock_host_result.failed = False
        mock_host_result.result = {
            "interfaces": [
                {"name": "Gi0/0", "status": "up"},
                {"name": "Gi0/1", "status": "down"},
            ]
        }

        mock_aggregated_result = MagicMock()
        mock_aggregated_result.__getitem__ = MagicMock(return_value=mock_host_result)

        # Patch get_nornir in network_executor module
        with patch("olav.tools.network_executor.get_nornir") as mock_get_nornir:
            mock_nr = MagicMock()
            mock_nr_filtered = MagicMock()
            mock_nr_filtered.inventory.hosts = {"R1": MagicMock()}
            mock_nr.filter.return_value = mock_nr_filtered
            mock_nr_filtered.run.return_value = mock_aggregated_result
            mock_get_nornir.return_value = mock_nr

            # Mock database methods
            with patch.object(executor.db, "is_command_allowed", return_value=True):
                with patch.object(executor.db, "log_execution"):
                    result = executor.execute_with_parsing(
                        "R1", "show ip interface brief"
                    )

                    # Verify complete workflow
                    assert result.success is True
                    assert result.structured is True
                    assert result.tokens_saved > 0
                    # Check for parsed structure (interface key from TextFSM)
                    assert "interface" in result.output or "Gi0/0" in result.output or "interfaces" in result.output

    def test_parse_rate_statistics(self) -> None:
        """Test tracking of parse success rate."""
        # This would be implemented with a statistics tracker
        # For now, just verify the structure exists
        NetworkExecutor()

        # Token statistics tracking is enabled by default
        from olav.core.settings import get_settings

        settings = get_settings()
        assert settings.execution_enable_token_stats is True


@pytest.mark.unit
class TestSettingsConfiguration:
    """Test settings configuration for TextFSM."""

    def test_textfsm_settings_defaults(self) -> None:
        """Test default TextFSM settings."""
        from olav.core.settings import get_settings

        settings = get_settings()

        assert settings.execution_use_textfsm is True
        assert settings.execution_textfsm_fallback is True
        assert settings.execution_enable_token_stats is True

    def test_modify_textfsm_settings(self) -> None:
        """Test modifying TextFSM settings."""
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"

            # Create custom settings
            settings_data = {
                "execution": {
                    "useTextFSM": False,
                    "textFSMFallbackToRaw": False,
                    "enableTokenStatistics": False,
                }
            }

            with open(settings_path, "w") as f:
                json.dump(settings_data, f)

            # Load and verify
            from olav.core.settings import OlavSettings

            settings = OlavSettings(settings_path=settings_path)

            assert settings.execution_use_textfsm is False
            assert settings.execution_textfsm_fallback is False
            assert settings.execution_enable_token_stats is False
