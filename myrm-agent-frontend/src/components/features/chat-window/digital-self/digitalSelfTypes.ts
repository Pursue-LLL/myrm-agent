/**
 * [INPUT]
 * - None (pure TypeScript contract & configuration constants)
 *
 * [OUTPUT]
 * - ToneStyle, RecipientRelationship, OutboundChannelType, DraftStatus
 * - DraftContextSource, DigitalSelfDraftItem, OutboundAuditRecord
 * - TONE_STYLE_CONFIGS, RELATIONSHIP_CONFIGS, CHANNEL_CONFIGS
 *
 * [POS]
 * Defines runtime contracts for Digital Self Tone-Adapted Drafting and Outbound
 * Send Hard-Gate confirmation, preventing hallucinated outbound messaging.
 */

export type ToneStyle = 'formal' | 'semi-formal' | 'friendly' | 'concise';

export type RecipientRelationship = 'leader' | 'colleague' | 'partner' | 'teammate';

export type OutboundChannelType = 'feishu' | 'dingtalk' | 'wechat' | 'email' | 'slack';

export type DraftStatus = 'pending_review' | 'edited' | 'confirmed_sent' | 'discarded';

export interface DraftContextSource {
  id: string;
  title: string;
  excerpt: string;
  url?: string;
}

export interface DigitalSelfDraftItem {
  id: string;
  channel: OutboundChannelType;
  recipientName: string;
  relationship: RecipientRelationship;
  toneStyle: ToneStyle;
  originalMessage: string;
  originalTimestamp: number;
  draftContent: string;
  contextSources: DraftContextSource[];
  status: DraftStatus;
  createdAt: number;
  confirmedAt?: number;
  explicitlyConfirmedByHuman: boolean;
}

export interface ToneStyleConfig {
  style: ToneStyle;
  /** `digitalSelf` message key of the tone's name. */
  labelKey: string;
  /** `digitalSelf` message key of the tone's one-line description. */
  descriptionKey: string;
  colorClass: string;
}

export const TONE_STYLE_CONFIGS: Record<ToneStyle, ToneStyleConfig> = {
  formal: {
    style: 'formal',
    labelKey: 'toneFormal',
    descriptionKey: 'toneFormalDesc',
    colorClass: 'text-indigo-600 dark:text-indigo-400 bg-indigo-500/10 border-indigo-500/30',
  },
  'semi-formal': {
    style: 'semi-formal',
    labelKey: 'toneSemiFormal',
    descriptionKey: 'toneSemiFormalDesc',
    colorClass: 'text-sky-600 dark:text-sky-400 bg-sky-500/10 border-sky-500/30',
  },
  friendly: {
    style: 'friendly',
    labelKey: 'toneFriendly',
    descriptionKey: 'toneFriendlyDesc',
    colorClass: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  },
  concise: {
    style: 'concise',
    labelKey: 'toneConcise',
    descriptionKey: 'toneConciseDesc',
    colorClass: 'text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/30',
  },
};

export interface RelationshipConfig {
  relationship: RecipientRelationship;
  /** `digitalSelf` message key of the relationship's name. */
  labelKey: string;
  recommendedTone: ToneStyle;
  colorClass: string;
}

export const RELATIONSHIP_CONFIGS: Record<RecipientRelationship, RelationshipConfig> = {
  leader: {
    relationship: 'leader',
    labelKey: 'relationLeader',
    recommendedTone: 'formal',
    colorClass: 'text-purple-600 dark:text-purple-400 bg-purple-500/10',
  },
  colleague: {
    relationship: 'colleague',
    labelKey: 'relationColleague',
    recommendedTone: 'semi-formal',
    colorClass: 'text-blue-600 dark:text-blue-400 bg-blue-500/10',
  },
  partner: {
    relationship: 'partner',
    labelKey: 'relationPartner',
    recommendedTone: 'formal',
    colorClass: 'text-amber-600 dark:text-amber-400 bg-amber-500/10',
  },
  teammate: {
    relationship: 'teammate',
    labelKey: 'relationTeammate',
    recommendedTone: 'friendly',
    colorClass: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10',
  },
};

export interface ChannelConfig {
  channel: OutboundChannelType;
  /** `digitalSelf` message key of the channel's name. */
  labelKey: string;
}

export const CHANNEL_CONFIGS: Record<OutboundChannelType, ChannelConfig> = {
  feishu: { channel: 'feishu', labelKey: 'channelFeishu' },
  dingtalk: { channel: 'dingtalk', labelKey: 'channelDingtalk' },
  wechat: { channel: 'wechat', labelKey: 'channelWechat' },
  email: { channel: 'email', labelKey: 'channelEmail' },
  slack: { channel: 'slack', labelKey: 'channelSlack' },
};

export interface OutboundAuditRecord {
  recordId: string;
  draftId: string;
  channel: OutboundChannelType;
  recipientName: string;
  finalContent: string;
  sentAt: number;
  confirmedByHuman: true;
}
