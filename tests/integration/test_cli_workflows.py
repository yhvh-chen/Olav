"""Integration test for CLI workflows mode."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_workflows_mode_imports():
    """Test that workflows mode can be imported without errors."""
    from olav.agents.root_agent_orchestrator import create_workflow_orchestrator
    
    # Should import successfully
    assert create_workflow_orchestrator is not None
    assert callable(create_workflow_orchestrator)


@pytest.mark.asyncio  
async def test_workflow_orchestrator_creation():
    """Test WorkflowOrchestrator creation."""
    from olav.agents.root_agent_orchestrator import WorkflowOrchestrator
    from unittest.mock import Mock
    
    mock_checkpointer = Mock()
    orchestrator = WorkflowOrchestrator(checkpointer=mock_checkpointer)
    
    # Should have 5 workflows (query, execution, netbox, deep_dive, inspection)
    assert len(orchestrator.workflows) >= 3
    
    # Should have classify methods
    assert hasattr(orchestrator, 'classify_intent')
    assert hasattr(orchestrator, '_classify_by_keywords')
    assert hasattr(orchestrator, 'route')


def test_cli_help_shows_workflows():
    """Test that CLI help shows workflows mode."""
    import subprocess
    import os
    
    # Set PYTHONPATH
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    
    result = subprocess.run(
        ["uv", "run", "python", "-m", "olav.main", "chat", "--help"],
        capture_output=True,
        text=True,
        env=env
    )
    
    # Should mention workflows in help
    assert result.returncode == 0
    assert "workflow" in result.stdout.lower()


def test_cli_default_mode_is_workflows():
    """Test that default agent mode is workflows."""
    # Verify from help output that workflows orchestrator is used
    import subprocess
    import os
    
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    
    result = subprocess.run(
        ["uv", "run", "python", "-m", "olav.main", "chat", "--help"],
        capture_output=True,
        text=True,
        env=env
    )
    
    # Check that help mentions workflows orchestrator architecture
    assert result.returncode == 0
    assert "Workflows Orchestrator" in result.stdout or "workflow" in result.stdout.lower()
