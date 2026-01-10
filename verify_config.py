#!/usr/bin/env python3
"""Verify v0.8 configuration is correct."""

try:
    from config.settings import settings
    
    print("✅ Configuration loaded successfully")
    print(f"  - Environment: {settings.environment}")
    print(f"  - DuckDB path: {settings.duckdb_path}")
    print(f"  - Checkpoint DB path: {settings.checkpoint_db_path}")
    print(f"  - LLM Provider: {settings.llm_provider}")
    print(f"  - Log Level: {settings.log_level}")
    
    # Check that olav_mode is gone
    if hasattr(settings, 'olav_mode'):
        print("❌ ERROR: olav_mode still exists in settings!")
        exit(1)
    else:
        print("✅ olav_mode successfully removed")
    
    # Check that netconf_port is gone or commented
    if hasattr(settings, 'netconf_port'):
        print("❌ ERROR: netconf_port still exists in settings!")
        exit(1)
    else:
        print("✅ netconf_port successfully commented out")
    
    print("\n✅ All configuration checks passed!")
    
except Exception as e:
    print(f"❌ Configuration error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
