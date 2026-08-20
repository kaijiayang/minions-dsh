#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""minions_bridge.py — Python bridge between DeepSeek Harness and the Minions protocol.

The bridge is the single JSON-over-stdio contract used by the
``dsh-plugin-minions`` DeepSeek Harness tool plugin.

Design principles (strict):
  * Input : a single JSON object read from stdin.
  * Output: exactly one JSON object written to stdout (success or failure).
  * Logs  : all logging / progress / warnings go to stderr so stdout stays
            parseable.

stdin input JSON
----------------
{
  "local_client":  {"type": "openai_compat", "platform": "lmstudio",
                     "model_name": "qwen3-8b", "kwargs": {"base_url": "...", ...}},
  "remote_client": {"type": "deepseek", "model_name": "deepseek-chat",
                    "kwargs": {"api_key": "...", ...}},
  "protocol":      {"type": "minions", "max_rounds": 3, "log_dir": "minion_logs"},
  "call_params":   {"task": "...", "doc_metadata": "...", "context": ["..."]}
}

stdout output JSON
------------------
{"success": true, "result": {"final_answer": "...", "usage": {...}}, "error": null}

Standardized config file
------------------------
Instead of a hand-written stdin payload you can point the bridge at the
project's canonical ``minions.yaml`` (see ``minions/config.py``)::

    python minions_bridge.py --config minions.yaml --call-json payload.json

``call-json`` may be omitted; the bridge then reads the call parameters from
stdin (only ``call_params`` is consumed in config mode).

CLI modes
---------
  * (no args)                 — read the full payload from stdin (back-compat).
  * --config <path>           — load clients/protocol from the config file;
                                call params come from stdin or --call-json.
  * --validate-config <path>  — load + validate the config, print the resolved
                                bridge payload to stdout and exit 0/1.
  * --self-test               — offline sanity check of parsing/configuration.

Standalone smoke test:
  echo '{...}' | python dsh-plugin/python/minions_bridge.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import warnings

# ---------------------------------------------------------------------------
# sys.path bootstrap: make the `minions` package importable when this script
# is run directly (not via the Harness plugin, which sets PYTHONPATH itself).
# The repository root is the parent of the `dsh-plugin` directory.
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ---------------------------------------------------------------------------
# stdout hygiene: keep the original stdout; everything else goes to stderr.
# ---------------------------------------------------------------------------
_original_stdout = sys.stdout

warnings.filterwarnings("ignore")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("PYTHONWARNINGS", "ignore")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(stream=sys.stderr, level=logging.ERROR)


class _StdoutToStderr:
    """Redirect stray ``print`` calls to stderr so stdout stays clean."""

    def __init__(self) -> None:
        self._buffer = []

    def write(self, data: str) -> int:
        if data.strip():
            self._buffer.append(data)
        return len(data)

    def flush(self) -> None:
        if self._buffer:
            sys.stderr.write("".join(self._buffer))
            sys.stderr.flush()
            self._buffer = []

    def isatty(self) -> bool:
        return False


_stdout_capture = _StdoutToStderr()


def _emit_error(message: str, extra: str = None) -> None:
    """Write an error JSON object to stdout and exit non-zero."""
    payload: dict = {"success": False, "result": None, "error": message}
    if extra:
        payload["error_detail"] = extra
    try:
        _original_stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        _original_stdout.flush()
    except Exception:
        pass
    sys.exit(1)


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------

