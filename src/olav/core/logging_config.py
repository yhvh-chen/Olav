"""Logging configuration for OLAV."""

import logging

from rich.logging import RichHandler


def setup_logging(verbose: bool = False) -> None:
    """Configure application logging levels.

    Args:
        verbose: If True, show detailed logs including timestamps and paths.
                 If False, only show essential OLAV logs and suppress third-party noise.
    """
    # Root logger - suppress everything by default
    logging.getLogger().setLevel(logging.WARNING)

    # OLAV module - adjust based on verbosity
    olav_level = logging.DEBUG if verbose else logging.INFO
    olav_logger = logging.getLogger("olav")
    olav_logger.setLevel(olav_level)

    # Silence third-party libraries
    # HTTP/Network libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # AI/LLM libraries
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)

    # LangChain ecosystem
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("langchain_core").setLevel(logging.WARNING)
    logging.getLogger("langchain_openai").setLevel(logging.WARNING)
    logging.getLogger("langgraph").setLevel(logging.WARNING)

    # Database libraries
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("psycopg").setLevel(logging.WARNING)

    # Configure Rich handler for OLAV logs only
    if not olav_logger.handlers:
        handler = RichHandler(
            show_time=verbose,
            show_path=verbose,
            markup=True,
            rich_tracebacks=True,
            tracebacks_show_locals=verbose,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        olav_logger.addHandler(handler)
        olav_logger.propagate = False  # Don't propagate to root logger
