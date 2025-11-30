"""
Auto-correction and HITL rules for NetBox reconciliation.
"""

from olav.sync.rules.auto_correct import (
    AUTO_CORRECT_RULES,
    get_auto_correct_handler,
    is_safe_auto_correct,
)
from olav.sync.rules.hitl_required import (
    HITL_REQUIRED_RULES,
    get_hitl_prompt,
    get_hitl_summary,
    requires_hitl_approval,
)

__all__ = [
    "AUTO_CORRECT_RULES",
    "HITL_REQUIRED_RULES",
    "get_auto_correct_handler",
    "get_hitl_prompt",
    "get_hitl_summary",
    "is_safe_auto_correct",
    "requires_hitl_approval",
]
