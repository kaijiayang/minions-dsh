"""OpenAI-compatible client for locally deployed model servers.

This client talks to any local model server that exposes an **OpenAI-compatible
``/v1/chat/completions``** API, including:

* `LM Studio <https://lmstudio.ai>`_ (``http://127.0.0.1:1234/v1``)
* `Ollama <https://ollama.com>`_ OpenAI-compatible endpoint (``http://127.0.0.1:11434/v1``)
* `vLLM <https://docs.vllm.ai>`_ (``http://127.0.0.1:8000/v1``)
* `llama.cpp server <https://github.com/ggml-org/llama.cpp>`_ (``http://127.0.0.1:8080/v1``)
* any other server implementing the OpenAI chat-completions protocol

Usage::

    from minions.clients.openai_compat import OpenAICompatClient

    # LM Studio
    client = OpenAICompatClient(model_name="qwen3-8b", platform="lmstudio")

    # Ollama (OpenAI-compatible endpoint)
    client = OpenAICompatClient(model_name="qwen3:8b", platform="ollama")

    # vLLM
    client = OpenAICompatClient(model_name="Qwen/Qwen3-8B", platform="vllm")

    # Any custom endpoint
    client = OpenAICompatClient(
        model_name="my-model",
        base_url="http://127.0.0.1:8080/v1",
        api_key="no-key",
    )

The :class:`OpenAICompatClient` returns the same 3-tuple
``(responses, usage, done_reasons)`` as other local clients, so it drops
straight into the Minions / Minion protocols as the *local worker*.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

from minions.clients.base import MinionsClient
from minions.usage import Usage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Platform presets
# ---------------------------------------------------------------------------

@dataclass
class PlatformPreset:
    """Default connection settings for a known local model platform."""

    name: str
    base_url: str
    api_key: str
    description: str


PLATFORM_PRESETS: Dict[str, PlatformPreset] = {
    "lmstudio": PlatformPreset(
        name="lmstudio",
        base_url="http://127.0.0.1:1234/v1",
        api_key="lm-studio",
        description="LM Studio Local Inference Server",
    ),
    "ollama": PlatformPreset(
        name="ollama",
        base_url="http://127.0.0.1:11434/v1",
        api_key="ollama",
        description="Ollama OpenAI-compatible endpoint (/v1)",
    ),
    "vllm": PlatformPreset(
        name="vllm",
        base_url="http://127.0.0.1:8000/v1",
        api_key="EMPTY",
        description="vLLM OpenAI-compatible server",
    ),
    "llamacpp": PlatformPreset(
        name="llamacpp",
        base_url="http://127.0.0.1:8080/v1",
        api_key="no-key",
        description="llama.cpp server (OpenAI-compatible)",
    ),
    "generic": PlatformPreset(
        name="generic",
        base_url="",
        api_key="local",
        description="Any custom OpenAI-compatible endpoint (base_url is required)",
    ),
}

#: Platforms that are known to expose an OpenAI-compatible API.
SUPPORTED_PLATFORMS = tuple(PLATFORM_PRESETS.keys())


def resolve_platform(
    platform: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """Resolve a platform name / explicit endpoint into ``(base_url, api_key)``.

    Args:
        platform: One of :data:`SUPPORTED_PLATFORMS`, or ``"auto"``.
        base_url: Explicit endpoint (``http://host:port/v1``). Takes priority.
        api_key: Explicit API key (some servers require one, most accept any).

    Returns:
        A ``(base_url, api_key)`` pair. ``base_url`` may be ``None`` if the
        platform preset has no default and none was supplied.
    """
    name = (platform or "auto").lower().strip()

    if base_url:
        # An explicit endpoint always wins.
        resolved_base = base_url.rstrip("/")
        resolved_key = api_key or "local"
        return resolved_base, resolved_key

    if name == "auto":
        # No explicit endpoint and no preset name: fall back to LM Studio,
        # the most common local OpenAI-compatible server.
        preset = PLATFORM_PRESETS["lmstudio"]
        logger.info("platform='auto' and no base_url: defaulting to %s", preset.description)
        return preset.base_url, preset.api_key

    preset = PLATFORM_PRESETS.get(name)
    if preset is None:
        raise ValueError(
            f"Unknown local platform {platform!r}. Supported platforms: "
            f"{', '.join(SUPPORTED_PLATFORMS)}. "
            "Alternatively pass an explicit base_url pointing at any "
            "OpenAI-compatible endpoint."
        )
    if not preset.base_url:
        raise ValueError(
            f"Platform {name!r} requires an explicit base_url "
            "(it has no default endpoint)."
        )
    return preset.base_url, api_key or preset.api_key


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class OpenAICompatClient(MinionsClient):
    """Chat client for any OpenAI-compatible local model server.

    Args:
        model_name: Model id as exposed by the server (e.g. ``qwen3-8b`` in
            LM Studio, ``qwen3:8b`` in Ollama, ``Qwen/Qwen3-8B`` in vLLM).
        platform: One of :data:`SUPPORTED_PLATFORMS` (``lmstudio``, ``ollama``,
            ``vllm``, ``llamacpp``, ``generic``) or ``"auto"``. Ignored when
            ``base_url`` is provided explicitly.
        base_url: OpenAI-compatible endpoint, e.g. ``http://127.0.0.1:1234/v1``.
            Overrides the platform default.
        api_key: API key for the endpoint. Most local servers ignore it, so a
            placeholder is fine. Defaults to the platform preset value, or to
            ``OPENAI_COMPAT_API_KEY`` / ``OPENAI_API_KEY`` env vars.
        temperature: Sampling temperature.
        max_tokens: Maximum number of tokens to generate. Local servers
            commonly expect ``max_tokens`` (not ``max_completion_tokens``).
        verify_server: If ``True`` (default), probe ``GET /models`` at
            construction time and raise a clear error when the server is not
            reachable.
        **kwargs: Extra keyword arguments forwarded to ``chat.completions.create``
            on every call (e.g. ``top_p``, ``response_format``).
    """

    def __init__(
        self,
        model_name: str,
        platform: str = "auto",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        verify_server: bool = True,
        **kwargs,
    ):
        base_url, api_key = resolve_platform(platform, base_url, api_key)

        super().__init__(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
            base_url=base_url,
            local=True,
            **kwargs,
        )

        self.platform = (platform or "auto").lower()
        self.api_key = (
            api_key
            or os.getenv("OPENAI_COMPAT_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or "local"
        )
        # Persistent per-call defaults (e.g. top_p, response_format) that were
        # passed as **kwargs to the constructor.
        self._default_kwargs = {k: v for k, v in kwargs.items()}
        self.base_url = base_url or os.getenv(
            "OPENAI_COMPAT_BASE_URL", os.getenv("OPENAI_BASE_URL")
        )
        if not self.base_url:
            raise ValueError(
                "No base_url resolved. Provide base_url, a known platform "
                f"({', '.join(SUPPORTED_PLATFORMS)}), or set "
                "OPENAI_COMPAT_BASE_URL."
            )
        self.base_url = self.base_url.rstrip("/")

        # Import lazily so that importing this module never requires `openai`.
        import openai

        self._openai = openai
        self.client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)

        if verify_server:
            self.check_server_health()

    # ------------------------------------------------------------------
    # Health / introspection
    # ------------------------------------------------------------------

    def check_server_health(self) -> Dict[str, Any]:
        """Probe the server's ``GET /v1/models`` endpoint.

        Raises:
            RuntimeError: if the server is not reachable, with actionable hints.
        """
        url = f"{self.base_url}/models"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(
                f"OpenAI-compatible server at {self.base_url} is not running or "
                f"reachable. ({e})\n"
                f"Start your local server first:\n"
                f"  - LM Studio : Local Server tab -> Start Server\n"
                f"  - Ollama    : ollama serve\n"
                f"  - vLLM      : vllm serve <model> --api-key EMPTY\n"
                f"  - llama.cpp : llama-server -m <model>.gguf\n"
                f"Then check {url}."
            ) from e

    def list_models(self) -> Dict[str, Any]:
        """List the models exposed by the server (``GET /v1/models``)."""
        try:
            response = self.client.models.list()
            return {
                "object": "list",
                "data": [model.model_dump() for model in response.data],
            }
        except Exception as e:
            self.logger.error(f"Failed to list models from {self.base_url}: {e}")
            raise

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: Union[List[Dict[str, Any]], List[List[Dict[str, Any]]]],
        **kwargs,
    ) -> Tuple[List[str], Usage, List[str]]:
        """Run chat completion(s) against the local server.

        Supports two shapes:
          * a single conversation: ``[{"role": ..., "content": ...}, ...]``
            -> one API call, returns a 1-element response list;
          * a batch of conversations: ``[[{...}], [{...}], ...]`` (list of
            lists, as produced by the parallel Minions protocol for multiple
            worker chunks) -> one API call per conversation, returns one
            response per conversation.

        Returns:
            ``(responses, usage, done_reasons)`` — the 3-tuple expected from
            local clients by the Minions / Minion protocols.
        """
        # Batch mode: each element is its own single-message conversation.
        if messages and isinstance(messages[0], list):
            responses: List[str] = []
            done_reasons: List[str] = []
            total_usage = Usage(prompt_tokens=0, completion_tokens=0)
            for batch in messages:
                resp, usage, reasons = self._chat_once(batch, **kwargs)
                responses.extend(resp)
                done_reasons.extend(reasons)
                total_usage += usage
            return responses, total_usage, done_reasons
        # Single conversation mode.
        return self._chat_once(messages, **kwargs)

    def _chat_once(
        self,
        messages: List[Dict[str, Any]],
        **kwargs,
    ) -> Tuple[List[str], Usage, List[str]]:
        """Run one chat completion for a single conversation."""
        assert len(messages) > 0, "Messages cannot be empty."

        # Local servers historically expect `max_tokens` rather than
        # OpenAI's `max_completion_tokens`. Allow per-call override.
        max_tokens = kwargs.pop("max_tokens", self.max_tokens)

        # Merge persistent extra params (constructor kwargs) with per-call kwargs.
        params: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": self.temperature,
            **getattr(self, "_default_kwargs", {}),
            **kwargs,
        }

        try:
            response = self.client.chat.completions.create(**params)
        except Exception as e:
            self.logger.error(f"OpenAI-compatible call to {self.base_url} failed: {e}")
            raise

        if response.usage is None:
            usage = Usage(prompt_tokens=0, completion_tokens=0)
        else:
            usage = Usage(
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
            )

        responses = [choice.message.content for choice in response.choices]
        done_reasons = [choice.finish_reason for choice in response.choices]
        return responses, usage, done_reasons
