# Configuration

The standardized configuration file is `minions.yaml` (YAML or JSON, both
supported). The authoritative JSON Schema lives at
[`config.schema.json`](../config.schema.json).

## Where the config is looked up

`minions/config.py` searches in this order:

1. The explicit path passed to the loader (`--config PATH`,
   `load_config(PATH)`).
2. The `MINIONS_CONFIG` environment variable.
3. `minions.yaml` / `minions.yml` / `minions.json` in the **current working
   directory**.
4. The same filenames at the **repository root**.

## Full reference

```yaml
version: 1                       # required; only 1 is supported

# ---------------------------------------------------------------------------
remote:                          # the cloud supervisor (required)
  provider: deepseek             # deepseek | openai | anthropic | openai_compat |
                                 #   ollama | openrouter | groq | together
  model: deepseek-chat           # required
  base_url: https://api.deepseek.com/v1   # optional; provider default applies
  api_key_env: DEEPSEEK_API_KEY  # read the key from this env var (preferred)
  api_key: sk-...                # or a literal key (not recommended)
  temperature: 0.0               # default 0.0
  max_tokens: 4096               # default 2048

# ---------------------------------------------------------------------------
local:                           # the local worker (required)
  platform: lmstudio             # lmstudio | ollama | vllm | llamacpp |
                                 #   generic | auto
  model: qwen3-8b                # required; id exactly as exposed by your server
  base_url: http://127.0.0.1:1234/v1   # optional; overrides platform default
  api_key: lm-studio             # placeholder is fine for most local servers
  # api_key_env: OPENAI_COMPAT_API_KEY  # alternative to api_key
  temperature: 0.0
  max_tokens: 2048

# ---------------------------------------------------------------------------
protocol:                        # collaboration protocol (required)
  type: minions                  # minions | minion
  max_rounds: 3                  # default 3
  log_dir: minion_logs           # default minion_logs

# ---------------------------------------------------------------------------
plugin:                          # DeepSeek Harness plugin options (optional)
  bridge_python: python          # python interpreter for the bridge
  bridge_script: python/minions_bridge.py
  timeout_ms: 300000             # subprocess timeout (ms)
  max_buffer: 20971520           # max stdout buffer (bytes, default 20 MB)
```

Additional keys inside `remote:` / `local:` are forwarded as extra kwargs to
the client constructor (e.g. `top_p`, `response_format`).

## Platform presets (local)

`local.platform` selects default connection settings. Every platform is
accessed through the same OpenAI-compatible API.

| Platform | Default `base_url` | Default `api_key` | Notes |
|----------|--------------------|--------------------|-------|
| `lmstudio` | `http://127.0.0.1:1234/v1` | `lm-studio` | LM Studio "Local Server" |
| `ollama` | `http://127.0.0.1:11434/v1` | `ollama` | Ollama's OpenAI-compatible endpoint |
| `vllm` | `http://127.0.0.1:8000/v1` | `EMPTY` | `vllm serve ... --api-key EMPTY` |
| `llamacpp` | `http://127.0.0.1:8080/v1` | `no-key` | `llama-server` |
| `generic` | *required* | `local` | any custom endpoint |
| `auto` | LM Studio defaults | — | `base_url` wins if provided |

An explicit `base_url` always overrides the platform default.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `MINIONS_CONFIG` | Path to the config file |
| `DEEPSEEK_API_KEY` | DeepSeek key (used by `remote.api_key_env`) |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | OpenAI provider |
| `ANTHROPIC_API_KEY` | Anthropic provider |
| `OPENAI_COMPAT_BASE_URL` / `OPENAI_COMPAT_API_KEY` | Default local endpoint override |
| `MINIONS_BRIDGE_PY` | Python interpreter for the bridge |
| `MINIONS_BRIDGE_SCRIPT` | Bridge script path |
| `MINIONS_LOCAL_BASE_URL` / `MINIONS_LOCAL_API_KEY` | Plugin-side local endpoint overrides |

Any string value in the config may reference an environment variable with
`${VAR}` or `$VAR` syntax; it is expanded before validation. See
[`.env.example`](../.env.example).

### Where environment variables come from (Harness plugin)

When the plugin is used through `dsh web`, the bridge subprocess inherits the
`dsh web` process environment, which is populated from (in order, later wins):

1. The launching shell — `export DEEPSEEK_API_KEY=...` before `dsh web`.
2. `./.env` in dsh's working directory and `~/.dsh/.env` — auto-loaded at
   startup by `loadLayeredEnv` (a repo-root `.env` is gitignored).
3. The plugin's `env:` block in the plugin config (e.g. the profile user layer
   `cordis.patch.yml`) — merged into the subprocess environment by the plugin
   itself.

This means `remote.api_key_env: DEEPSEEK_API_KEY` resolves from any of the
three, without the key ever being stored in `minions.yaml`.

## Secrets

- **Never commit keys.** Prefer `api_key_env: VAR_NAME` over `api_key:`.
- `api_key_env` wins over a literal `api_key` when both are present; the
  resolved value is injected as the client's `api_key` kwarg.
- The bridge subprocess inherits the parent environment, so `export
  DEEPSEEK_API_KEY=...` before starting `dsh web` is enough (alternatives: a
  `.env` file auto-loaded at startup, or the plugin config's `env:` block).
- If a key referenced by `api_key_env` is missing, validation fails with a
  clear `Environment variable '...' is not set` message rather than silently
  sending an empty key.

## Validation

```bash
python dsh-plugin/python/minions_bridge.py --validate-config minions.yaml
```

This loads + validates the file and prints the **resolved** bridge payload
(secrets included — keep the output private).

## Examples

Ready-made configs:

- `examples/configs/minions.lmstudio.yaml`
- `examples/configs/minions.ollama.yaml`
- `examples/configs/minions.vllm.yaml`

## Config mode in the Harness plugin

Set `configFile` in the plugin config to the absolute path of your
`minions.yaml`. The bridge then loads clients/protocol from the file; per-call
tool arguments (`local_model`, `remote_model`, `max_rounds`, `protocol`)
become **overrides** on top of the file values.
