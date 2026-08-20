import { execFile, type ChildProcess } from 'node:child_process'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'

/**
 * Plugin configuration. Sensitive values (API keys, etc.) must be supplied
 * through `env` / environment variables — never hard-coded.
 */
export interface MinionsPluginConfig {
  /** Python interpreter (default 'python'). */
  bridgePython?: string
  /** Bridge script path (relative to the plugin root or absolute). */
  bridgeScript?: string
  /**
   * Path to the standardized `minions.yaml` config file. When set, the bridge
   * loads clients/protocol from that file (see minions/config.py); per-call
   * arguments below act as overrides.
   */
  configFile?: string
  /** Default local small model name. */
  defaultLocalModel?: string
  /** Default remote large model name. */
  defaultRemoteModel?: string
  /** Default max collaboration rounds. */
  defaultMaxRounds?: number
  /** Default protocol: minions | minion. */
  defaultProtocol?: 'minions' | 'minion'
  /**
   * Default local platform (all OpenAI-compatible): lmstudio | ollama |
   * vllm | llamacpp | generic | auto.
   */
  defaultLocalPlatform?: 'lmstudio' | 'ollama' | 'vllm' | 'llamacpp' | 'generic' | 'auto'
  /** Default remote client type: deepseek | openai | anthropic | openai_compat. */
  defaultRemoteClientType?: string
  /** Local OpenAI-compatible endpoint (e.g. LM Studio http://127.0.0.1:1234/v1). */
  localBaseUrl?: string
  /** Local endpoint API key (LM Studio usually accepts any placeholder). */
  localApiKey?: string
  /** Subprocess timeout in ms (default 300_000). */
  timeoutMs?: number
  /** Max stdout buffer (default 20MB). */
  maxBuffer?: number
  /** Extra environment variables merged into the subprocess env. */
  env?: Record<string, string>
  /** Full local client config (overrides everything derived above). */
  localClient?: Record<string, unknown>
  /** Full remote client config. */
  remoteClient?: Record<string, unknown>
}

export interface MinionsRunInput {
  task: string
  context: string[]
  doc_metadata?: string
  max_rounds?: number
  protocol?: 'minions' | 'minion'
  local_model?: string
  remote_model?: string
  /** Local platform: lmstudio | ollama | vllm | llamacpp | generic | auto. */
  local_platform?: 'lmstudio' | 'ollama' | 'vllm' | 'llamacpp' | 'generic' | 'auto'
  /** Local OpenAI-compatible endpoint (overrides plugin config localBaseUrl). */
  local_base_url?: string
  /** Remote client type: deepseek | openai | anthropic | openai_compat. */
  remote_client_type?: 'deepseek' | 'openai' | 'anthropic' | 'openai_compat'
  local_client_kwargs?: Record<string, unknown>
  remote_client_kwargs?: Record<string, unknown>
}

/** JSON value type matching dsh-tools JsonValue (from the Python bridge stdout). */
export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue }

/**
 * Bridge output. Must strictly match the `minions_run` output.schema:
 * { success: boolean, result: json, error: string } with
 * additionalProperties: false.
 */
export interface BridgeOutput {
  success: boolean
  result: JsonValue
  error: string
}

export interface Bridge {
  run(input: MinionsRunInput, signal?: AbortSignal): Promise<BridgeOutput>
}

/** Running child processes (cleaned up by ctx.effect). */
const activeChildren = new Set<ChildProcess>()

/** Local platforms exposed to tool callers. */
export const LOCAL_PLATFORMS = ['lmstudio', 'ollama', 'vllm', 'llamacpp', 'generic', 'auto'] as const

const DEFAULT_LOCAL_BASE_URL = 'http://127.0.0.1:1234/v1'

/**
 * Build the stdin JSON payload for the bridge (non-config mode).
 */
