"""UI module for OLAV chat interface."""

from olav.ui.chat_ui import ChatUI

# NOTE: ChatUI is legacy and will be replaced in Phase 3 (LangServe + New CLI)
# Currently still in use by main.py for CLI rendering

__all__ = ["ChatUI"]
