# dsh-plugin-minions

DeepSeek Harness **tool plugin**: registers a `minions_run` tool that lets any
Harness agent delegate long-context reasoning to a **cloud supervisor** (task
decomposition + synthesis) and a **local worker** (LM Studio / Ollama / vLLM /
llama.cpp via OpenAI-compatible APIs) — cutting cloud API costs.

> This directory is the plugin half of the **minions-dsh** project. For
> installation, configuration, and usage, see the
> [project README](../README.md), [docs/DSH_PLUGIN.md](../docs/DSH_PLUGIN.md),
> and [docs/CONFIGURATION.md](../docs/CONFIGURATION.md).

## Layout

```
dsh-plugin/
├── package.json              # npm package (entry lib/index.js)
├── tsconfig.json             # TypeScript config (CommonJS)
├── cordis.yml                # Harness local overlay (portable template)
├── src/
│   ├── index.ts              # plugin entry: name / inject / apply
│   ├── minions-tool.ts       # minions_run tool definition
│   ├── bridge.ts             # subprocess bridge (payload build, spawn, parse)
│   └── smoke.ts              # Node smoke test
└── python/
    ├── minions_bridge.py     # JSON-over-stdio bridge (stdin in / stdout out)
    └── requirements.txt      # minimal Python dependencies
```

## Build & smoke test

```bash
npm install
npm run build       # tsc -> lib/
npm run smoke       # build + offline smoke test (uses a mock Python script)
```

## Load into Harness

```bash
# from the repository root
dsh web --patch ./dsh-plugin/cordis.yml
```

Edit `cordis.yml` first: set the plugin `name` to the absolute `file:///` path
of `lib/index.js`, optionally set `configFile` to your `minions.yaml`, and
**never commit API keys** (export them in your shell — the bridge subprocess
inherits the environment).

## Bridge contract

`python/minions_bridge.py` speaks strict JSON-over-stdio:

- stdin: one JSON object (clients + protocol + call params), or
  `--config minions.yaml` + call params;
- stdout: exactly one JSON object `{success, result, error}`;
- stderr: logs.

Offline checks:

```bash
python python/minions_bridge.py --self-test
python python/minions_bridge.py --validate-config ../minions.yaml
```

## License

MIT — see the [project LICENSE](../LICENSE).
