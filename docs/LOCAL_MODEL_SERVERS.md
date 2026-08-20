# Local model servers

`minions-dsh` talks to your local models through **OpenAI-compatible APIs**.
Any server that implements `POST /v1/chat/completions` works — the four
platforms below are the most common. No vendor SDKs are required.

> **Choosing a model**: pick a small but capable instruct model for the
> *worker* role — it has to read long contexts and follow the protocol's
> structured-output instructions. Good starting points: Qwen3 4B/8B, Llama
> 3.2 3B/8B, Gemma 3 4B, Phi-4 mini. Quantized GGUF (Q4_K_M) is fine.

---

## LM Studio (easiest, GUI)

1. Download from <https://lmstudio.ai> and install.
2. Open the app → **My Models** → search and download a model (e.g. `Qwen3-8B`).
3. Go to the **Local Server** tab → click **Start Server**.
   - Default endpoint: `http://127.0.0.1:1234/v1`
4. Verify: open `http://127.0.0.1:1234/v1/models` in a browser — you should
   see the model list.
5. Configure:

```yaml
local:
  platform: lmstudio
  model: qwen3-8b            # must match the id shown in My Models (case-sensitive)
  base_url: http://127.0.0.1:1234/v1
```

---

## Ollama

1. Install from <https://ollama.com/download>.
2. Pull a model: `ollama pull qwen3:8b`
3. Start the server: `ollama serve` (the OpenAI-compatible endpoint is
   `http://127.0.0.1:11434/v1`).
4. Verify: `curl http://127.0.0.1:11434/v1/models`
5. Configure:

```yaml
local:
  platform: ollama
  model: qwen3:8b            # ollama's model tag syntax
  base_url: http://127.0.0.1:11434/v1
```

> Ollama's native API is also supported by the upstream `OllamaClient`, but
> the OpenAI-compatible path above is recommended for uniformity.

---

## vLLM (production-grade, high throughput)

1. Install: `pip install vllm` (CUDA required for GPU serving).
2. Serve a model:

```bash
vllm serve Qwen/Qwen3-8B --api-key EMPTY --port 8000
```

3. Verify: `curl http://127.0.0.1:8000/v1/models`
4. Configure:

```yaml
local:
  platform: vllm
  model: Qwen/Qwen3-8B       # vLLM uses HuggingFace-style model ids
  base_url: http://127.0.0.1:8000/v1
```

> Use `--max-model-len` to raise the context window for long documents.

---

## llama.cpp server

1. Build or download a `llama-server` binary from
   <https://github.com/ggml-org/llama.cpp/releases>.
2. Run it with a GGUF model:

```bash
llama-server -m path/to/model.Q4_K_M.gguf --port 8080
```

3. Verify: `curl http://127.0.0.1:8080/v1/models`
4. Configure:

```yaml
local:
  platform: llamacpp
  model: model              # arbitrary id; any string works
  base_url: http://127.0.0.1:8080/v1
```

---

## Any other OpenAI-compatible server

```yaml
local:
  platform: generic
  model: my-model
  base_url: http://my-server:PORT/v1   # required for generic
  api_key: whatever                    # some servers require a real token
```

## Health check

`OpenAICompatClient` probes `GET {base_url}/models` at construction. If the
server is down, you get a clear error like:

```
OpenAI-compatible server at http://127.0.0.1:1234/v1 is not running or
reachable. Start your local server first: ...
```

## Tips

- **Context window** — long documents need a large context. Prefer models with
  ≥ 32k context; chunk your input into paragraphs/sections anyway (the
  protocol already chunks).
- **Structured output** — the worker must emit `{explanation, citation,
  answer}`. Use a model that follows formatting instructions well; the
  protocol includes a tolerant parser as a fallback.
- **GPU vs CPU** — quantization (Q4_K_M) lets 4-8B models run on 8 GB VRAM;
  CPU-only works but is slower — fine for the worker role.
