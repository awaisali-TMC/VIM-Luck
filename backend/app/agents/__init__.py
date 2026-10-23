"""ADK-based invoice processing agent (proof of concept).

Wraps existing extraction/matching/duplicate-check services into an
LlmAgent so a single conversational call can run the full pipeline:
  extract → validate totals → check duplicates → match PO → decide.

Mirrors the pattern from google/adk-samples invoice-processing.
"""
