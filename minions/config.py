"""Standardized configuration for minions-dsh.

This module defines the canonical ``minions.yaml`` configuration schema and
provides a loader that supports:

* **YAML or JSON** config files (YAML preferred; JSON accepted transparently).
* **Environment-variable expansion** — any string value may reference an
  environment variable with ``${VAR_NAME}`` syntax, and endpoints may point at
  their secret via ``api_key_env``.
* **Validation** with actionable error messages.

The canonical file is ``minions.yaml`` at the repository root::

    # minions.yaml
    version: 1

    remote:                      # cloud supervisor (decomposes & synthesizes)
      provider: deepseek         # deepseek | openai | anthropic | openai_compat
      model: deepseek-chat
      base_url: https://api.deepseek.com/v1
      api_key_env: DEEPSEEK_API_KEY

    local:                       # local worker (reads long context)
      platform: lmstudio         # lmstudio | ollama | vllm | llamacpp | generic | auto
      model: qwen3-8b
      base_url: http://127.0.0.1:1234/v1

    protocol:
      type: minions              # minions | minion
      max_rounds: 3
      log_dir: minion_logs

    plugin:                      # DeepSeek Harness plugin options (optional)
      bridge_python: python
      timeout_ms: 300000

See ``docs/CONFIGURATION.md`` for the full reference.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # PyYAML is optional; JSON configs always work.
    import yaml as _yaml
except ImportError:  # pragma: no cover - depends on environment
    _yaml = None

# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class ConfigError(ValueError):
    """Raised when a configuration file is invalid or cannot be loaded."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class EndpointConfig:
    """One LLM endpoint (the cloud supervisor or the local worker)."""

    kind: str  # "local" | "remote"
    provider: str  # for remote: deepseek | openai | anthropic | openai_compat | ...
    platform: str = "auto"  # for local: lmstudio | ollama | vllm | llamacpp | generic | auto
    model: str = ""
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_key_env: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 2048
    extra: Dict[str, Any] = field(default_factory=dict)

    def resolved_api_key(self) -> Optional[str]:
        """Return the API key, honouring ``api_key_env``."""
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            value = os.getenv(self.api_key_env)
            if value is None:
                raise ConfigError(
                    f"Environment variable {self.api_key_env!r} referenced by "
                    f"{self.kind}.api_key_env is not set."
                )
            return value
        return None

    def to_client_dict(self) -> Dict[str, Any]:
        """Serialize to the bridge ``client_config`` JSON shape."""
        if self.kind == "local":
            out: Dict[str, Any] = {
                "type": "openai_compat",
                "platform": self.platform,
                "model_name": self.model,
            }
        else:
            out = {"type": self.provider, "model_name": self.model}

        kwargs: Dict[str, Any] = dict(self.extra)
        if self.base_url:
            kwargs["base_url"] = self.base_url
        api_key = self.resolved_api_key()
        if api_key:
            kwargs["api_key"] = api_key
        kwargs.setdefault("temperature", self.temperature)
        kwargs.setdefault("max_tokens", self.max_tokens)
        out["kwargs"] = kwargs
        return out


