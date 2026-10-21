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
  labelKey: string;
  displayName: string;
  description: string;
  colorClass: string;
}

export const TONE_STYLE_CONFIGS: Record<ToneStyle, ToneStyleConfig> = {
  formal: {
    style: 'formal',
    labelKey: 'toneFormal',
    displayName: '严谨正式',
    description: '措辞严谨礼貌，适合上级汇报、公文或正式商务往来',
    colorClass: 'text-indigo-600 dark:text-indigo-400 bg-indigo-500/10 border-indigo-500/30',
  },
  'semi-formal': {
    style: 'semi-formal',
    labelKey: 'toneSemiFormal',
    displayName: '职场得体',
    description: '务实高效且不失礼貌，适合日常跨部门协同与业务对齐',
    colorClass: 'text-sky-600 dark:text-sky-400 bg-sky-500/10 border-sky-500/30',
  },
  friendly: {
    style: 'friendly',
    labelKey: 'toneFriendly',
    displayName: '友好活泼',
    description: '亲和自然，带有适当语气助词，适合组内伙伴与熟悉协作者',
    colorClass: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  },
  concise: {
    style: 'concise',
    labelKey: 'toneConcise',
    displayName: '简明干练',
    description: '开门见山，突出关键结论与行动项，拒绝冗长客套',
    colorClass: 'text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/30',
  },
};

export interface RelationshipConfig {
  relationship: RecipientRelationship;
  displayName: string;
  recommendedTone: ToneStyle;
  colorClass: string;
}

export const RELATIONSHIP_CONFIGS: Record<RecipientRelationship, RelationshipConfig> = {
  leader: {
    relationship: 'leader',
    displayName: '直属领导',
    recommendedTone: 'formal',
    colorClass: 'text-purple-600 dark:text-purple-400 bg-purple-500/10',
  },
  colleague: {
    relationship: 'colleague',
    displayName: '协作同事',
    recommendedTone: 'semi-formal',
    colorClass: 'text-blue-600 dark:text-blue-400 bg-blue-500/10',
  },
  partner: {
    relationship: 'partner',
    displayName: '外部客户/伙伴',
    recommendedTone: 'formal',
    colorClass: 'text-amber-600 dark:text-amber-400 bg-amber-500/10',
  },
  teammate: {
    relationship: 'teammate',
    displayName: '组内伙伴',
    recommendedTone: 'friendly',
    colorClass: 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10',
  },
};

export interface ChannelConfig {
  channel: OutboundChannelType;
  displayName: string;
}

export const CHANNEL_CONFIGS: Record<OutboundChannelType, ChannelConfig> = {
  feishu: { channel: 'feishu', displayName: '飞书' },
  dingtalk: { channel: 'dingtalk', displayName: '钉钉' },
  wechat: { channel: 'wechat', displayName: '企业微信' },
  email: { channel: 'email', displayName: '工作邮件' },
  slack: { channel: 'slack', displayName: 'Slack' },
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
