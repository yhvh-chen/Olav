"""
OLAV v0.8 - Network AI Operations Assistant
DeepAgents Native Framework
"""

__version__ = "0.8.0"


def __getattr__(name: str):
    """Lazy import to avoid loading deepagents when only tools are needed."""
    if name in (
        "create_olav_agent",
        "get_inspector_agent",
        "get_macro_analyzer",
        "get_micro_analyzer",
        "initialize_olav",
    ):
        from olav.agent import (
            create_olav_agent,
            get_inspector_agent,
            get_macro_analyzer,
            get_micro_analyzer,
            initialize_olav,
        )

        return locals()[name]

    if name in ("OlavDatabase", "get_database"):
        from olav.core.database import OlavDatabase, get_database

        return locals()[name]

    if name in ("api_call", "search_capabilities"):
        from olav.tools.capabilities import api_call, search_capabilities

        return locals()[name]

    if name in ("reload_capabilities", "validate_capabilities"):
        from olav.tools.loader import reload_capabilities, validate_capabilities

        return locals()[name]

    if name in ("list_devices", "nornir_execute"):
        from olav.tools.network import list_devices, nornir_execute

        return locals()[name]

    raise AttributeError(f"module 'olav' has no attribute {name!r}")


__all__ = [
    # Version
    "__version__",
    # Agent
    "create_olav_agent",
    "initialize_olav",
    "get_macro_analyzer",
    "get_micro_analyzer",
    "get_inspector_agent",
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
