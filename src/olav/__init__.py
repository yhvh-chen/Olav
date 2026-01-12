"""
OLAV v0.8 - Network AI Operations Assistant
DeepAgents Native Framework
"""

__version__ = "0.8.0"


def __getattr__(name: str) -> object:  # noqa: ANN401
    """Lazy import to avoid loading deepagents when only tools are needed."""
    if name in (
        "create_olav_agent",
        "get_inspector_agent",
        "get_macro_analyzer",
        "get_micro_analyzer",
        "initialize_olav",
    ):
        from olav.agent import (  # noqa: F401
            create_olav_agent,
            get_inspector_agent,
            get_macro_analyzer,
            get_micro_analyzer,
            initialize_olav,
        )

        return locals()[name]

    if name in ("OlavDatabase", "get_database"):
        from olav.core.database import (  # noqa: F401
            OlavDatabase,
            get_database,
        )

        return locals()[name]

    if name in ("api_call", "search_capabilities"):
        from olav.tools.capabilities import (  # noqa: F401
            api_call,
            search_capabilities,
        )

        return locals()[name]

    if name in ("reload_capabilities", "validate_capabilities"):
        from olav.tools.loader import (  # noqa: F401
            reload_capabilities,
            validate_capabilities,
        )

        return locals()[name]

    if name in ("list_devices", "nornir_execute"):
        from olav.tools.network import (  # noqa: F401
            list_devices,
            nornir_execute,
        )

        return locals()[name]

    raise AttributeError(f"module 'olav' has no attribute {name!r}")


__all__ = [
    # Version
    "__version__",
    # Agent
    "create_olav_agent",  # pyright: ignore [reportUnsupportedDunderAll]
    "initialize_olav",  # pyright: ignore [reportUnsupportedDunderAll]
    "get_macro_analyzer",  # pyright: ignore [reportUnsupportedDunderAll]
    "get_micro_analyzer",  # pyright: ignore [reportUnsupportedDunderAll]
    "get_inspector_agent",  # pyright: ignore [reportUnsupportedDunderAll]
    # Database
    "OlavDatabase",  # pyright: ignore [reportUnsupportedDunderAll]
    "get_database",  # pyright: ignore [reportUnsupportedDunderAll]
    # Tools
    "nornir_execute",  # pyright: ignore [reportUnsupportedDunderAll]
    "list_devices",  # pyright: ignore [reportUnsupportedDunderAll]
    "search_capabilities",  # pyright: ignore [reportUnsupportedDunderAll]
    "api_call",  # pyright: ignore [reportUnsupportedDunderAll]
    "reload_capabilities",  # pyright: ignore [reportUnsupportedDunderAll]
    "validate_capabilities",  # pyright: ignore [reportUnsupportedDunderAll]
]
# All items above are provided via __getattr__ lazy loading
