/**
 * [INPUT]
 * @/store/chat/types::ActionMode, AgentConfig (POS: 会话级 Agent 与模式配置类型)
 * @/store/config/providerTypes::DefaultModelConfig, ProviderConfig, CustomModelInfo, hasUsableProviderAuth (POS: Provider and default-model configuration contract)
 *
 * [OUTPUT]
 * resolveSmartRouting: Decide whether complexity routing applies to a turn and resolve its light / reasoning slots.
 *
 * [POS]
 * Single decision point for smart routing activation and slots. Shared by the chat request builder, the model picker and the empty-chat badge so the request sent to the server and what the UI claims cannot disagree.
 */

import type { ActionMode, AgentConfig } from '@/store/chat/types';
import {
  hasUsableProviderAuth,
  type CustomModelInfo,
  type DefaultModelConfig,
  type ModelSlot,
  type ProviderConfig,
  type SingleModelSelection,
} from '@/store/config/providerTypes';

export interface RoutingSlotSelection {
  readonly primary: SingleModelSelection | null;
  readonly fallback: SingleModelSelection | null;
  /** Extra kwargs configured on the slot; absent for auto-picked slots. */
  readonly modelKwargs?: Record<string, unknown>;
}

export interface SmartRouting {
  /** The request carries light / reasoning slots and the server routes by complexity. */
  readonly active: boolean;
  /** The picker may offer "Smart Routing": selecting it clears the agent's pinned model. */
  readonly canSelect: boolean;
  readonly light: RoutingSlotSelection;
  readonly reasoning: RoutingSlotSelection;
}

interface PricedModel {
  selection: SingleModelSelection;
  cost: number;
}

const NO_SLOT: RoutingSlotSelection = { primary: null, fallback: null };
const NOT_ROUTED: SmartRouting = { active: false, canSelect: false, light: NO_SLOT, reasoning: NO_SLOT };

/**
 * Enabled models with a known input price. Models known to lack function calling are skipped:
 * a routed turn drives the full tool loop.
 */
function collectPricedModels(
  providers: ProviderConfig[],
  customModelInfo: Record<string, CustomModelInfo>,
): PricedModel[] {
  const priced: PricedModel[] = [];
  for (const provider of providers) {
    if (!provider.isEnabled || !hasUsableProviderAuth(provider)) {
      continue;
    }
    for (const model of provider.enabledModels ?? []) {
      const info = customModelInfo[`${provider.id}/${model}`];
      if (info?.supports_function_calling === false) {
        continue;
      }
      const cost = info?.input_cost_per_million;
      if (typeof cost === 'number') {
        priced.push({ selection: { providerId: provider.id, model }, cost });
      }
    }
  }
  return priced;
}

/** First model holding the extreme price, so ties resolve by enabled-model order. */
function pickByCost(priced: PricedModel[], cheapest: boolean): SingleModelSelection | null {
  let best: PricedModel | null = null;
  for (const candidate of priced) {
    if (best === null || (cheapest ? candidate.cost < best.cost : candidate.cost > best.cost)) {
      best = candidate;
    }
  }
  return best?.selection ?? null;
}

type SlotKey = 'lightModel' | 'reasoningModel';

function resolveSlot(
  key: SlotKey,
  agentConfig: AgentConfig | null,
  defaultModelConfig: DefaultModelConfig,
  providers: ProviderConfig[],
  autoPicked: SingleModelSelection | null,
): RoutingSlotSelection {
  const agentSlot: ModelSlot | undefined = agentConfig?.routingConfig?.[key];
  const defaultSlot: ModelSlot | undefined = defaultModelConfig.routingConfig?.[key];
  const configured = [agentSlot, defaultSlot].find(
    (slot) => slot?.primary && providers.some((p) => p.id === slot.primary?.providerId),
  );

  return {
    primary: configured?.primary ?? autoPicked,
    fallback: agentSlot?.fallback ?? defaultSlot?.fallback ?? null,
    ...(configured ? { modelKwargs: configured.modelKwargs ?? {} } : {}),
  };
}

/**
 * Precedence: fast mode never routes > the agent's explicit routing flag (true/false) > an agent that
 * pins a model does not route > the default routing config (routing is on unless it is switched off).
 * Routing additionally needs at least one resolvable slot: a configured slot whose provider exists, or an
 * auto-picked one (cheapest / priciest function-calling model; needs models at two or more distinct prices).
 */
export function resolveSmartRouting(
  actionMode: ActionMode,
  agentConfig: AgentConfig | null,
  defaultModelConfig: DefaultModelConfig,
  providers: ProviderConfig[],
  customModelInfo: Record<string, CustomModelInfo>,
): SmartRouting {
  const agentFlag = agentConfig?.routingConfig?.enabled;
  const enabled = agentFlag ?? defaultModelConfig.routingConfig?.enabled !== false;
  if (!enabled) {
    return NOT_ROUTED;
  }

  const priced = collectPricedModels(providers, customModelInfo);
  const hasPricePair = priced.some((model) => model.cost !== priced[0].cost);
  const light = resolveSlot(
    'lightModel',
    agentConfig,
    defaultModelConfig,
    providers,
    hasPricePair ? pickByCost(priced, true) : null,
  );
  const reasoning = resolveSlot(
    'reasoningModel',
    agentConfig,
    defaultModelConfig,
    providers,
    hasPricePair ? pickByCost(priced, false) : null,
  );
  if (!light.primary && !reasoning.primary) {
    return NOT_ROUTED;
  }

  const pinned = actionMode === 'agent' && Boolean(agentConfig?.modelSelection);
  const bypassed = actionMode === 'fast' || (pinned && agentFlag !== true);
  return { active: !bypassed, canSelect: actionMode === 'agent', light, reasoning };
}
