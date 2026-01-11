"""Core module

Re-exports from config package for backward compatibility.
"""

# Re-export settings from config package
from config.settings import DiagnosisSettings, ExecutionSettings, Settings, get_settings

__all__ = ["Settings", "get_settings", "ExecutionSettings", "DiagnosisSettings"]
