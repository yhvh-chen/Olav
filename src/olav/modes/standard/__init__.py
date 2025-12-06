"""Standard Mode - Fast single-step query execution.

Components:
    - UnifiedClassifier: LLM-based tool selection (single call)
    - FastPathExecutor: Direct tool invocation
    - ConfidenceGate: Route to Expert Mode if confidence < threshold

Capabilities:
    - SuzieQ query/summarize/unique/aver
    - NetBox read/write (HITL for writes)
    - Schema discovery
    - Nornir config (HITL for writes)
"""
