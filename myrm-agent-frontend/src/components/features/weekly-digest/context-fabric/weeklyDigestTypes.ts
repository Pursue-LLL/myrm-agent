export type ChannelType = 'feishu' | 'wechat' | 'desktop' | 'web' | 'cli';

export type FootprintCategory =
  | 'pr-review'
  | 'rfc-decision'
  | 'deliverable'
  | 'learning'
  | 'risk-roadblock';

export interface ChannelFootprintItem {
  id: string;
  channel: ChannelType;
  category: FootprintCategory;
  title: string;
  description: string;
  metrics?: string;
  artifactRef?: string;
  timestamp: number;
  includedInDigest: boolean;
}

export type DigestStylePreset = 'executive' | 'technical' | 'bullet';

export interface WeeklyDigestSummary {
  id: string;
  weekIdentifier: string;
  dateRange: string;
  stylePreset: DigestStylePreset;
  accomplishments: string[];
  keyDecisions: string[];
  codeLearnings: string[];
  pendingRisks: string[];
  nextSteps: string[];
  markdownContent: string;
  synthesizedAt: number;
}

export interface RefinementInstruction {
  id: string;
  prompt: string;
  appliedAt: number;
}