export function buildPayload(input: MinionsRunInput, config: MinionsPluginConfig): unknown {
  const protocol = input.protocol ?? config.defaultProtocol ?? 'minions'
  const maxRounds = input.max_rounds ?? config.defaultMaxRounds ?? 3
  const localModel = input.local_model ?? config.defaultLocalModel ?? 'qwen3-8b'
  const remoteModel = input.remote_model ?? config.defaultRemoteModel ?? 'deepseek-chat'

  // ---- Local client: unified OpenAI-compatible endpoint (LM Studio / Ollama / vLLM ...) ----
  const localPlatform = input.local_platform ?? config.defaultLocalPlatform ?? 'lmstudio'
  let localClient: Record<string, unknown>
  if (config.localClient && Object.keys(config.localClient).length > 0) {
    localClient = config.localClient
  } else {
    const kwargs: Record<string, unknown> = { ...(input.local_client_kwargs ?? {}) }
    kwargs.base_url =
      input.local_base_url ??
      kwargs.base_url ??
      config.localBaseUrl ??
      process.env.MINIONS_LOCAL_BASE_URL ??
      DEFAULT_LOCAL_BASE_URL
    kwargs.api_key = kwargs.api_key ?? config.localApiKey ?? process.env.MINIONS_LOCAL_API_KEY ?? 'local'
    localClient = {
      type: 'openai_compat',
      platform: localPlatform,
      model_name: localModel,
      kwargs,
    }
  }

  // ---- Remote client ----
  const remoteClient =
    config.remoteClient && Object.keys(config.remoteClient).length > 0
      ? config.remoteClient
      : {
          type: input.remote_client_type ?? config.defaultRemoteClientType ?? 'deepseek',
          model_name: remoteModel,
          kwargs: input.remote_client_kwargs ?? {},
        }

  const callParams: Record<string, unknown> = {
    task: input.task,
    context: input.context,
  }
  if (input.doc_metadata) callParams.doc_metadata = input.doc_metadata

  return {
    local_client: localClient,
    remote_client: remoteClient,
    protocol: { type: protocol, max_rounds: maxRounds },
    call_params: callParams,
  }
}

/**
 * Build the stdin JSON for config-file mode: only call params plus optional
 * per-call overrides (the bridge loads clients/protocol from minions.yaml).
 */
export function buildConfigPayload(input: MinionsRunInput): unknown {
  const callParams: Record<string, unknown> = {
    task: input.task,
    context: input.context,
  }
  if (input.doc_metadata) callParams.doc_metadata = input.doc_metadata

  const overrides: Record<string, unknown> = {}
  if (input.local_model) overrides.local_model = input.local_model
  if (input.remote_model) overrides.remote_model = input.remote_model
  if (input.max_rounds !== undefined) overrides.max_rounds = input.max_rounds
  if (input.protocol) overrides.protocol = input.protocol

  return { call_params: callParams, overrides }
}

/** Resolve the absolute path of the bridge script. */
function resolveScriptPath(raw: string, pluginRoot: string): string {
  return resolve(pluginRoot, raw)
}

/**
 * Merge env vars: process.env as the base, plugin `env` on top, and make sure
 * PYTHONPATH points at the repository root.
 */
function buildEnv(config: MinionsPluginConfig, pluginRoot: string): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...process.env }

  const repoRoot = resolve(pluginRoot, '..')
  const sep = process.platform === 'win32' ? ';' : ':'
  const existingPy = (env.PYTHONPATH ?? '').trim()
  env.PYTHONPATH = existingPy ? `${repoRoot}${sep}${existingPy}` : repoRoot
  env.PYTHONUNBUFFERED = env.PYTHONUNBUFFERED ?? '1'

  if (config.env) {
    Object.assign(env, config.env)
  }
  return env
}

/**
 * Run the Python bridge once. JSON in via stdin, JSON out via stdout,
 * logs via stderr.
 */
