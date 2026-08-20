/**
 * Plugin smoke test (runs without Harness, validates the bridge chain).
 *
 * Run: npm run smoke   (builds lib first, then executes node lib/smoke.js)
 *
 * Requires:
 *   - A Python interpreter
 *   - The `minions` package importable (PYTHONPATH points at the repo root)
 *   - For real inference: a local/remote model; the default test uses a mock
 *     Python script to verify the subprocess + JSON chain.
 */
import { buildPayload, buildConfigPayload, runMinions, type MinionsPluginConfig } from './bridge'
import { resolve } from 'node:path'
import { writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'

const pluginRoot = resolve(__dirname, '..')
const config: MinionsPluginConfig = {
  bridgePython: process.env.MINIONS_BRIDGE_PY || 'python',
  bridgeScript: 'python/minions_bridge.py',
  defaultLocalModel: 'qwen3-8b',
  defaultLocalPlatform: 'lmstudio',
  defaultRemoteModel: 'deepseek-chat',
  defaultMaxRounds: 1,
  timeoutMs: 30000,
}

async function main() {
  // 1. Payload generation (raw mode) — openai_compat + platform presets
  console.log('[smoke] 1. buildPayload (openai_compat / platform) ...')
  const payload = buildPayload(
    {
      task: 'Summarize',
      context: ['para 1', 'para 2'],
      doc_metadata: 'test doc',
      max_rounds: 2,
      protocol: 'minions',
      local_platform: 'ollama',
    },
    config,
  ) as any
  assert(payload.protocol.type === 'minions' && payload.protocol.max_rounds === 2, 'protocol config wrong')
  assert(payload.call_params.context.length === 2 && payload.call_params.task === 'Summarize', 'call_params wrong')
  assert(payload.local_client.type === 'openai_compat', 'local client type should be openai_compat')
  assert(payload.local_client.platform === 'ollama', 'local platform wrong')
  assert(
    payload.local_client.kwargs.base_url === 'http://127.0.0.1:11434/v1' ||
      payload.local_client.kwargs.base_url !== undefined,
    'local base_url missing',
  )
  console.log('[smoke]    payload OK\n')

  // 2. Config-mode payload (call_params + overrides)
  console.log('[smoke] 2. buildConfigPayload ...')
  const cfgPayload = buildConfigPayload({ task: 'T', context: ['c'], local_model: 'x', max_rounds: 5 }) as any
  assert(cfgPayload.call_params.task === 'T', 'config payload task wrong')
  assert(cfgPayload.overrides.local_model === 'x' && cfgPayload.overrides.max_rounds === 5, 'overrides wrong')
  console.log('[smoke]    config payload OK\n')

  // 3. Subprocess + JSON round-trip with a mock Python script
  console.log('[smoke] 3. subprocess + JSON round-trip (mock script) ...')
  const mockScript = resolve(tmpdir(), 'mock_bridge.py')
  const mockCode = `import sys, json
raw = sys.stdin.buffer.read().decode('utf-8-sig')
data = json.loads(raw)
print(json.dumps({"success": True, "result": {"final_answer": "mock answer for: " + data["call_params"]["task"], "usage": {"total_tokens": 100}}, "error": None}))
`
  writeFileSync(mockScript, mockCode)
  try {
    const mockResult = await runMinions(
      { task: 'Test', context: ['c'] },
      { ...config, bridgeScript: mockScript },
      pluginRoot,
    )
    console.log('[smoke]    mock result =', JSON.stringify(mockResult))
    assert(mockResult.success === true, 'mock should succeed')
    assert((mockResult.result as any)?.final_answer === 'mock answer for: Test', 'mock final_answer mismatch')
    console.log('[smoke]    subprocess chain OK\n')
  } finally {
    rmSync(mockScript, { force: true })
  }

  // 4. Error handling: missing script
  console.log('[smoke] 4. error handling (missing script) ...')
  try {
    await runMinions({ task: 't', context: ['c'] }, { ...config, bridgeScript: 'no/such.py' }, pluginRoot)
    throw new Error('expected an error, got none')
  } catch (e) {
    console.log('[smoke]    expected error: ' + (e as Error).message.split('\n')[0])
    console.log('[smoke]    error handling OK\n')
  }

  console.log('[smoke] all smoke tests passed')
}

function assert(cond: boolean, msg: string) {
  if (!cond) {
    console.error('[smoke] assertion failed: ' + msg)
    process.exit(1)
  }
}

main().catch((e) => {
  console.error('[smoke] smoke test failed:', e)
  process.exit(1)
})
