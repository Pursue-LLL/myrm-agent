/**
 * [INPUT]
 * None - Pure TypeScript Contract definitions.
 *
 * [OUTPUT]
 * - BotPresenceStatus, GroupChatBotMember
 * - DeliberationMessageStatus, DeliberationMessage, NeedsYouIntervention
 * - GroupChatRoomHeaderProps, AgentMentionPopupProps
 * - DeliberationThreadBubbleProps, InteractiveNeedsYouBannerProps
 *
 * [POS]
 * Type contracts for Multi-Agent Group Chat Cockpit and Deliberation Visualizer.
 */

export type BotPresenceStatus = 'idle' | 'reasoning' | 'pass';

export interface GroupChatBotMember {
  id: string;
  name: string;
  role: string;
  avatar?: string;
  colorBadge: string;
  status: BotPresenceStatus;
  skills: string[];
  description?: string;
}

export type DeliberationMessageStatus = 'speaking' | 'pass' | 'needs-you';

export interface DeliberationMessage {
  id: string;
  agentId: string;
  agentName: string;
  role: string;
  content: string;
  status: DeliberationMessageStatus;
  passReason?: string;
  timestamp: string;
  options?: string[];
  colorBadge?: string;
}

export interface NeedsYouIntervention {
  threadId: string;
  issueTitle: string;
  contextSummary: string;
  suggestedOptions: string[];
  timestamp?: string;
}

export interface GroupChatRoomHeaderProps {
  roomName: string;
  members: GroupChatBotMember[];
  onSelectMember?: (member: GroupChatBotMember) => void;
  className?: string;
}

export interface AgentMentionPopupProps {
  isOpen: boolean;
  filterText?: string;
  members: GroupChatBotMember[];
  onSelectAgent: (member: GroupChatBotMember) => void;
  onClose: () => void;
  className?: string;
}

export interface DeliberationThreadBubbleProps {
  message: DeliberationMessage;
  onSelectOption?: (option: string) => void;
  className?: string;
}

export interface InteractiveNeedsYouBannerProps {
  intervention: NeedsYouIntervention | null;
  onIntervene: (decision: string) => void;
  onDismiss?: () => void;
  className?: string;
}