def _create_client(client_config: dict):
    """Build a local/remote client from a bridge client config.

    Supported client types:
      * ``openai_compat`` — any OpenAI-compatible local endpoint
        (LM Studio / Ollama / vLLM / llama.cpp ...). ``platform`` may be one of
        ``lmstudio | ollama | vllm | llamacpp | generic | auto``.
      * ``ollama``, ``docker_model_runner``, ``lemonade`` — local clients.
      * ``openai`` / ``deepseek`` — OpenAI-compatible cloud endpoints.
      * ``anthropic`` — Anthropic cloud endpoint.

    API keys are read from the config / environment — never hard-coded.
    Client modules are imported lazily so a minimal install (openai only)
    is enough for LM Studio + DeepSeek usage.
    """
    client_type = (client_config.get("type") or "ollama").lower()
    kwargs = dict(client_config.get("kwargs") or {})
    model_name = client_config.get("model_name", "") or ""

    if client_type == "openai_compat":
        from minions.clients.openai_compat import OpenAICompatClient
        platform = client_config.get("platform", "auto") or "auto"
        return OpenAICompatClient(
            model_name=model_name,
            platform=platform,
            **kwargs,
        )

    if client_type == "ollama":
        from minions.clients.ollama import OllamaClient
        model_name = model_name or os.getenv("MINIONS_LOCAL_MODEL", "llama3.2:3b")
        return OllamaClient(model_name=model_name, **kwargs)

    if client_type == "docker_model_runner":
        from minions.clients.docker_model_runner import DockerModelRunnerClient
        return DockerModelRunnerClient(
            model_name=model_name or "ai/llama3.2:3B-Q4_0",
            port=client_config.get("port", 12434),
            timeout=client_config.get("timeout", 60),
            **kwargs,
        )

    if client_type == "lemonade":
        from minions.clients.lemonade import LemonadeClient
        return LemonadeClient(model_name=model_name or "llama3.2:3b", **kwargs)

    if client_type in ("openai", "deepseek"):
        from minions.clients.openai import OpenAIClient
        if client_type == "deepseek":
            model_name = model_name or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            base_url = kwargs.pop("base_url", None) or os.getenv(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            )
            api_key = kwargs.pop("api_key", None) or os.getenv("DEEPSEEK_API_KEY")
            return OpenAIClient(
                model_name=model_name,
                api_key=api_key,
                base_url=base_url,
                local=False,
                **kwargs,
            )
        model_name = model_name or os.getenv("MINIONS_REMOTE_MODEL", "deepseek-chat")
        local = bool(kwargs.pop("local", client_config.get("local", False)))
        base_url = kwargs.pop("base_url", None) or os.getenv("OPENAI_BASE_URL")
        api_key = kwargs.pop("api_key", None) or os.getenv("OPENAI_API_KEY")
        return OpenAIClient(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
            local=local,
            **kwargs,
        )

    if client_type == "anthropic":
        from minions.clients.anthropic import AnthropicClient
        model_name = model_name or "claude-3-5-sonnet-20241022"
        return AnthropicClient(model_name=model_name, **kwargs)

    raise ValueError(
        f"Unknown client type {client_type!r}. Supported: "
        "openai_compat/ollama/docker_model_runner/lemonade/openai/deepseek/anthropic"
    )


