import type { ContentBlock } from '@deepseek-ai/dsh-llm'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { Context } from '@deepseek-ai/cordis'
import type { Bridge, MinionsPluginConfig, MinionsRunInput } from './bridge'
import { LOCAL_PLATFORMS } from './bridge'

/**
 * 注册 minions_run 工具。
 * 工具 schema 使用 dsh-tools 的 ParameterSchemaSpec（属性级 required 标记）。
 */
export function registerMinionsTools(ctx: Context, bridge: Bridge, config: MinionsPluginConfig): void {
  ctx.tools.register(
    defineTool({
      name: 'minions_run',
      description:
        '使用 Minions 分层多模型协作协议处理长上下文/大批量文档推理任务。' +
        '云端大模型负责拆分任务、调度与综合，本地部署的小模型（LM Studio / Ollama / vLLM 等 OpenAI 兼容端点）' +
        '负责阅读长上下文并执行子任务，从而显著降低云端 API 费用。' +
        '适用于长文档总结、多文档问答、大规模信息抽取、需多轮迭代推理的场景。' +
        '注意：任务耗时可能达数十秒至数分钟。',
      parameters: {
        task: {
          type: 'string',
          required: true,
          description: '给远程 Supervisor 的主任务描述，例如“总结要点”“抽取关键信息”。',
        },
        context: {
          type: 'array',
          items: { type: 'string' },
          required: true,
          description: '长上下文/文档片段列表。每个元素是一段文本（建议按段落/章节切分）。',
        },
        doc_metadata: {
          type: 'string',
          description: '上下文类型描述，例如“Medical Report”“Financial Report”，帮助模型理解文档。',
        },
        max_rounds: {
          type: 'integer',
          description: '本地模型与远程模型的最大协作轮数，默认取插件配置（通常为 3）。',
        },
        protocol: {
          type: 'string',
          enum: ['minions', 'minion'] as const,
          description: 'minions：并行分解任务；minion：单轮对话式协作。默认 minions。',
        },
        local_model: {
          type: 'string',
          description: '本地小模型名（如 qwen3-8b / qwen3:8b）。默认取插件配置。',
        },
        local_platform: {
          type: 'string',
          enum: LOCAL_PLATFORMS,
          description:
            '本地模型部署平台（全部走 OpenAI 兼容 API）：lmstudio / ollama / vllm / llamacpp / generic / auto。' +
            '默认取插件配置（通常为 lmstudio）。',
        },
        local_base_url: {
          type: 'string',
          description:
            '本地 OpenAI 兼容端点地址（如 LM Studio: http://127.0.0.1:1234/v1，' +
            'Ollama: http://127.0.0.1:11434/v1，vLLM: http://127.0.0.1:8000/v1）。默认取插件配置 localBaseUrl。',
        },
        remote_model: {
          type: 'string',
          description: '远程大模型名（如 deepseek-chat）。默认取插件配置。',
        },
        remote_client_type: {
          type: 'string',
          enum: ['deepseek', 'openai', 'anthropic', 'openai_compat'] as const,
          description: '远程客户端类型，默认 deepseek。',
        },
      },
      output: {
        schema: {
          type: 'object',
          additionalProperties: false,
          properties: {
            success: { type: 'boolean' },
            result: { type: 'json' },
            error: { type: 'string' },
          },
        },
        render: (_args, value) => renderOutput(value),
      },
      timeoutMs: (config.timeoutMs ?? 300_000) + 15_000,
      isConcurrencySafe: () => false,
      async execute(args, exec) {
        const input: MinionsRunInput = {
          task: args.task,
          context: args.context,
          doc_metadata: args.doc_metadata,
          max_rounds: args.max_rounds ?? config.defaultMaxRounds ?? 3,
          protocol: args.protocol ?? config.defaultProtocol ?? 'minions',
          local_model: args.local_model,
          local_platform: args.local_platform,
          local_base_url: args.local_base_url,
          remote_model: args.remote_model,
          remote_client_type: args.remote_client_type,
        }
        const raw = await bridge.run(input, exec.signal)
        // bridge 的 normalizeOutput 已保证返回 { success, result, error } 严格符合 schema：
        //   - success: boolean
        //   - result: json（可为 null）
        //   - error: string（成功为空字符串 ''，绝不 null/缺失；error_detail 已并入 error）
        //   - 无任何额外字段（满足 additionalProperties:false）
        // 此处再做一次无损 JSON 兜底，清掉 result 内可能存在的 NaN/Infinity/undefined/BigInt 等非标准值。
        const cleaned = toLosslessJson(raw)
        return cleaned
      },
    }),
  )
}

/** 将任意值深度清理为严格的无损 JSON（JSON-safe），并去除非标准值。 */
function toLosslessJson<T>(value: T): T {
  // 用 replacer 拦截 NaN/Infinity/undefined/BigInt/函数/Symbol
  return JSON.parse(JSON.stringify(value, (key, val) => {
    if (typeof val === 'number') {
      if (Number.isNaN(val)) return null
      if (val === Infinity) return null
      if (val === -Infinity) return null
      return val
    }
    if (typeof val === 'bigint') return val.toString()
    if (typeof val === 'function' || typeof val === 'symbol') return undefined
    if (val === undefined) return null
    return val
  }))
}

function renderOutput(value: { success?: boolean; result?: unknown; error?: string | null }): ContentBlock[] {
  if (value?.success === false) {
    return [
      {
        type: 'text',
        text: `Minions 推理失败：${value.error ?? '未知错误'}`,
      },
    ]
  }
  const result = value?.result as { final_answer?: string; usage?: unknown } | null | undefined
  const finalAnswer = result?.final_answer ?? JSON.stringify(result ?? null)
  const usage = result?.usage ? `\n\n[usage] ${JSON.stringify(result.usage)}` : ''
  return [{ type: 'text', text: `${finalAnswer}${usage}` }]
}
