# Changelog

All notable changes to **minions-dsh** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2025-07-01

### Added

- **Unified OpenAI-compatible local client** (`minions/clients/openai_compat.py`)
  with platform presets for **LM Studio**, **Ollama**, **vLLM**, **llama.cpp**
  and arbitrary `generic` OpenAI-compatible endpoints. No vendor SDKs needed.
- **Standardized configuration system** (`minions/config.py`): canonical
  `minions.yaml` (YAML/JSON), `${ENV_VAR}` expansion, `api_key_env` secret
  indirection, validation with actionable errors, and a JSON Schema
  (`config.schema.json`).
- **Bridge CLI modes**: `--config`, `--validate-config`, `--self-test`;
  per-call `overrides` (model / rounds / protocol) in config mode.
- **Harness plugin updates**: `local_platform` tool parameter, `configFile`
  support, portable secret-free `cordis.yml` template, fixed package metadata.
- **Open-source project scaffolding**: README (EN + zh-CN), `CONTRIBUTING.md`,
  `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, `docs/` (architecture,
  configuration, local servers, plugin, development, troubleshooting),
  `examples/configs/`, `.env.example`, `pyproject.toml` packaging, unit tests.

### Changed

- Replaced the ad-hoc local OpenAI client usage with the unified
  `openai_compat` client across the plugin and bridge.
- `setup.py` replaced by `pyproject.toml` (setuptools backend; still
  `pip install -e .`).

### Fixed

- Removed a hard-coded API key and machine-specific absolute paths from
  `dsh-plugin/cordis.yml`.
- Bridge script now bootstraps `sys.path` so it can be run directly from any
  working directory.

## [1.0.0] - 2025-06-01

### Added

- Initial DeepSeek Harness tool plugin (`dsh-plugin`) bridging to the Minions
  hierarchical multi-model collaboration protocol.
- `minions_run` tool: task decomposition by the cloud supervisor, execution by
  the local worker, JSON-over-stdio subprocess bridge.

---

## Upstream

This project is built on the MIT-licensed
[HazyResearch/minions](https://github.com/HazyResearch/minions) protocol
library. See the upstream repository for its history.
