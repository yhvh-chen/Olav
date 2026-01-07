"""
OLAV v0.8 - Network AI Operations Assistant
DeepAgents Native Framework
"""

__version__ = "0.8.0"

# Main agent
from olav.agent import create_olav_agent, get_macro_analyzer, get_micro_analyzer, initialize_olav

# Core database
from olav.core.database import OlavDatabase, get_database

# Tools
from olav.tools.capabilities import api_call, search_capabilities
from olav.tools.loader import reload_capabilities, validate_capabilities
from olav.tools.network import list_devices, nornir_execute

__all__ = [
    # Version
    "__version__",
    # Agent
    "create_olav_agent",
    "initialize_olav",
    "get_macro_analyzer",
    "get_micro_analyzer",
    # Database
    "OlavDatabase",
    "get_database",
    # Tools
    "nornir_execute",
    "list_devices",
    "search_capabilities",
    "api_call",
    "reload_capabilities",
    "validate_capabilities",
]
