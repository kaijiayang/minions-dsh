# minions-dsh

**Cloud LLMs orchestrate. Local small models execute. Your API bill shrinks.**

`minions-dsh` is a [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) plugin (and the Python protocol library behind it) built on top of the [Minions](https://arxiv.org/abs/2502.15964) hierarchical multi-model collaboration protocol from Stanford [HazyResearch](https://hazyresearch.stanford.edu/).

It solves one problem: **long-context / high-volume reasoning is expensive in the cloud.** Instead of streaming every document to a frontier model, `minions-dsh` lets a **cloud LLM (the supervisor)** decompose the task and synthesize the final answer, while a **locally-deployed small model (the worker)** reads the long context and executes the sub-tasks on your own hardware — through the **OpenAI-compatible APIs** exposed by **LM Studio, Ollama, vLLM, llama.cpp**, and any other compatible server.

```
         ┌────────────────────────────────────────────────────┐
         │              DeepSeek Harness (Agent)               │
         │                                                      │
         │   Agent ──calls──► minions_run tool (TS plugin)      │
         │                              │  spawn subprocess      │
         └──────────────────────────────┼───────────────────────┘
                                        ▼
                         Python bridge (minions_bridge.py)
                                        │
         ┌──────────────────────────────┴───────────────────────┐
         ▼                                                      ▼
   Cloud supervisor                                      Local worker
   (DeepSeek / OpenAI / ...)                     (LM Studio / Ollama / vLLM
   decomposes + synthesizes                     reads long context,
   → only compact sub-task                     executes sub-tasks on your
     outputs ever leave your machine)          hardware — costs you nothing
```

- **Paper**: [Minions: Cost-efficient Collaboration Between On-device and Cloud Language Models](https://arxiv.org/pdf/2502.15964)
- **Upstream project**: [HazyResearch/minions](https://github.com/HazyResearch/minions) (MIT)
- **License**: MIT (both this project and the upstream library)

---

## Table of Contents

- [Features](#features)
- [How it works](#how-it-works)
- [Quick start](#quick-start)
  - [1. Install](#1-install)
  - [2. Start a local model server](#2-start-a-local-model-server)
  - [3. Configure](#3-configure)
  - [4. Run](#4-run)
- [DeepSeek Harness plugin](#deepseek-harness-plugin)
- [Local platform support](#local-platform-support)
- [Configuration](#configuration)
- [Command-line interface](#command-line-interface)
- [Project layout](#project-layout)
- [Documentation](#documentation)
- [Development](#development)
- [Security](#security)
- [License](#license)

---

## Features

- 🧠 **Hierarchical multi-model collaboration** — the Minions protocol: a cloud supervisor decomposes the task into sub-tasks, a local worker executes them against the long context, and the supervisor iterates until it can synthesize a final answer.
- 💸 **Cost savings** — the long context never leaves your machine; only compact sub-task outputs go to the cloud, cutting API tokens by up to ~90% in the common case.
- 🖥️ **One client for all local servers** — a single OpenAI-compatible client (`OpenAICompatClient`) with platform presets for **LM Studio**, **Ollama**, **vLLM**, **llama.cpp**, and any custom endpoint.
- 📄 **Standardized configuration** — a canonical `minions.yaml` (JSON Schema available), with `${ENV_VAR}` expansion and `api_key_env` secret indirection. Never hard-code keys.
- 🔌 **DeepSeek Harness plugin** — registers a `minions_run` tool so any Harness agent can delegate long-context work to the local/cloud pair at runtime.
- 🧪 **Tested bridge contract** — strict JSON-in/JSON-out over stdio, offline self-tests, unit tests, and a Node smoke test.

## How it works

The protocol runs in rounds:

1. **Supervisor (cloud)** decomposes the task into `N` sub-tasks (`JobManifest`s).
2. **Worker (local)** reads the context chunks and executes each sub-task, returning structured `{explanation, citation, answer}` outputs.
3. **Supervisor (cloud)** evaluates the outputs; if the information is insufficient, it emits more sub-tasks (next round) — up to `max_rounds` — otherwise it synthesizes the **final answer**.

Both roles are pluggable. The defaults are:

| Role | Default | Typical choice |
|------|---------|----------------|
| Supervisor (remote) | `deepseek-chat` | DeepSeek, OpenAI, Anthropic |
| Worker (local) | `qwen3-8b` via LM Studio | any GGUF / vLLM-served model |

## Quick start

### 1. Install

Requires **Python 3.9+** and **Node.js 18+** (for the Harness plugin).

```bash
git clone https://github.com/kaijiayang/minions-dsh.git
cd minions-dsh
pip install -e .          # installs the minions protocol library + bridge deps
```

### 2. Start a local model server

Pick one — all of them expose an OpenAI-compatible API that this project speaks natively:

- **LM Studio** — load a model (e.g. `qwen3-8b`), open the *Local Server* tab, click **Start Server** → `http://127.0.0.1:1234/v1`.
- **Ollama** — `ollama serve` (the OpenAI-compatible endpoint is `http://127.0.0.1:11434/v1`).
- **vLLM** — `vllm serve Qwen/Qwen3-8B --api-key EMPTY` → `http://127.0.0.1:8000/v1`.
- **llama.cpp** — `llama-server -m <model>.gguf` → `http://127.0.0.1:8080/v1`.

See [docs/LOCAL_MODEL_SERVERS.md](docs/LOCAL_MODEL_SERVERS.md) for details and model suggestions.

### 3. Configure

Copy the canonical config and edit it (or use one of the ready-made examples):

```bash
cp minions.yaml minions.yaml   # it already lives at the repo root
# or:
cp examples/configs/minions.lmstudio.yaml minions.yaml
```

Set your cloud API key in the environment:

```bash
export DEEPSEEK_API_KEY=sk-...
```

### 4. Run

**Via the Python bridge (no Harness needed):**

```bash
echo '{"call_params":{"task":"Summarize the key findings","context":["Long document text..."],"doc_metadata":"Research paper"}}' \
  | python dsh-plugin/python/minions_bridge.py --config minions.yaml
```

**As a Python library:**

```python
from minions.config import load_config
from minions.minions import Minions
from minions.clients.openai_compat import OpenAICompatClient
from minions.clients.openai import OpenAIClient

local = OpenAICompatClient(model_name="qwen3-8b", platform="lmstudio")
remote = OpenAIClient(model_name="deepseek-chat", api_key=..., base_url="https://api.deepseek.com", local=False)

minions = Minions(local_client=local, remote_client=remote, max_rounds=3)
result = minions(
    task="Summarize the key findings",
    doc_metadata="Research paper",
    context=["Long document text..."],
)
print(result["final_answer"])
```

**Validate your config first:**

```bash
python dsh-plugin/python/minions_bridge.py --validate-config minions.yaml
```

## DeepSeek Harness plugin

The `dsh-plugin/` directory is an installable Harness **tool plugin** that registers a `minions_run` tool. Any Harness agent can then delegate long-context reasoning to your local/cloud pair:

```bash
cd dsh-plugin
npm install
npm run build
# from the repository root:
dsh web --patch ./dsh-plugin/cordis.yml     # then open http://127.0.0.1:3080
```

Before starting, edit `dsh-plugin/cordis.yml`:

- replace the placeholder plugin `name` with the **absolute** path to `dsh-plugin/lib/index.js` (`file:///` form on Windows),
- optionally set `configFile` to the absolute path of your `minions.yaml` (recommended — the plugin then reads everything from it),
- never commit API keys: export them in your shell (the bridge subprocess inherits the environment).

Full details: [docs/DSH_PLUGIN.md](docs/DSH_PLUGIN.md).

### The `minions_run` tool

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | ✅ | Main task for the cloud supervisor |
| `context` | string[] | ✅ | Long-context / document chunks |
| `doc_metadata` | string | — | Context type hint (e.g. "Medical Report") |
| `max_rounds` | integer | — | Max collaboration rounds (default 3) |
| `protocol` | `minions` \| `minion` | — | Parallel decomposition vs. single conversation |
| `local_model` | string | — | Local model id on your server |
| `local_platform` | enum | — | `lmstudio` \| `ollama` \| `vllm` \| `llamacpp` \| `generic` \| `auto` |
| `local_base_url` | string | — | Override the local OpenAI-compatible endpoint |
| `remote_model` | string | — | Cloud model id |
| `remote_client_type` | enum | — | `deepseek` \| `openai` \| `anthropic` \| `openai_compat` |

## Local platform support

Every supported local platform is accessed through the **same OpenAI-compatible API** — no vendor SDKs required:

| Platform | Default endpoint | API key | Notes |
|----------|------------------|---------|-------|
| **LM Studio** | `http://127.0.0.1:1234/v1` | any placeholder | GUI app; "Local Server" tab |
| **Ollama** | `http://127.0.0.1:11434/v1` | `ollama` | native or OpenAI-compatible |
| **vLLM** | `http://127.0.0.1:8000/v1` | `EMPTY` | production-grade, high throughput |
| **llama.cpp** | `http://127.0.0.1:8080/v1` | any placeholder | `llama-server` |
| **generic** | required | any | any OpenAI-compatible server |

Set `local.platform` in `minions.yaml` or `local_platform` per tool call. An explicit `base_url` always wins over the platform default.

## Configuration

The canonical file is `minions.yaml` at the repository root (schema: `config.schema.json`):

```yaml
version: 1

remote:                        # cloud supervisor
  provider: deepseek           # deepseek | openai | anthropic | openai_compat
  model: deepseek-chat
  base_url: https://api.deepseek.com/v1
  api_key_env: DEEPSEEK_API_KEY   # read the key from this env var

local:                         # local worker (OpenAI-compatible)
  platform: lmstudio           # lmstudio | ollama | vllm | llamacpp | generic | auto
  model: qwen3-8b
  base_url: http://127.0.0.1:1234/v1
  api_key: lm-studio           # placeholder is fine for most local servers

protocol:
  type: minions                # minions | minion
  max_rounds: 3
  log_dir: minion_logs

plugin:                        # DeepSeek Harness plugin options (optional)
  bridge_python: python
  timeout_ms: 300000
```

Rules:

- **Secrets** — use `api_key_env: <VAR>` or `${VAR}` interpolation; never commit keys.
- **Location** — the loader checks, in order: `MINIONS_CONFIG` env var → `minions.yaml` in the CWD → `minions.yaml` at the repo root.
- **Validation** — `python dsh-plugin/python/minions_bridge.py --validate-config minions.yaml`.

Full reference: [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Command-line interface

The bridge doubles as a CLI:

```bash
# offline self-test
python dsh-plugin/python/minions_bridge.py --self-test

# validate a config and print the resolved bridge payload
python dsh-plugin/python/minions_bridge.py --validate-config minions.yaml

# run one task using the config file (call params from stdin)
echo '{"call_params":{"task":"...","context":["..."]}}' \
  | python dsh-plugin/python/minions_bridge.py --config minions.yaml

# full raw JSON payload (backwards compatible)
echo '{"local_client":{...},"remote_client":{...},"protocol":{...},"call_params":{...}}' \
  | python dsh-plugin/python/minions_bridge.py
```

## Project layout

```
minions-dsh/
├── minions/                     # Python protocol library
│   ├── minions.py               #   Minions protocol (supervisor ↔ worker rounds)
│   ├── minion.py                #   Minion single-conversation protocol
│   ├── config.py                #   ★ standardized config loader/validator
│   └── clients/
│       ├── openai_compat.py     #   ★ unified OpenAI-compatible local client
│       ├── openai.py            #   OpenAI/DeepSeek cloud client
│       ├── ollama.py            #   Ollama native client
│       └── ...                  #   other upstream clients
├── dsh-plugin/                  # DeepSeek Harness plugin
│   ├── src/                     #   TypeScript: index.ts, bridge.ts, minions-tool.ts
│   ├── python/minions_bridge.py #   ★ JSON-over-stdio bridge (stdin in / stdout out)
│   └── cordis.yml               #   Harness local overlay (template)
├── minions.yaml                 # ★ canonical configuration
├── config.schema.json           # ★ JSON Schema for minions.yaml
├── examples/configs/            #   ready-made configs (LM Studio / Ollama / vLLM)
├── docs/                        #   architecture, configuration, servers, plugin, dev, troubleshooting
├── tests/                       #   Python unit tests
└── pyproject.toml               #   packaging (setuptools)
```

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow, plugin ↔ bridge contract |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Full `minions.yaml` reference, env vars, JSON Schema |
| [docs/LOCAL_MODEL_SERVERS.md](docs/LOCAL_MODEL_SERVERS.md) | Setting up LM Studio / Ollama / vLLM / llama.cpp |
| [docs/DSH_PLUGIN.md](docs/DSH_PLUGIN.md) | Installing & configuring the Harness plugin |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Building, testing, contributing |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common errors and fixes |

## Development

```bash
pip install -e ".[dev]"

# Python tests
python -m pytest tests/

# Bridge self-test
python dsh-plugin/python/minions_bridge.py --self-test

# TypeScript plugin
cd dsh-plugin && npm install && npm run build && npm run smoke
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Security

- Never commit API keys — use `api_key_env` / `${VAR}` and your shell environment.
- The long context stays on your machine by design; only sub-task summaries reach the cloud.
- Report vulnerabilities privately — see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) — this project **and** the upstream [HazyResearch/minions](https://github.com/HazyResearch/minions) library are MIT licensed. See [LICENSE](LICENSE) for the full text and attribution.
