/**
 * [INPUT]
 * - None (Pure Type Definitions)
 *
 * [OUTPUT]
 * - OutlineTurnItem: Normalized conversation turn model
 * - StaircaseGeometryItem: Dynamic physical geometry properties for staircase scale track
 * - OutlineTooltipData: Inspection card model displayed on hover
 * - ConversationOutlineProps: Public API for the Conversation Outline component
 *
 * [POS]
 * Type foundation for Conversation Outline Staircase Navigator and Composer Fast Focus.
 * Zero `any`. File length < 100 lines.
 */

export interface OutlineTurnItem {
  turnIndex: number;
  userMessageId: string;
  assistantMessageId: string | null;
  promptPreview: string;
  replyPreview: string | null;
  isLoaded: boolean;
  messageIndex: number;
  isInFlight?: boolean;
  tokensUsed?: number;
  artifactName?: string;
}

export interface StaircaseGeometryItem {
  turnIndex: number;
  scale: number;
  width: number;
  height: number;
  opacity: number;
  isCenter: boolean;
  distanceFromActive: number;
}

export interface OutlineTooltipData {
  turnIndex: number;
  title: string;
  replySnippet: string | null;
  isInFlight?: boolean;
  topOffset: number;
}

export interface ConversationOutlineProps {
  items: OutlineTurnItem[];
  activeViewportTurn: number | null;
  onJumpToTurn: (item: OutlineTurnItem) => void;
  isLoading?: boolean;
  className?: string;
  maxVisibleTicks?: number;
}
