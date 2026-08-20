# Architecture

This document describes the design of `minions-dsh`: the Python protocol
library, the DeepSeek Harness plugin, and the JSON-over-stdio bridge that
connects them.

## High-level design

```
┌────────────────────────────────────────────────────────────────────┐
│                     DeepSeek Harness (Node.js)                      │
│                                                                    │
│   Agent (LLM) ──tool call──►  minions_run (TS plugin)              │
│                                  │  inject: ['tools']              │
│                                  │  ctx.tools.register(...)        │
│                                  ▼                                 │
│                        bridge.ts (subprocess mgmt)                 │
└──────────────────────────────────┼─────────────────────────────────┘
                                   │ spawn: python minions_bridge.py
                                   │        stdin : JSON payload
                                   │        stdout: JSON result
                                   ▼
                  ┌──────────────────────────────────────┐
                  │  minions_bridge.py (Python)          │
                  │  - resolves clients from config      │
                  │  - runs the protocol                 │
                  └───────────────┬──────────────────────┘
                                  │
              ┌───────────────────┴───────────────────┐
              ▼                                       ▼
   Cloud supervisor (remote client)        Local worker (local client)
   DeepSeek / OpenAI / Anthropic           OpenAICompatClient → LM Studio
   ● decomposes the task                    / Ollama / vLLM / llama.cpp
   ● evaluates worker outputs               ● reads the long context
   ● synthesizes the final answer           ● executes sub-tasks
                                            (long context never leaves here)
```

### The two halves

| Half | Language | Responsibility |
|------|----------|----------------|
| `dsh-plugin/src/*` | TypeScript | Register the tool, manage the subprocess, parse/validate the result, render output |
| `minions/` + `dsh-plugin/python/minions_bridge.py` | Python | The Minions protocol, all model clients, the standardized config |

The two halves are decoupled by a **strict JSON-over-stdio contract**, so
either half can be replaced or tested independently.

## The bridge contract

`minions_bridge.py` follows three hard rules:

1. **One JSON object in** on stdin.
2. **One JSON object out** on stdout — nothing else, ever.
3. **All logs** (progress, warnings, tracebacks) go to stderr.

### Input payload

```json
{
  "local_client": {
    "type": "openai_compat",
    "platform": "lmstudio",
    "model_name": "qwen3.8-27b",
    "kwargs": { "base_url": "http://127.0.0.1:1234/v1", "api_key": "lm-studio" }
  },
  "remote_client": {
    "type": "deepseek",
    "model_name": "deepseek-chat",
    "kwargs": { "base_url": "https://api.deepseek.com/v1", "api_key": "sk-..." }
  },
  "protocol": { "type": "minions", "max_rounds": 3, "log_dir": "minion_logs" },
  "call_params": { "task": "...", "doc_metadata": "...", "context": ["..."] }
}
```

### Output payload

Success:

```json
{ "success": true, "result": { "final_answer": "...", "usage": { } }, "error": null }
```

Failure:

```json
{ "success": false, "result": null, "error": "message", "error_detail": "traceback (optional)" }
```

### Modes

| Mode | How to invoke | Behavior |
|------|---------------|----------|
| Raw payload | no args, full JSON on stdin | back-compatible with the original plugin |
| Config mode | `--config minions.yaml` (+ `--call-json` optional) | clients/protocol come from the standardized config; call params from stdin or file; optional `overrides` for model/rounds/protocol |
| Validate | `--validate-config minions.yaml` | load + validate config, print the resolved payload, exit 0/1 |
| Self-test | `--self-test` | offline checks, no model servers contacted |

## Plugin internals

- **`src/index.ts`** — exports `name`, `inject: ['tools']`, and `apply(ctx, config)`;
  creates the bridge and registers the tool.
- **`src/bridge.ts`** — builds the stdin payload (`buildPayload` / `buildConfigPayload`),
  spawns Python via `execFile`, enforces timeout (`timeoutMs`) and stdout cap
  (`maxBuffer`), supports `AbortSignal` cancellation, and kills child processes
  on plugin teardown (`ctx.effect`).