def _create_protocol(protocol_config: dict, local_client, remote_client):
    """Create the Minions / Minion protocol instance."""
    from minions.minion import Minion
    from minions.minions import Minions

    protocol_type = (protocol_config.get("type") or "minions").lower()
    kwargs = dict(protocol_config.get("kwargs") or {})

    if protocol_type == "minion":
        return Minion(
            local_client=local_client,
            remote_client=remote_client,
            max_rounds=protocol_config.get("max_rounds", 3),
            callback=protocol_config.get("callback"),
            log_dir=protocol_config.get("log_dir", "minion_logs"),
            **kwargs,
        )

    if protocol_type == "minions":
        return Minions(
            local_client=local_client,
            remote_client=remote_client,
            max_rounds=protocol_config.get("max_rounds", 3),
            callback=protocol_config.get("callback"),
            log_dir=protocol_config.get("log_dir", "minion_logs"),
            **kwargs,
        )

    raise ValueError(f"Unknown protocol type {protocol_type!r} (supported: minions/minion)")


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _read_stdin_json() -> dict:
    """Read a UTF-8 (BOM-tolerant) JSON object from stdin."""
    raw_bytes = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read().encode("utf-8")
    raw = raw_bytes.decode("utf-8-sig", errors="replace")
    while raw.startswith("\ufeff"):
        raw = raw[1:]
    if not raw.strip():
        _emit_error("stdin is empty; expected a JSON payload.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        _emit_error(f"stdin is not valid JSON: {e}")


def _run_payload(input_data: dict) -> None:
    """Execute one full bridge payload and write the result JSON to stdout."""
    local_config = input_data.get("local_client") or {"type": "openai_compat", "platform": "lmstudio"}
    remote_config = input_data.get("remote_client") or {"type": "deepseek"}
    protocol_config = input_data.get("protocol") or {"type": "minions"}
    call_params = input_data.get("call_params") or {}

    if "context" not in call_params or not call_params.get("context"):
        _emit_error("call_params.context cannot be empty (must be a list of strings).")
    if not call_params.get("task"):
        _emit_error("call_params.task cannot be empty.")
    # The minions (plural) protocol requires doc_metadata; default when missing.
    if not call_params.get("doc_metadata"):
        call_params["doc_metadata"] = "Generic document"

    local_client = _create_client(local_config)
    remote_client = _create_client(remote_config)
    protocol = _create_protocol(protocol_config, local_client, remote_client)
    result = protocol(**call_params)

    output = {
        "success": True,
        "result": _sanitize_json(_simplify_result(result)),
        "error": None,
    }
    _original_stdout.write(
        json.dumps(output, ensure_ascii=False, default=_json_default, indent=2, allow_nan=False)
    )
    _original_stdout.flush()
    sys.exit(0)


def _run_config_mode(config_path: str, call_params: dict, overrides: dict = None) -> None:
    """Load minions.yaml and execute the protocol with it.

    ``overrides`` may carry per-call overrides: ``local_model``,
    ``remote_model``, ``max_rounds``, ``protocol``.
    """
    from minions.config import load_config

    overrides = overrides or {}
    cfg = load_config(config_path)

    if overrides.get("local_model"):
        cfg.local.model = str(overrides["local_model"])
    if overrides.get("remote_model"):
        cfg.remote.model = str(overrides["remote_model"])
    if overrides.get("protocol") in ("minions", "minion"):
        cfg.protocol.type = overrides["protocol"]
    if overrides.get("max_rounds") is not None:
        cfg.protocol.max_rounds = int(overrides["max_rounds"])

    payload = cfg.to_bridge_payload(call_params=call_params)
    sys.stderr.write(
        f"[bridge] loaded config {os.path.abspath(config_path)}; "
        f"local={cfg.local.platform}/{cfg.local.model}, "
        f"remote={cfg.remote.provider}/{cfg.remote.model}, "
        f"protocol={cfg.protocol.type} (max_rounds={cfg.protocol.max_rounds})\n"
    )
    _run_payload(payload)


def _validate_config(config_path: str) -> None:
    """Load + validate the config and print the resolved payload to stdout."""
    from minions.config import load_config

    cfg = load_config(config_path)
    payload = cfg.to_bridge_payload(
        call_params={"task": "<example>", "context": ["<example>"]}
    )
    _original_stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    _original_stdout.flush()
    sys.exit(0)


def _self_test() -> None:
    """Offline self-check that does not touch any model server."""
    sys.stderr.write("[self-test] minions_bridge self-test...\n")

    # 1. Invalid JSON must be rejected
    try:
        json.loads("not-json")
        raise AssertionError("expected JSONDecodeError")
    except json.JSONDecodeError:
        sys.stderr.write("[self-test] invalid JSON rejected OK\n")

    # 2. Client construction for openai_compat (no server contact)
    from minions.clients.openai_compat import OpenAICompatClient, resolve_platform
    base, key = resolve_platform("ollama")
    assert base == "http://127.0.0.1:11434/v1", base
    sys.stderr.write("[self-test] platform resolution OK\n")

    # 3. Config module round-trip (no file needed)
    from minions.config import parse_config
    cfg = parse_config(
        {
            "version": 1,
            "local": {"platform": "lmstudio", "model": "qwen3-8b"},
            "remote": {"provider": "deepseek", "model": "deepseek-chat"},
            "protocol": {"type": "minions", "max_rounds": 2},
        }
    )
    payload = cfg.to_bridge_payload({"task": "t", "context": ["c"]})
    assert payload["local_client"]["type"] == "openai_compat"
    assert payload["protocol"]["max_rounds"] == 2
    assert payload["call_params"]["task"] == "t"
    sys.stderr.write("[self-test] config round-trip OK\n")

    # 4. stdout stays clean
    _original_stdout.write(json.dumps({"success": True, "result": "ok", "error": None}, ensure_ascii=False))
    _original_stdout.flush()
    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Minions bridge (JSON over stdio)")
    parser.add_argument("--config", help="Path to the standardized minions.yaml config file")
    parser.add_argument(
        "--call-json",
        help="Path to a JSON file holding only the call_params (config mode). "
        "Defaults to reading call_params from stdin.",
    )
    parser.add_argument("--validate-config", metavar="PATH", help="Validate a config file and print the resolved payload")
    parser.add_argument("--self-test", action="store_true", help="Run the offline self-test")
    args = parser.parse_args()

    # Redirect all stray prints (including `minions` package import warnings)
    # to stderr BEFORE importing anything from minions, so stdout stays pure
    # JSON. Final results are written to _original_stdout explicitly.
    _stdout_capture._buffer = []
    old_stdout = sys.stdout
    sys.stdout = _stdout_capture
    try:
        if args.self_test:
            _self_test()
        if args.validate_config:
            _validate_config(args.validate_config)

        if args.config:
            stdin_data = {}
            if args.call_json:
                with open(args.call_json, encoding="utf-8") as fh:
                    stdin_data = json.load(fh)
            else:
                stdin_data = _read_stdin_json()
            call_params = stdin_data.get("call_params") or {}
            overrides = stdin_data.get("overrides") or {}
            _run_config_mode(args.config, call_params, overrides)
        else:
            _run_payload(_read_stdin_json())
    finally:
        _stdout_capture.flush()
        sys.stdout = old_stdout


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _simplify_result(result):
    """Keep only the key fields of a protocol result."""
    if not isinstance(result, dict):
        return result
    allowed = {
        "final_answer",
        "usage",
        "local_usage",
        "remote_usage",
        "final_messages",
        "supervisor_messages",
        "worker_messages",
        "session_id",
        "log_file",
    }
    out = {}
    for key in allowed:
        if key in result:
            out[key] = result[key]
    return out


def _sanitize_json(obj):
    """Recursively clean non-standard JSON values (NaN/Infinity -> None)."""
    import math

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    if isinstance(obj, str):
        return obj
    if obj is None or isinstance(obj, bool):
        return obj
    return _sanitize_json(_json_default(obj))


def _json_default(obj):
    """JSON fallback serializer for dataclass/pydantic/arbitrary objects."""
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if isinstance(obj, dict):
        return {k: _json_default(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_default(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return {k: _json_default(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    return str(obj)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        import traceback
        _emit_error(str(e), extra=traceback.format_exc())
