"""Inspection Mode - YAML-driven batch audits.

Components:
    - YAMLLoader: Load inspection profiles
    - IntentCompiler: LLM-driven intent → query plan
    - MapReduceExecutor: Parallel device execution
    - ThresholdValidator: Zero-hallucination validation

Capabilities:
    - Intelligent inspection (LLM chooses table/conditions)
    - Batch parallel execution
    - Python-based threshold validation
    - Caching for query plans
"""