@dataclass
class ProtocolConfig:
    type: str = "minions"
    max_rounds: int = 3
    log_dir: str = "minion_logs"
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginConfig:
    """Options for the DeepSeek Harness plugin (used by dsh-plugin)."""

    bridge_python: str = "python"
    bridge_script: str = "python/minions_bridge.py"
    timeout_ms: int = 300_000
    max_buffer: int = 20 * 1024 * 1024
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MinionsConfig:
    version: int = 1
    local: EndpointConfig = field(default_factory=lambda: EndpointConfig("local"))
    remote: EndpointConfig = field(default_factory=lambda: EndpointConfig("remote"))
    protocol: ProtocolConfig = field(default_factory=ProtocolConfig)
    plugin: PluginConfig = field(default_factory=PluginConfig)

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_bridge_payload(self, call_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build the JSON payload consumed by ``dsh-plugin/python/minions_bridge.py``."""
        return {
            "local_client": self.local.to_client_dict(),
            "remote_client": self.remote.to_client_dict(),
            "protocol": {
                "type": self.protocol.type,
                "max_rounds": self.protocol.max_rounds,
                "log_dir": self.protocol.log_dir,
                **self.protocol.extra,
            },
            "call_params": call_params or {},
            "plugin": self.plugin.__dict__,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "local": {
                "platform": self.local.platform,
                "model": self.local.model,
                "base_url": self.local.base_url,
                "api_key": self.local.api_key,
                "api_key_env": self.local.api_key_env,
                "temperature": self.local.temperature,
                "max_tokens": self.local.max_tokens,
                **self.local.extra,
            },
            "remote": {
                "provider": self.remote.provider,
                "model": self.remote.model,
                "base_url": self.remote.base_url,
                "api_key": self.remote.api_key,
                "api_key_env": self.remote.api_key_env,
                "temperature": self.remote.temperature,
                "max_tokens": self.remote.max_tokens,
                **self.remote.extra,
            },
            "protocol": self.protocol.__dict__,
            "plugin": self.plugin.__dict__,
        }


# ---------------------------------------------------------------------------
# Loading & validation
# ---------------------------------------------------------------------------

_DEFAULT_FILENAMES = ("minions.yaml", "minions.yml", "minions.json")


def _expand_env(value: Any) -> Any:
    """Recursively expand ``${VAR}`` / ``$VAR`` references in strings."""
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def _parse_text(text: str, path: Path) -> Dict[str, Any]:
    text = text.lstrip("\ufeff")
    try:
        if _yaml is not None:
            return _yaml.safe_load(text) or {}
        return json.loads(text)
    except Exception as e:
        if _yaml is None and (path.suffix in (".yaml", ".yml")):
            raise ConfigError(
                f"Cannot parse {path}: PyYAML is not installed. "
                "Install it with `pip install pyyaml` or use a JSON config."
            ) from e
        raise ConfigError(f"Cannot parse config file {path}: {e}") from e


def find_config_file(path: Optional[str] = None) -> Optional[Path]:
    """Locate the config file.

    Resolution order:
      1. Explicit ``path`` argument — if it does not exist, raise immediately
         (an explicit path must never silently fall back).
      2. ``MINIONS_CONFIG`` environment variable.
      3. ``minions.yaml`` / ``minions.yml`` / ``minions.json`` in the current
         working directory.
      4. Same filenames at the repository root (parent of this package).
    """
    if path:
        explicit = Path(path)
        if not explicit.is_file():
            raise ConfigError(f"Config file not found: {path}")
        return explicit

    candidates: List[Path] = []
    if os.getenv("MINIONS_CONFIG"):
        candidates.append(Path(os.getenv("MINIONS_CONFIG")))  # type: ignore[arg-type]
    for name in _DEFAULT_FILENAMES:
        candidates.append(Path.cwd() / name)
        candidates.append(Path(__file__).resolve().parent.parent / name)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_config(path: Optional[str] = None) -> MinionsConfig:
    """Load and validate a ``minions.yaml`` (or JSON) configuration file.

    Raises:
        ConfigError: if the file cannot be found, parsed, or validated.
    """
    cfg_path = find_config_file(path)
    if cfg_path is None:
        raise ConfigError(
            "No configuration file found. Create minions.yaml at the repository "
            "root (see examples/configs/) or set the MINIONS_CONFIG env var."
        )

    raw = _parse_text(cfg_path.read_text(encoding="utf-8"), cfg_path)
    return parse_config(raw, source=str(cfg_path))


def parse_config(raw: Dict[str, Any], source: str = "<dict>") -> MinionsConfig:
    """Validate a raw config dict and build a :class:`MinionsConfig`.

    ``${VAR}`` / ``$VAR`` references are expanded from the environment before
    validation, so callers can pass either file contents or plain dicts.
    """
    if not isinstance(raw, dict):
        raise ConfigError(f"Config root must be a mapping, got {type(raw).__name__}")

    raw = _expand_env(raw)

    version = raw.get("version", 1)
    if version != 1:
        raise ConfigError(
            f"Unsupported config version {version!r} (expected 1) in {source}."
        )

    local_raw = raw.get("local") or {}
    remote_raw = raw.get("remote") or {}
    protocol_raw = raw.get("protocol") or {}
    plugin_raw = raw.get("plugin") or {}

    if not isinstance(local_raw, dict) or not isinstance(remote_raw, dict):
        raise ConfigError("'local' and 'remote' sections must be mappings.")

    local = _parse_endpoint(local_raw, kind="local", source=source)
    remote = _parse_endpoint(remote_raw, kind="remote", source=source)

    if not local.model:
        raise ConfigError(f"'local.model' is required ({source}).")
    if not remote.model:
        raise ConfigError(f"'remote.model' is required ({source}).")

    protocol_type = str(protocol_raw.get("type", "minions")).lower()
    if protocol_type not in ("minions", "minion"):
        raise ConfigError(
            f"protocol.type must be 'minions' or 'minion', got {protocol_type!r}."
        )
    try:
        max_rounds = int(protocol_raw.get("max_rounds", 3))
    except (TypeError, ValueError):
        raise ConfigError("protocol.max_rounds must be an integer.")
    if max_rounds < 1:
        raise ConfigError("protocol.max_rounds must be >= 1.")

    protocol = ProtocolConfig(
        type=protocol_type,
        max_rounds=max_rounds,
        log_dir=str(protocol_raw.get("log_dir", "minion_logs")),
        extra={k: v for k, v in protocol_raw.items() if k not in ("type", "max_rounds", "log_dir")},
    )

    plugin = PluginConfig(
        bridge_python=str(plugin_raw.get("bridge_python", "python")),
        bridge_script=str(plugin_raw.get("bridge_script", "python/minions_bridge.py")),
        timeout_ms=int(plugin_raw.get("timeout_ms", 300_000)),
        max_buffer=int(plugin_raw.get("max_buffer", 20 * 1024 * 1024)),
        extra={k: v for k, v in plugin_raw.items() if k not in PluginConfig.__dataclass_fields__},
    )

    return MinionsConfig(
        version=version, local=local, remote=remote, protocol=protocol, plugin=plugin
    )


def _parse_endpoint(raw: Dict[str, Any], kind: str, source: str) -> EndpointConfig:
    known = {
        "model",
        "base_url",
        "api_key",
        "api_key_env",
        "temperature",
        "max_tokens",
        # local-only keys
        "platform",
        # remote-only keys
        "provider",
    }

    if kind == "local":
        platform = str(raw.get("platform", "auto")).lower()
        if platform not in ("auto", "lmstudio", "ollama", "vllm", "llamacpp", "generic"):
            raise ConfigError(
                f"local.platform must be one of lmstudio/ollama/vllm/llamacpp/"
                f"generic/auto, got {platform!r} ({source})."
            )
        provider = "openai_compat"
    else:
        platform = "auto"
        provider = str(raw.get("provider", "openai")).lower()
        if provider not in ("deepseek", "openai", "anthropic", "openai_compat", "ollama", "openrouter", "groq", "together"):
            raise ConfigError(
                f"Unsupported remote.provider {provider!r} ({source}). Supported: "
                "deepseek/openai/anthropic/openai_compat."
            )

    def _num(key: str, default: float) -> float:
        try:
            return float(raw.get(key, default))
        except (TypeError, ValueError):
            raise ConfigError(f"{kind}.{key} must be a number ({source}).")

    def _int(key: str, default: int) -> int:
        try:
            return int(raw.get(key, default))
        except (TypeError, ValueError):
            raise ConfigError(f"{kind}.{key} must be an integer ({source}).")

    return EndpointConfig(
        kind=kind,
        provider=provider if kind == "remote" else "openai_compat",
        platform=platform,
        model=str(raw.get("model", "")),
        base_url=str(raw["base_url"]) if raw.get("base_url") else None,
        api_key=str(raw["api_key"]) if raw.get("api_key") else None,
        api_key_env=str(raw["api_key_env"]) if raw.get("api_key_env") else None,
        temperature=_num("temperature", 0.0),
        max_tokens=_int("max_tokens", 2048),
        extra={k: v for k, v in raw.items() if k not in known},
    )