export function runMinions(
  input: MinionsRunInput,
  config: MinionsPluginConfig,
  pluginRoot: string,
  signal?: AbortSignal,
): Promise<BridgeOutput> {
  const pythonBin = config.bridgePython ?? process.env.MINIONS_BRIDGE_PY ?? 'python'
  const scriptRaw = config.bridgeScript ?? process.env.MINIONS_BRIDGE_SCRIPT ?? 'python/minions_bridge.py'
  const script = resolveScriptPath(scriptRaw, pluginRoot)

  const timeoutMs = config.timeoutMs ?? 300_000
  const maxBuffer = config.maxBuffer ?? 20 * 1024 * 1024

  return new Promise<BridgeOutput>((resolvePromise, reject) => {
    if (!existsSync(script)) {
      reject(
        new Error(
          `Bridge script not found: ${script}. Set bridgeScript in the plugin ` +
            `config, or confirm dsh-plugin/python/minions_bridge.py exists.`,
        ),
      )
      return
    }

    // Config-file mode vs. raw-payload mode.
    const configFile = config.configFile
    const cliArgs = [script]
    let stdinPayload: string
    if (configFile) {
      if (!existsSync(configFile)) {
        reject(new Error(`Config file not found: ${configFile}.`))
        return
      }
      cliArgs.push('--config', configFile)
      stdinPayload = JSON.stringify(buildConfigPayload(input))
    } else {
      stdinPayload = JSON.stringify(buildPayload(input, config))
    }

    const env = buildEnv(config, pluginRoot)

    let child: ChildProcess
    try {
      child = execFile(
        pythonBin,
        cliArgs,
        {
          timeout: timeoutMs,
          maxBuffer,
          env,
          windowsHide: true,
        },
        (err, stdout) => {
          activeChildren.delete(child)

          const trimmed = stdout?.trim() ?? ''
          let structured: BridgeOutput | undefined
          if (trimmed) {
            try {
              structured = normalizeOutput(JSON.parse(trimmed))
            } catch {
              structured = undefined
            }
          }

          if (err) {
            const code = (err as NodeJS.ErrnoException).code
            if (code === 'ETIMEDOUT' || (err as any).killed) {
              reject(new Error(`Minions bridge timed out (>${timeoutMs}ms). Increase timeoutMs.`))
              return
            }
            if (structured) {
              resolvePromise(structured)
              return
            }
            const stderrSnippet = extractStderr(err)
            reject(
              new Error(
                `Minions bridge failed: ${err.message}` +
                  (stderrSnippet ? `\nstderr: ${stderrSnippet}` : '') +
                  `\nCheck that Python (${pythonBin}) and the minions dependencies are installed.`,
              ),
            )
            return
          }

          if (!trimmed) {
            reject(new Error('Minions bridge returned no output (empty stdout).'))
            return
          }
          if (!structured) {
            reject(
              new Error(
                'Minions bridge output is not valid JSON. stdout must contain a single JSON object.' +
                  `\nActual output (first 2000 chars): ${trimmed.slice(0, 2000)}`,
              ),
            )
            return
          }
          resolvePromise(structured)
        },
      )
    } catch (e) {
      reject(
        new Error(
          `Cannot start Python subprocess (${pythonBin}): ${(e as Error).message}.`,
        ),
      )
      return
    }

    activeChildren.add(child)

    if (signal) {
      const onAbort = () => {
        try {
          child.kill()
        } catch {
          /* ignore */
        }
      }
      if (signal.aborted) onAbort()
      else signal.addEventListener('abort', onAbort, { once: true })
    }

    child.stderr?.on('data', (chunk: Buffer) => {
      process.stderr.write(chunk)
    })

    try {
      child.stdin?.write(stdinPayload)
      child.stdin?.end()
    } catch (e) {
      reject(new Error(`Failed to write bridge stdin: ${(e as Error).message}`))
    }
  })
}

/** Normalize the bridge raw JSON output into BridgeOutput. */
export function normalizeOutput(raw: unknown): BridgeOutput {
  const obj = (raw ?? {}) as Record<string, unknown>
  let error = ''
  const err = obj.error
  const detail = obj.error_detail
  if (err !== null && err !== undefined) {
    error = String(err)
  }
  if (detail !== null && detail !== undefined) {
    error = error ? `${error}\n\n${String(detail)}` : String(detail)
  }
  return {
    success: Boolean(obj.success),
    result: (obj.result ?? null) as JsonValue,
    error,
  }
}

function extractStderr(err: Error & { stderr?: Buffer | string }): string {
  if (typeof err.stderr === 'string') return err.stderr.slice(0, 2000)
  if (Buffer.isBuffer(err.stderr)) return err.stderr.toString('utf8').slice(0, 2000)
  return ''
}

/** Kill all active child processes (plugin teardown). */
export function killAllChildren(): void {
  for (const child of activeChildren) {
    try {
      child.kill('SIGKILL')
    } catch {
      /* ignore */
    }
  }
  activeChildren.clear()
}

/** Bridge factory: binds the plugin root + ctx, wires lifecycle cleanup. */
export function createBridge(ctx: Context, config: MinionsPluginConfig): Bridge {
  const pluginRoot = resolve(__dirname, '..')

  ctx.effect(() => {
    return () => killAllChildren()
  })

  return {
    run: (input: MinionsRunInput, signal?: AbortSignal): Promise<BridgeOutput> =>
      runMinions(input, config, pluginRoot, signal),
  }
}
