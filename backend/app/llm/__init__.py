"""LLM layer.

The LLM never computes anything. It receives a fact sheet (numbers we computed from
data) and is only allowed to *explain* it. Every number in its output is then checked
against the fact sheet (see grounding.py); if the narrative cites a number we can't
trace, we fall back to a deterministic template narrative and say so in the UI.
"""
from .client import LLMError, complete_json, provider_info  # noqa: F401
