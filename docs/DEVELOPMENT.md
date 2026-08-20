# Development

Guide for building, testing, and extending `minions-dsh`.

## Prerequisites

- Python 3.9+ (tested on 3.10)
- Node.js 18+ and npm

## Setup

```bash
git clone https://github.com/kaijiayang/minions-dsh.git
cd minions-dsh

pip install -e ".[dev]"        # Python package (editable) + dev deps
cd dsh-plugin && npm install && cd ..
```

## Repo map

```
minions/
├── minions.py            # Minions protocol (plural, parallel decomposition)
├── minion.py             # Minion protocol (single conversation)
├── config.py             # ★ standardized config loader/validator
├── usage.py              # token usage dataclass
├── clients/
│   ├── base.py           # MinionsClient ABC
│   ├── openai_compat.py  # ★ unified OpenAI-compatible local client
│   ├── openai.py         # OpenAI / DeepSeek cloud client
│   └── ...               # other upstream clients
└── prompts/ utils/       # protocol prompts & utilities
dsh-plugin/
├── src/                  # TypeScript plugin
│   ├── index.ts          # entry (name / inject / apply)
│   ├── bridge.ts         # subprocess bridge (payload build, spawn, parse)
│   ├── minions-tool.ts   # minions_run tool definition
│   └── smoke.ts          # Node smoke test
├── python/minions_bridge.py  # ★ JSON-over-stdio bridge
└── cordis.yml            # Harness overlay template
tests/                    # Python unit tests
docs/                     # documentation
examples/                 # ready-made configs & usage
```

## Running checks

```bash
# 1. Python unit tests
python -m pytest tests/

# 2. Bridge offline self-test (no servers needed)
python dsh-plugin/python/minions_bridge.py --self-test

# 3. Config validation on every example
for f in examples/configs/*.yaml; do
  python dsh-plugin/python/minions_bridge.py --validate-config "$f"
done

# 4. TypeScript build + smoke test
cd dsh-plugin
npm run build
npm run smoke
```

## Adding a new local platform

1. Add a preset to `PLATFORM_PRESETS` in `minions/clients/openai_compat.py`.
2. Add the platform name to `SUPPORTED_PLATFORMS` / the `local.platform` enum
   in `minions/config.py` and `config.schema.json`.
3. Add the platform to `docs/LOCAL_MODEL_SERVERS.md` and the README table.
4. Add a test in `tests/test_openai_compat.py`.

## Adding a config option

1. Extend the dataclasses in `minions/config.py` (`EndpointConfig` /
   `ProtocolConfig` / `PluginConfig`).
2. Update `config.schema.json` and `docs/CONFIGURATION.md`.
3. Add a test in `tests/test_config.py`.

## Changing the bridge contract

The contract is deliberately strict:

- stdin: one JSON object;
- stdout: one JSON object (`{success, result, error}`) — nothing else;
- stderr: logs.

Any change to the input/output shape must update **both** sides
(`bridge.ts` ↔ `minions_bridge.py`), the plugin's `output.schema` in
`minions-tool.ts`, and `docs/ARCHITECTURE.md`.

## End-to-end test (with real servers)

```bash
# terminal 1 — start your local server (e.g. LM Studio or ollama serve)
# terminal 2 — set the cloud key and run:
export DEEPSEEK_API_KEY=sk-...
echo '{"call_params":{"task":"Summarize","context":["Hello world. This is a test."]}}' \
  | python dsh-plugin/python/minions_bridge.py --config minions.yaml
```

## Planned enhancements

- **Persistent Python worker** — avoid per-call process spawn overhead
  (HTTP or long-lived stdin managed by `ctx.effect`).
- **Async tool mode** — return a task id + poll/callback for very long runs.
- **More protocol variants** — expose Subtask / DeepResearch / MoA.
- **Cost telemetry** — report estimated $ saved (local vs cloud tokens).
