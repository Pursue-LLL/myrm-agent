/**
 * [INPUT]
 * - ./outlineTypes
 * - ./useOutlineGeometry
 * - ./useComposerFastFocus
 * - ./ConversationOutline
 *
 * [OUTPUT]
 * - Unified exports for Conversation Outline and Composer Fast Focus
 *
 * [POS]
 * Facade entry for chat-window outline module.
 */

export * from './outlineTypes';
export * from './useOutlineGeometry';
export * from './useComposerFastFocus';
export { ConversationOutline } from './ConversationOutline';
