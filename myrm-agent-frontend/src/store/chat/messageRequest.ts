/**
 * [INPUT]
 * ./chatActions, ./modelSelection, ./createMessageRequest, ./smartUpdater, ./sendMessage, ./attachToChat (POS: Message request pipeline modules)
 *
 * [OUTPUT]
 * The pipeline's public API under one stable import path: chat store contract types, model slot resolution
 * (getModelSelection, getRoutingModelSelections, validateChatModelConfig, ...), request assembly (createMessageRequest,
 * resolveEffectiveAgentId), send orchestration (sendMessage, createSmartUpdater) and attach / recovery (attachToChat,
 * attachForHitlRecovery).
 *
 * [POS]
 * Facade of the chat message request layer. The store and the stream modules import it lazily (the pipeline reads the
 * stores, so a static import from them would form an import cycle).
 */

export type { ChatActionsMethods, ChatActionsState } from './chatActions';
export { attachForHitlRecovery, attachToChat } from './attachToChat';
export type { AttachToChatOptions, HitlRecoveryResult } from './attachToChat';
export { createMessageRequest, resolveEffectiveAgentId } from './createMessageRequest';
export {
  getAutoMoaPresetId,
  getAutoMoaReasoning,
  getCodeModelSelection,
  getFallbackCodeModelSelection,
  getFallbackLiteModelSelection,
  getFallbackLongDocModelSelection,
  getFallbackModelSelection,
  getLiteModelSelection,
  getLongDocModelSelection,
  getModelSelection,
  getRoutingModelSelections,
  getSafetyFallbackModelSelection,
  getVisionFallbackModelSelection,
  validateChatModelConfig,
} from './modelSelection';
export type { RoutingModelSelections } from './modelSelection';
export { sendMessage } from './sendMessage';
export { createSmartUpdater } from './smartUpdater';
