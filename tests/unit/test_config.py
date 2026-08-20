"""Unit tests for the standardized configuration system (minions/config.py)."""

import os

import pytest

from minions.config import (
    ConfigError,
    load_config,
    parse_config,
)


# ---------------------------------------------------------------------------
# parse_config
# ---------------------------------------------------------------------------


def test_parse_config_minimal():
    cfg = parse_config(
        {
            "version": 1,
            "local": {"platform": "lmstudio", "model": "qwen3-8b"},
            "remote": {"provider": "deepseek", "model": "deepseek-chat"},
        }
    )
    assert cfg.local.platform == "lmstudio"
    assert cfg.local.model == "qwen3-8b"
    assert cfg.remote.provider == "deepseek"
    assert cfg.remote.model == "deepseek-chat"
    assert cfg.protocol.type == "minions"
    assert cfg.protocol.max_rounds == 3


def test_parse_config_protocol():
    cfg = parse_config(
        {
            "version": 1,
            "local": {"model": "m"},
            "remote": {"model": "r"},
            "protocol": {"type": "minion", "max_rounds": 5, "log_dir": "logs"},
        }
    )
    assert cfg.protocol.type == "minion"
    assert cfg.protocol.max_rounds == 5
    assert cfg.protocol.log_dir == "logs"


def test_parse_config_bad_version():
    with pytest.raises(ConfigError, match="Unsupported config version"):
        parse_config({"version": 2, "local": {}, "remote": {}})


def test_parse_config_missing_model():
    with pytest.raises(ConfigError, match="local.model"):
        parse_config({"version": 1, "local": {"platform": "lmstudio"}, "remote": {"model": "r"}})


def test_parse_config_bad_protocol():
    with pytest.raises(ConfigError, match="protocol.type"):
        parse_config(
            {
                "version": 1,
                "local": {"model": "m"},
                "remote": {"model": "r"},
                "protocol": {"type": "bogus"},
            }
        )


def test_parse_config_bad_platform():
    with pytest.raises(ConfigError, match="local.platform"):
        parse_config(
            {"version": 1, "local": {"platform": "bogus", "model": "m"}, "remote": {"model": "r"}}
        )


def test_parse_config_bad_provider():
    with pytest.raises(ConfigError, match="remote.provider"):
        parse_config(
            {"version": 1, "local": {"model": "m"}, "remote": {"provider": "bogus", "model": "r"}}
        )


# ---------------------------------------------------------------------------
# api_key_env resolution
# ---------------------------------------------------------------------------


def test_api_key_env_resolution(monkeypatch):
    monkeypatch.setenv("MY_TEST_KEY", "secret-value")
    cfg = parse_config(
        {
            "version": 1,
            "local": {"model": "m"},
            "remote": {"model": "r", "api_key_env": "MY_TEST_KEY"},
        }
    )
    assert cfg.remote.resolved_api_key() == "secret-value"


def test_api_key_env_missing(monkeypatch):
    monkeypatch.delenv("MY_MISSING_KEY", raising=False)
    cfg = parse_config(
        {
            "version": 1,
            "local": {"model": "m"},
            "remote": {"model": "r", "api_key_env": "MY_MISSING_KEY"},
        }
    )
    with pytest.raises(ConfigError, match="MY_MISSING_KEY"):
        cfg.remote.resolved_api_key()


# ---------------------------------------------------------------------------
# ${ENV} expansion
# ---------------------------------------------------------------------------


def test_env_var_expansion(monkeypatch):
    monkeypatch.setenv("TEST_BASE_URL", "http://127.0.0.1:9999/v1")
    cfg = parse_config(
        {
            "version": 1,
            "local": {"model": "m", "base_url": "${TEST_BASE_URL}"},
            "remote": {"model": "r"},
        }
    )
    assert cfg.local.base_url == "http://127.0.0.1:9999/v1"


# ---------------------------------------------------------------------------
# to_bridge_payload
# ---------------------------------------------------------------------------


def test_to_bridge_payload_shape(monkeypatch):
    monkeypatch.setenv("K", "v")
    cfg = parse_config(
        {
            "version": 1,
            "local": {"platform": "ollama", "model": "qwen3:8b"},
            "remote": {"provider": "deepseek", "model": "deepseek-chat", "api_key_env": "K"},
            "protocol": {"type": "minions", "max_rounds": 2},
        }
    )
    payload = cfg.to_bridge_payload({"task": "t", "context": ["c"]})
    assert payload["local_client"]["type"] == "openai_compat"
    assert payload["local_client"]["platform"] == "ollama"
    assert payload["local_client"]["model_name"] == "qwen3:8b"
    assert payload["remote_client"]["type"] == "deepseek"
    assert payload["remote_client"]["kwargs"]["api_key"] == "v"
    assert payload["protocol"]["max_rounds"] == 2
    assert payload["call_params"]["task"] == "t"


# ---------------------------------------------------------------------------
# load_config (file based)
# ---------------------------------------------------------------------------


def test_load_config_from_json(tmp_path):
    cfg_file = tmp_path / "minions.json"
    cfg_file.write_text(
        '{"version": 1, "local": {"model": "m"}, "remote": {"model": "r"}}',
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_file))
    assert cfg.local.model == "m"
    assert cfg.remote.model == "r"


def test_load_config_yaml_round_trip(tmp_path):
    pytest.importorskip("yaml")
    cfg_file = tmp_path / "minions.yaml"
    cfg_file.write_text(
        "version: 1\n"
        "local:\n"
        "  platform: vllm\n"
        "  model: Qwen/Qwen3-8B\n"
        "remote:\n"
        "  provider: openai\n"
        "  model: gpt-4o\n",
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_file))
    assert cfg.local.platform == "vllm"
    assert cfg.local.model == "Qwen/Qwen3-8B"
    assert cfg.remote.provider == "openai"


def test_load_config_missing_file(tmp_path, monkeypatch):
    import minions.config as cfg_module

    monkeypatch.delenv("MINIONS_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg_module, "find_config_file", lambda path=None: None)
    with pytest.raises(ConfigError, match="No configuration file found"):
        load_config(str(tmp_path / "does-not-exist.yaml"))
