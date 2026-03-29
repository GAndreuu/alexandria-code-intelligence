"""
ACI :: LLM Provider
====================
Abstraction layer for LLM calls. Supports:
- Google Gemini (recommended)
- Anthropic (Claude)
- OpenAI (GPT)
- Ollama (local)
- None (graceful degradation)

LLM is used for:
1. Logic analysis (finding algorithmic flaws)
2. Contract evolution (suggesting new rules)
3. Dream synthesis (deeper insights than AST alone)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""
    provider: str = "none"  # google | anthropic | openai | ollama | none
    model: str = "claude-sonnet-4-20250514"
    api_key_env: str = "ANTHROPIC_API_KEY"
    max_tokens: int = 4096
    temperature: float = 0.3


class LLMProvider:
    """Unified LLM interface with graceful degradation."""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or self._auto_detect()
        self._client = None
        self._available = False
        self._init_client()

    @property
    def available(self) -> bool:
        return self._available

    def analyze(self, system: str, user: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Send an analysis request to the LLM.

        Args:
            system: System prompt (defines the LLM's role).
            user: User prompt (the question/task).
            context: Optional structured context to include.

        Returns:
            LLM response text, or fallback message if unavailable.
        """
        if not self._available:
            return "[LLM unavailable — install provider and set API key for deep analysis]"

        if context:
            user = f"{user}\n\n## Context\n```json\n{json.dumps(context, indent=2, default=str)[:8000]}\n```"

        try:
            return self._call(system, user)
        except Exception as e:
            logger.error("LLM call failed")
            return f"[LLM error: {str(e)[:100]}]"

    # ── Provider-specific ─────────────────────────────────────

    def _init_client(self) -> None:
        provider = self.config.provider

        if provider == "google":
            try:
                from google import genai
                key = os.environ.get(self.config.api_key_env or "GEMINI_API_KEY", "")
                if key:
                    self._client = genai.Client(api_key=key)
                    self._available = True
                    logger.info("LLM: Google Gemini initialized")
                else:
                    logger.info("LLM: No GEMINI_API_KEY found")
            except ImportError:
                logger.info("LLM: google-genai package not installed. Run: pip install google-genai")

        elif provider == "anthropic":
            try:
                import anthropic
                key = os.environ.get(self.config.api_key_env, "")
                if key:
                    self._client = anthropic.Anthropic(api_key=key)
                    self._available = True
                    logger.info("LLM: Anthropic initialized")
                else:
                    logger.info("LLM: No API key found")
            except ImportError:
                logger.info("LLM: anthropic package not installed")

        elif provider == "openai":
            try:
                import openai
                key = os.environ.get(self.config.api_key_env or "OPENAI_API_KEY", "")
                if key:
                    self._client = openai.OpenAI(api_key=key)
                    self._available = True
                    logger.info("LLM: OpenAI initialized")
            except ImportError:
                logger.info("LLM: openai package not installed")

        elif provider == "ollama":
            try:
                import httpx
                resp = httpx.get("http://localhost:11434/api/tags", timeout=2)
                if resp.status_code == 200:
                    self._available = True
                    logger.info("LLM: Ollama initialized")
            except Exception:
                logger.info("LLM: Ollama not available")

        else:
            logger.info("LLM: Provider set to 'none', degrading gracefully")

    def _call(self, system: str, user: str) -> str:
        provider = self.config.provider

        if provider == "google":
            resp = self._client.models.generate_content(
                model=self.config.model,
                contents=f"{system}\n\n{user}",
                config={
                    "max_output_tokens": self.config.max_tokens,
                    "temperature": self.config.temperature,
                },
            )
            return resp.text

        elif provider == "anthropic":
            resp = self._client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text

        elif provider == "openai":
            resp = self._client.chat.completions.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return resp.choices[0].message.content

        elif provider == "ollama":
            import httpx
            resp = httpx.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": self.config.model,
                    "system": system,
                    "prompt": user,
                    "stream": False,
                },
                timeout=60,
            )
            return resp.json().get("response", "")

        return "[No LLM provider]"

    def _auto_detect(self) -> LLMConfig:
        """Auto-detect available LLM provider."""
        # Check config file
        config_path = Path(".aci") / "config.yaml"
        if config_path.exists():
            try:
                import yaml
                raw = yaml.safe_load(config_path.read_text())
                llm = raw.get("llm", {})
                return LLMConfig(
                    provider=llm.get("provider", "none"),
                    model=llm.get("model", "claude-sonnet-4-20250514"),
                    api_key_env=llm.get("api_key_env", "ANTHROPIC_API_KEY"),
                )
            except Exception:
                pass

        # Auto-detect by checking env vars (Google first — it's the recommended provider)
        if os.environ.get("GEMINI_API_KEY"):
            return LLMConfig(provider="google", model="gemini-2.5-flash", api_key_env="GEMINI_API_KEY")
        if os.environ.get("ANTHROPIC_API_KEY"):
            return LLMConfig(provider="anthropic")
        if os.environ.get("OPENAI_API_KEY"):
            return LLMConfig(provider="openai", model="gpt-4o", api_key_env="OPENAI_API_KEY")

        return LLMConfig(provider="none")


# ── Analysis Prompts ──────────────────────────────────────────

LOGIC_ANALYSIS_SYSTEM = """You are ACI Logic Analyzer — an expert code reviewer that identifies:
1. Algorithmic flaws (wrong complexity, incorrect logic)
2. Mathematical errors (wrong formulas, edge cases)
3. Missing error handling (unhandled states)
4. Better design patterns available
5. Potential race conditions or state issues

Be SPECIFIC and ACTIONABLE. Reference line numbers when possible.
Format findings as a numbered list with severity [CRITICAL/HIGH/MEDIUM/LOW]."""

CONTRACT_EVOLUTION_SYSTEM = """You are ACI Contract Evolver. Based on code patterns and audit data,
suggest improvements to the quality contract (rules that should be added, modified, or removed).

Be data-driven: only suggest changes supported by the evidence provided.
Format as YAML patches to the contract."""
