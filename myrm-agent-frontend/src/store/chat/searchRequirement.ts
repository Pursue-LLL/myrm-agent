/**
 * [INPUT]
 * @/lib/product-surface::resolveVisibleBuiltinAgentId (POS: Product surface SSOT for hidden builtin agents)
 * @/store/chat/types::{ActionMode, AgentConfig} (POS: Chat domain state and request contracts)
 *
 * [OUTPUT]
 * FAST_SEARCH_AGENT_ID: Id of the builtin Quick Search agent, the identity every fast-mode request is sent under.
 * requiresSearchService: Whether a turn needs a configured search service: the fast search mode, or the Quick Search agent picked in agent mode.
 *
 * [POS]
 * Search-service prerequisite of a turn. Imports no store, so the send guard and the request assembly share it without an import cycle.
 */
import { resolveVisibleBuiltinAgentId } from '@/lib/product-surface';
import type { ActionMode, AgentConfig } from '@/store/chat/types';

export const FAST_SEARCH_AGENT_ID = 'builtin-fast-search';

/**
 * The Quick Search agent answers through the search service and the server refuses its turns without one, so a send
 * under that identity is held back with a setup prompt instead. The identity is the one `resolveEffectiveAgentId`
 * puts on the request.
 */
export const requiresSearchService = (actionMode: ActionMode, agentConfig: AgentConfig | null): boolean =>
  actionMode === 'fast' || resolveVisibleBuiltinAgentId(agentConfig?.agentId?.trim()) === FAST_SEARCH_AGENT_ID;
