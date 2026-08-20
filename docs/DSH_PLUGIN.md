# DeepSeek Harness plugin

`dsh-plugin/` is an installable **tool plugin** for
[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness). It
registers a single tool, `minions_run`, that any Harness agent can call to
delegate long-context reasoning to your local/cloud model pair.

## Requirements

- Python 3.9+ with the project installed (`pip install -e .` at the repo root)
- Node.js 18+
- A running local model server (see [LOCAL_MODEL_SERVERS.md](LOCAL_MODEL_SERVERS.md))
- A cloud API key (DeepSeek / OpenAI / Anthropic / ...) in your environment

## Install & build

```bash
cd dsh-plugin
npm install
npm run build        # produces lib/ (entry: lib/index.js)
```

## Load into Harness

The simplest path uses `dsh`'s `--patch` overlay:

```bash
# from the repository root
dsh web --patch ./dsh-plugin/cordis.yml
# open http://127.0.0.1:3080
```

### Edit `cordis.yml` first

`dsh-plugin/cordis.yml` is a **template** — it must be adjusted to your
machine:

```yaml
- insert:
    - id: minions
      name: 'file:///ABSOLUTE/PATH/TO/minions-dsh/dsh-plugin/lib/index.js'  # ← your path
      config:
        bridgePython: 'python'          # or an absolute interpreter path
        bridgeScript: 'dsh-plugin/python/minions_bridge.py'
        configFile: 'D:/path/to/minions-dsh/minions.yaml'   # ← recommended

        defaultLocalPlatform: 'lmstudio'
        defaultLocalModel: 'qwen3-8b'
        localBaseUrl: 'http://127.0.0.1:1234/v1'

        defaultRemoteClientType: 'deepseek'
        defaultRemoteModel: 'deepseek-chat'

        defaultMaxRounds: 3
        defaultProtocol: 'minions'
        timeoutMs: 300000
```

Notes:

- On Windows the plugin `name` must be a `file:///` URL (bare `D:/...` paths
  fail with `ERR_UNSUPPORTED_ESM_URL_SCHEME`).
- **Recommended**: set `configFile` to the absolute path of your
  `minions.yaml`. The bridge then reads clients/protocol from that file, and
  the per-call tool arguments act as overrides. Without `configFile`, use the
  `defaultLocalPlatform` / `defaultLocalModel` / ... keys.
- **Never commit API keys.** The bridge subprocess inherits the shell
  environment, so `export DEEPSEEK_API_KEY=sk-...` before `dsh web` is enough.
  Do not paste keys into `cordis.yml`.

## Plugin configuration reference

| Key | Default | Description |
|-----|---------|-------------|
| `bridgePython` | `python` | Python interpreter (absolute path recommended) |
| `bridgeScript` | `python/minions_bridge.py` | Bridge script path |
| `configFile` | — | Absolute path to `minions.yaml` (config mode) |
| `defaultLocalPlatform` | `lmstudio` | `lmstudio` \| `ollama` \| `vllm` \| `llamacpp` \| `generic` \| `auto` |
| `defaultLocalModel` | `qwen3-8b` | Local model id |
| `localBaseUrl` | `http://127.0.0.1:1234/v1` | Local OpenAI-compatible endpoint |
| `localApiKey` | `local` | Local endpoint key (placeholder fine) |
| `defaultRemoteClientType` | `deepseek` | `deepseek` \| `openai` \| `anthropic` \| `openai_compat` |
| `defaultRemoteModel` | `deepseek-chat` | Cloud model id |
| `defaultMaxRounds` | `3` | Max collaboration rounds |
| `defaultProtocol` | `minions` | `minions` \| `minion` |
| `timeoutMs` | `300000` | Subprocess timeout (ms) |
| `maxBuffer` | `20971520` | Max stdout buffer (bytes) |
| `env` | `{}` | Extra env vars for the subprocess |
| `localClient` / `remoteClient` | — | Fully override a client config |

## Using the tool

Ask the agent to use `minions_run`, or call it directly. Example agent prompt:

> Use the minions_run tool to summarize this long document: <paste text>.

The agent will pass the document as `context`, the instruction as `task`, and
optionally `local_platform: ollama` to switch the local server.

### Tool parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task` | string | ✅ | Main task for the cloud supervisor |
| `context` | string[] | ✅ | Long-context / document chunks |
| `doc_metadata` | string | — | Context type hint |
| `max_rounds` | integer | — | Max rounds (default 3) |
| `protocol` | `minions` \| `minion` | — | Parallel decomposition vs single conversation |
| `local_model` | string | — | Local model id |
| `local_platform` | enum | — | `lmstudio` \| `ollama` \| `vllm` \| `llamacpp` \| `generic` \| `auto` |
| `local_base_url` | string | — | Override the local endpoint |
| `remote_model` | string | — | Cloud model id |
| `remote_client_type` | enum | — | `deepseek` \| `openai` \| `anthropic` \| `openai_compat` |

### Output

The tool returns `{ success, result, error }` where `result` contains at least
`final_answer` and `usage`. Renderers display the final answer plus token usage
per side (local vs remote).

## Verifying the plugin without Harness

```bash
# bridge offline self-test
python dsh-plugin/python/minions_bridge.py --self-test

# config validation
python dsh-plugin/python/minions_bridge.py --validate-config minions.yaml

# node smoke test (mock bridge)
cd dsh-plugin && npm run smoke
```

## Publishing the plugin as an npm package

```bash
cd dsh-plugin
npm publish            # requires an npm account and the dsh-plugin-minions name
```

Consumers install it with `npm install dsh-plugin-minions` and enable it via
`dsh plugin add dsh-plugin-minions` (or the config UI). Remember that the
plugin shells out to Python — the target machine needs the `minions-dsh`
Python package installed as well.
