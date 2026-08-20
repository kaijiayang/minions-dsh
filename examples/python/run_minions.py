#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal end-to-end example: cloud supervisor + local worker via Python API.

Requires:
  * a running local model server (LM Studio / Ollama / vLLM ...), and
  * a cloud API key in the environment (e.g. DEEPSEEK_API_KEY).

Run:
    export DEEPSEEK_API_KEY=sk-...
    python examples/python/run_minions.py
"""

import os
import sys

# Make the repo root importable when running from anywhere.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from minions.clients.openai_compat import OpenAICompatClient  # noqa: E402
from minions.clients.openai import OpenAIClient  # noqa: E402
from minions.minions import Minions  # noqa: E402


def main() -> None:
    # --- Local worker: any OpenAI-compatible server -----------------------
    # platform: lmstudio | ollama | vllm | llamacpp | generic | auto
    local = OpenAICompatClient(model_name="qwen3.8-27b", platform="lmstudio")

    # --- Cloud supervisor --------------------------------------------------
    remote = OpenAIClient(
        model_name=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        local=False,
    )

    minions = Minions(local_client=local, remote_client=remote, max_rounds=3)

    context = """
    Minions is a communication protocol that enables small on-device models to
    collaborate with frontier models in the cloud. By only reading long
    contexts locally, we can reduce cloud costs with minimal or no quality
    degradation.
    """

    result = minions(
        task="Summarize the core idea of the Minions protocol in 3 bullet points.",
        doc_metadata="Protocol description",
        context=[context],
    )

    print("=" * 70)
    print("FINAL ANSWER")
    print("=" * 70)
    print(result["final_answer"])
    print("=" * 70)
    if result.get("usage"):
        print("Usage:", result["usage"])
    if result.get("log_file"):
        print("Log file:", result["log_file"])


if __name__ == "__main__":
    main()
