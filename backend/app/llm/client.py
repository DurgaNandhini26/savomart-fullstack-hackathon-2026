"""Provider-agnostic LLM client (config-driven, no SDK lock-in).

LLM_PROVIDER=anthropic  -> Anthropic Messages API
LLM_PROVIDER=openai     -> any OpenAI-compatible /chat/completions endpoint
                           (OpenAI, Groq, OpenRouter, Together, Ollama, LM Studio ...)
LLM_PROVIDER=none       -> disabled; callers use deterministic templates
"""
from __future__ import annotations

import json
import re

import httpx

from ..config import get_settings

DEFAULT_MODELS = {"anthropic": "claude-haiku-4-5-20251001", "openai": "gpt-4o-mini"}


class LLMError(RuntimeError):
    pass


def provider_info() -> dict:
    s = get_settings()
    p = (s.llm_provider or "none").lower()
    enabled = p in ("anthropic", "openai") and (bool(s.llm_api_key) or bool(s.llm_base_url))
    return {"provider": p if enabled else "none", "model": (s.llm_model or DEFAULT_MODELS.get(p, "")) if enabled else None,
            "enabled": enabled}


def complete_json(system: str, user: str, max_tokens: int = 1200) -> dict:
    """Ask the model for a JSON object. Raises LLMError on any failure."""
    s = get_settings()
    info = provider_info()
    if not info["enabled"]:
        raise LLMError("LLM disabled (LLM_PROVIDER=none or no key)")
    try:
        if info["provider"] == "anthropic":
            r = httpx.post(
                (s.llm_base_url or "https://api.anthropic.com") + "/v1/messages",
                headers={"x-api-key": s.llm_api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": info["model"], "max_tokens": max_tokens, "system": system,
                      "messages": [{"role": "user", "content": user}], "temperature": 0.2},
                timeout=s.llm_timeout_s,
            )
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        else:
            base = (s.llm_base_url or "https://api.openai.com/v1").rstrip("/")
            headers = {"content-type": "application/json"}
            if s.llm_api_key:
                headers["authorization"] = f"Bearer {s.llm_api_key}"
            r = httpx.post(
                f"{base}/chat/completions", headers=headers, timeout=s.llm_timeout_s,
                json={"model": info["model"], "max_tokens": max_tokens, "temperature": 0.2,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as exc:
        raise LLMError(f"{info['provider']} HTTP {exc.response.status_code}: {exc.response.text[:200]}") from exc
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        raise LLMError(f"{info['provider']} request failed: {exc!r}") from exc
    return parse_json(text)


def parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"model did not return valid JSON: {exc}") from exc
