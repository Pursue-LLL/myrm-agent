/**
 * [INPUT]
 * @/store/config/providerTypes::SingleModelSelection (POS: Provider/model selection type contract)
 *
 * [OUTPUT]
 * Chat message, stream event, artifact, memory citation and store state TypeScript contracts.
 *
 * [POS]
 * Chat state and SSE event type definitions. Split from monolithic types.ts for maintainability.
 */

export type CostStatus = 'actual' | 'estimated' | 'unknown';

export type ContextHealthStatus = 'healthy' | 'warning' | 'critical';

export type ContextBudget = {
  current_tokens: number;
  max_context_tokens: number;
  usage_percent: number;
  health_status: ContextHealthStatus;
};
