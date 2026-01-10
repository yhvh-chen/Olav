"""Tools module - uses lazy import to avoid loading langchain at module level."""


def __getattr__(name: str):
    """Lazy import to avoid loading langchain when only simple tools are needed."""
    if name == "delegate_task":
        from olav.tools.task_tools import delegate_task

        return delegate_task

    raise AttributeError(f"module 'olav.tools' has no attribute {name!r}")


__all__ = [
    "delegate_task",
]
