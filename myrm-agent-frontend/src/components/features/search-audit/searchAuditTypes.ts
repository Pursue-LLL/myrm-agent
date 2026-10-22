/**
 * 全透明检索链路审计与 100 分数据源量化质量矩阵数据模型
 */

export type SourceTier =
  | 'academic'
  | 'official_code'
  | 'sec_finance'
  | 'tech_media'
  | 'community'
  | 'unverified';

export interface SourceQualityMatrix {
  authorityScore: number;
  freshnessScore: number;
  signalToNoiseScore: number;
  firstHandScore: number;
  compositeScore: number;
  tier: SourceTier;
  tierLabel: string;
  verificationBadge: string;
}

export interface SubQueryTrace {
  subQueryId: string;
  queryText: string;
  category: 'academic' | 'finance' | 'code' | 'general';
  latencyMs: number;
  payloadBytes: number;
  isFullText: boolean;
  hasAiRewrite: boolean;
  timestamp: number;
}

export interface AuditCitationItem {
  id: string;
  url: string;
  domain: string;
  title: string;
  rawSnippet: string;
  fullTextSnippet?: string;
  subQueryId: string;
  qualityMatrix: SourceQualityMatrix;
}

export interface SearchAuditSession {
  auditSessionId: string;
  parentMessageId: string;
  totalLatencyMs: number;
  totalPayloadBytes: number;
  averageQualityScore: number;
  traces: SubQueryTrace[];
  citations: AuditCitationItem[];
  createdAt: number;
}
