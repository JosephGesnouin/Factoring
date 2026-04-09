#!/usr/bin/env python3
"""
Example: how to configure the LLM layer (C5) with your own API keys.

Three ways to inject your key:

  1. Directly in code via C5Config.api_key (explicit injection)
  2. Via .env file loaded by llm_config_from_env("path/to/.env")
  3. Via environment variables (ANTHROPIC_API_KEY / OPENAI_API_KEY)

The LLM layer is OPTIONAL — the system works fully without it.
Layers C1/C2/C3 handle the vast majority of matches deterministically.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reconciliation.config import ReconciliationConfig, C5Config
from reconciliation.c5_llm import LLMClient, LLMMatcher, llm_config_from_env
from reconciliation.orchestrator import ReconciliationOrchestrator


def example_1_direct_injection():
    """Method 1: Inject the API key directly in code."""
    config = ReconciliationConfig()

    # Anthropic Claude
    config.c5.provider = "anthropic"
    config.c5.model = "claude-sonnet-4-5"
    config.c5.api_key = "sk-ant-api03-YOUR-KEY-HERE"

    # Or OpenAI
    # config.c5.provider = "openai"
    # config.c5.model = "gpt-4o"
    # config.c5.api_key = "sk-proj-YOUR-KEY-HERE"

    # Optional: custom endpoint (proxies, Azure OpenAI, self-hosted)
    # config.c5.base_url = "https://my-proxy.example.com/v1"

    # Optional: monthly budget cap (USD)
    config.c5.monthly_budget_usd = 100.0

    orch = ReconciliationOrchestrator(config)
    print(f"Orchestrator configured with {config.c5.provider}:{config.c5.model}")
    return orch


def example_2_dotenv_file():
    """Method 2: Load from a .env file at the project root."""
    # First call llm_config_from_env, then assign to main config
    c5 = llm_config_from_env(env_file=".env")
    config = ReconciliationConfig()
    config.c5 = c5

    orch = ReconciliationOrchestrator(config)
    print(f"Orchestrator using key from .env (provider={c5.provider})")
    return orch


def example_3_env_vars():
    """Method 3: Rely on ANTHROPIC_API_KEY / OPENAI_API_KEY env vars.

    This is what happens automatically if you do NOTHING — the LLMClient
    will fall back to env vars if no api_key is explicitly set.
    """
    config = ReconciliationConfig()
    # No api_key set → LLMClient will read ANTHROPIC_API_KEY from env
    orch = ReconciliationOrchestrator(config)
    print("Orchestrator will read API key from environment")
    return orch


def example_4_disable_llm():
    """Method 4: Completely disable the LLM layer.

    Useful when you don't want any external API calls, or for testing.
    The pipeline will still work — unmatched payments go to human review.
    """
    config = ReconciliationConfig()
    config.c5.enabled = False  # kill switch

    orch = ReconciliationOrchestrator(config)
    print("LLM layer disabled — pipeline runs C0-C4 + C6 only")
    return orch


def example_5_test_connectivity():
    """Quick test: verify the API key works by making a minimal call."""
    config = C5Config()
    config.api_key = "sk-ant-YOUR-KEY"
    config.provider = "anthropic"
    config.max_tokens = 50

    client = LLMClient(config)
    result = client.query(
        prompt="Return only the JSON: {\"ok\": true}",
        system="You are a JSON generator. Output only valid JSON, nothing else.",
    )
    if result:
        print(f"LLM responded: {result}")
        print(f"Monthly cost so far: ${client._month_cost_usd:.4f}")
    else:
        print("LLM call failed (check API key / network / billing)")


if __name__ == "__main__":
    print("=" * 60)
    print("LLM API Key configuration examples")
    print("=" * 60)
    print()
    print("Method 1 — Direct injection:")
    example_1_direct_injection()
    print()
    print("Method 4 — Disabled:")
    example_4_disable_llm()
    print()
    print("See the source of this file for examples 2, 3, 5")
    print()
    print("To actually test connectivity, edit this file, set your key,")
    print("then call example_5_test_connectivity() at the bottom.")
