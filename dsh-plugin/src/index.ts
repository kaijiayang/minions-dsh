import type { Context } from '@deepseek-ai/cordis'
import { createBridge, type MinionsPluginConfig } from './bridge'
import { registerMinionsTools } from './minions-tool'

export const name = 'minions'

export const inject = ['tools']

export function apply(ctx: Context, config: MinionsPluginConfig): void {
  const bridge = createBridge(ctx, config)
  registerMinionsTools(ctx, bridge, config)
}