- **`src/minions-tool.ts`** — declares the `minions_run` tool (parameters,
  output schema, renderer) and maps tool args into a `MinionsRunInput`.

### Configuration precedence

1. Per-call tool arguments (`local_platform`, `local_model`, ...).
2. Plugin config (`defaultLocalPlatform`, `defaultLocalModel`, ...).
3. `minions.yaml` when `configFile` is set (config mode — clients & protocol
   come from the file; per-call args become overrides).
4. Environment variables (`MINIONS_LOCAL_BASE_URL`, `DEEPSEEK_API_KEY`, ...).
5. Built-in defaults (LM Studio at `127.0.0.1:1234/v1`, DeepSeek).

## Config subsystem (`minions/config.py`)

- `load_config(path=None)` — finds the config file (explicit → `MINIONS_CONFIG`
  → CWD → repo root), parses YAML/JSON, expands `${VAR}`, validates, and
  returns a typed `MinionsConfig`.
- `MinionsConfig.to_bridge_payload(call_params)` — the single function that
  serializes a config into the bridge input format, so the plugin, the CLI,
  and the library always agree.
- `config.schema.json` — JSON Schema for IDE validation and CI checks.

## Client layer

All clients extend `MinionsClient` (`minions/clients/base.py`) and implement
`chat(messages, **kwargs)`.

- Local clients return `(responses, usage, done_reasons)` (3-tuple).
- Remote clients return `(responses, usage)` (2-tuple).

`OpenAICompatClient` (`minions/clients/openai_compat.py`) is the unified local
client: platform presets supply default `base_url`/`api_key`, an explicit
`base_url` always wins, and it probes `GET /v1/models` on construction for fast
failure. It uses `max_tokens` (not `max_completion_tokens`) because local
servers (vLLM, Ollama, LM Studio) expect it.

### `chat()` input shapes

Local `chat()` accepts two shapes:

| Shape | Example | Behavior |
|-------|---------|----------|
| Single conversation | `[{"role": "user", "content": "..."}]` | one API call, one response |
| Batch (parallel protocol) | `[[{"role": "user", "content": "..."}], [{"role": "user", "content": "..."}]]` | one API call **per** conversation, one response per conversation |

The parallel `minions` protocol sends each worker chunk as its own
single-message conversation (a list of lists), so worker responses align 1:1
with `JobManifest`s — every chunk gets a job output, and outputs never get
attached to the wrong chunk. `chat()` is also safe to call with a single
conversation (used by the sequential `minion` protocol).

### Tolerant output parsing

Model outputs are rarely strict JSON. Two layers of leniency are built in:

- **Worker outputs** — `extract_job_output()` in `minions/minions.py` strips
  markdown code fences (```` ```python ````, ```` ```json ````, ...) before
  `JobOutput.model_validate_json()`, then falls back to a regex parser for
  Python-repr style `JobOutput(explanation='...', ...)`.
- **Supervisor synthesis** — the final-answer JSON is parsed by
  `_parse_json_lenient()`: strip fences → `json.loads` → `ast.literal_eval`
  (tolerates single-quoted, Python-style dicts) → extract the outer `{...}`
  block from surrounding prose.

Together these keep the protocol running even when the local or remote model
wraps its structured output in a code block or uses non-strict quoting.

## Why a subprocess bridge and not a native port?

- The Minions protocol and its ~40 clients are mature Python code; porting
  them to TypeScript would duplicate effort and risk behavioral drift.
- The strict JSON contract makes the Python side independently testable
  (`--self-test`, unit tests) and lets users drive the bridge from any
  language.
- Cost: one Python process per call (~1-2 s overhead). If that becomes a
  problem, a persistent worker (HTTP or long-lived stdin) is the planned
  enhancement — see `docs/DEVELOPMENT.md`.

## See also

- [Configuration](CONFIGURATION.md)
- [DeepSeek Harness plugin](DSH_PLUGIN.md)
- [Local model servers](LOCAL_MODEL_SERVERS.md)
- [Development](DEVELOPMENT.md)
- [Troubleshooting](TROUBLESHOOTING.md)
