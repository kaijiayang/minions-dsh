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

Two **mutually exclusive** ways — pick one (both produce a duplicate `minions`
entry):

### Way A — `--patch` overlay (portable template)

```bash
# from the repository root
dsh web --patch ./dsh-plugin/cordis.yml
```

Edit `cordis.yml` first: set the plugin `name` to the absolute `file:///` path
of `lib/index.js`, optionally set `configFile` to your `minions.yaml`, and
**never commit API keys** (export them in your shell — the bridge subprocess
inherits the environment).

### Way B — profile user layer (no `--patch`, HMR hot-reload)

The profile user layer is watched by dsh's HMR, so saving the file applies the
change immediately — **no dsh web restart needed**. Put an **`insert`** (not
`update`) in `~/.dsh/profiles/web/cordis.patch.yml`:

```yaml
- insert:
    - id: minions
      name: 'file:///ABSOLUTE/PATH/TO/dsh-plugin/lib/index.js'   # ← your absolute path
      config:
        bridgePython: 'python'
        bridgeScript: 'python/minions_bridge.py'
        configFile: 'ABSOLUTE/PATH/TO/minions.yaml'   # ← your absolute path
        defaultLocalPlatform: 'lmstudio'
        defaultLocalModel: 'qwen3-8b'   # ← model id as exposed by your server
        localBaseUrl: 'http://127.0.0.1:1234/v1'
        defaultRemoteClientType: 'deepseek'
        defaultRemoteModel: 'deepseek-chat'   # ← cloud model id
        defaultMaxRounds: 3
        defaultProtocol: 'minions'
        timeoutMs: 300000
        env:
          DEEPSEEK_API_KEY: 'sk-...'   # or rely on the environment / .env
```

Then start `dsh web` **without** `--patch`:

```bash
dsh web
```

**Why `insert` and not `update`:** patch layers apply in the order `bundle →
profile user layer → home → --patch overlays`. An overlay-inserted entry does
not exist yet when the user layer runs, so a user-layer `update` is silently
skipped (`patch: entry "minions" not found`); `insert` creates the entry
itself. Verify with `dsh web --dump-config` — the `minions` entry should come
from `cordis.patch.yml`.

Secrets (any one works): export the key in the launching shell; add an `env:`
block to the plugin config (merged into the bridge subprocess env); or drop a
`.env` in dsh's working directory (auto-loaded at startup, gitignored at the
repo root). See [docs/DSH_PLUGIN.md](../docs/DSH_PLUGIN.md) for the full
reference.

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
