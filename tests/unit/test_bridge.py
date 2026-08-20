"""Unit tests for the JSON-over-stdio bridge (dsh-plugin/python/minions_bridge.py).

The bridge's subprocess modes are exercised directly; the HTTP layer is never
touched (self-test and validate-config modes are offline).
"""

import json
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BRIDGE = os.path.join(REPO_ROOT, "dsh-plugin", "python", "minions_bridge.py")


def _run_bridge(*args, stdin_text=None, env_extra=None, env_remove=None):
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", REPO_ROOT)
    for name in env_remove or []:
        env.pop(name, None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, BRIDGE, *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=120,
    )


def test_self_test_offline():
    proc = _run_bridge("--self-test")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["success"] is True


def test_validate_config_lmstudio_example(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    config = os.path.join(REPO_ROOT, "examples", "configs", "minions.lmstudio.yaml")
    proc = _run_bridge("--validate-config", config)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["local_client"]["type"] == "openai_compat"
    assert payload["local_client"]["platform"] == "lmstudio"
    assert payload["remote_client"]["type"] == "deepseek"
    assert payload["remote_client"]["kwargs"]["api_key"] == "sk-test"
    assert payload["protocol"]["type"] == "minions"


def test_validate_config_ollama_example():
    config = os.path.join(REPO_ROOT, "examples", "configs", "minions.ollama.yaml")
    proc = _run_bridge("--validate-config", config, env_extra={"DEEPSEEK_API_KEY": "sk-test"})
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["local_client"]["platform"] == "ollama"
    assert payload["local_client"]["model_name"] == "qwen3:8b"


def test_validate_config_vllm_example():
    config = os.path.join(REPO_ROOT, "examples", "configs", "minions.vllm.yaml")
    proc = _run_bridge("--validate-config", config, env_extra={"DEEPSEEK_API_KEY": "sk-test"})
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["local_client"]["platform"] == "vllm"


def test_missing_config_errors():
    proc = _run_bridge("--validate-config", os.path.join(REPO_ROOT, "nope.yaml"))
    assert proc.returncode != 0
    out = json.loads(proc.stdout)
    assert out["success"] is False
    assert "Config file not found" in out["error"]


def test_missing_api_key_env_errors():
    config = os.path.join(REPO_ROOT, "examples", "configs", "minions.lmstudio.yaml")
    proc = _run_bridge("--validate-config", config, env_remove=["DEEPSEEK_API_KEY"])
    # DEEPSEEK_API_KEY referenced by api_key_env is unset in this env
    assert proc.returncode != 0
    out = json.loads(proc.stdout)
    assert "DEEPSEEK_API_KEY" in out["error"]


def test_stdout_clean_on_config_mode():
    """Config mode with a mock payload must keep stdout strictly JSON."""
    config = os.path.join(REPO_ROOT, "examples", "configs", "minions.ollama.yaml")
    stdin_text = json.dumps(
        {"call_params": {"task": "t", "context": ["c"]}, "overrides": {"max_rounds": 1}}
    )
    proc = _run_bridge("--config", config, stdin_text=stdin_text, env_extra={"DEEPSEEK_API_KEY": "sk-test"})
    # Without a live local server this fails at the health check — but stdout
    # must still be a single JSON object, never mixed with logs.
    out = json.loads(proc.stdout)
    assert out["success"] is False
    assert "not running or reachable" in out["error"]
