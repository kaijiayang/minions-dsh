# Troubleshooting

Common errors and how to fix them.

## Installation & imports

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: No module named 'minions'` | The bridge can't find the `minions` package | Install the package: `pip install -e .` at the repo root (the bridge also bootstraps `sys.path` for direct runs). |
| `ModuleNotFoundError: No module named 'yaml'` | PyYAML missing | `pip install pyyaml` (or `pip install -e ".[dev]"`). JSON configs work without it. |
| `ImportError: cannot import name ... from 'openai'` | openai SDK too old/new | `pip install -U openai` (>= 1.0 required). |
| Warnings about `mistral not installed`, `transformers not installed`, etc. | Optional provider SDKs missing | Harmless — the client registry skips unavailable providers. Only install what you use. |

## Local server not reachable

| Symptom | Cause | Fix |
|---------|-------|-----|
| `OpenAI-compatible server at http://127.0.0.1:1234/v1 is not running or reachable` | Local server is down or the port is wrong | Start it (LM Studio → Local Server → Start Server; `ollama serve`; `vllm serve ...`) and check `GET {base_url}/models` in a browser. |
| `ConnectError` / `Connection refused` from the OpenAI SDK | Endpoint wrong | Verify the `base_url` ends with `/v1` and matches the server's port. |
| `ModelNotFoundError` / 404 on the model | Model id mismatch | The `model` must match exactly what your server exposes (LM Studio: id in "My Models"; Ollama: tag like `qwen3:8b`; vLLM: HF id like `Qwen/Qwen3-8B`). Case-sensitive. |

## Remote (cloud) issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `AuthenticationError` / 401 | Key missing or wrong | `export DEEPSEEK_API_KEY=sk-...` (or set `api_key_env` accordingly) and re-run. |
| `404` from `https://api.deepseek.com` | Base URL without `/v1` or wrong provider URL | DeepSeek: `https://api.deepseek.com/v1` (the OpenAI client appends `/chat/completions`). |
| `InsufficientQuota` / 429 | Billing / rate limits | Top up or wait; lower `max_rounds` to reduce calls. |

## Bridge / plugin

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Bridge script not found: ...` | `bridgeScript` path wrong | Use an absolute path or a path relative to `dsh-plugin/`. |
| `Minions bridge timed out (>300000ms)` | Long run exceeds `timeoutMs` | Increase `timeoutMs` in the plugin config or `plugin.timeout_ms` in `minions.yaml`. |
| `spawn EPERM` (Node on Windows) | Sandbox/policy blocking child process stdio | Run outside the restricted sandbox, or escalate permissions for the dev run. |
| Tool returns `success:false` with `error_detail` | Business error from the bridge | Read `error` and the `error_detail` traceback; usually a server or key issue above. |
| `ERR_UNSUPPORTED_ESM_URL_SCHEME` (Windows) | Plugin `name` in cordis.yml is a bare `D:/...` path | Use the `file:///D:/...` form. |
| `call_params.context cannot be empty` | Tool called without context | Always pass at least one context chunk. |
| `validation error for JobOutput` / 无法从本地模型输出中解析 JobOutput 字段 | The local model didn't emit strict JSON (e.g. wrapped in a markdown code fence) | The protocol strips code fences (```` ```json ```` / ```` ```python ````) and also accepts Python-repr style `JobOutput(explanation='...')`. If it still fails, check the worker's raw output in `minion_logs/` and consider a model that follows formatting instructions better. |
| Worker output is empty / a chunk silently gets no result | The worker is a *reasoning* model that spent its whole `max_tokens` budget on thinking, returning empty `content` (`finish_reason: "length"`) | Raise `local.max_tokens` (2048+) or disable thinking in the server/prompt; verify with a direct `POST {base_url}/v1/chat/completions` call. |
| `Failed to get valid JSON response after N attempts` | The supervisor's final-answer JSON wasn't strict (fences, single quotes, prose around it) | The protocol now parses it leniently (`_parse_json_lenient`); if it still fails, check the raw synthesis response in `minion_logs/`. |

## Config

| Symptom | Cause | Fix |
|---------|-------|-----|
| `No configuration file found` | Loader can't locate `minions.yaml` | Set `MINIONS_CONFIG` or run from the repo root / config dir. |
| `Unsupported config version` | `version` != 1 | Set `version: 1`. |
| `Environment variable X referenced by ... is not set` | `api_key_env` points at an unset var | Export the var or switch to `api_key`. |
| `local.platform must be one of ...` | Typo in platform | Use `lmstudio` \| `ollama` \| `vllm` \| `llamacpp` \| `generic` \| `auto`. |

## Still stuck?

Open an issue with:

1. the exact command you ran,
2. the full error output,
3. your `minions.yaml` (redact secrets),
4. your platform + versions (Python, openai, plugin version).
