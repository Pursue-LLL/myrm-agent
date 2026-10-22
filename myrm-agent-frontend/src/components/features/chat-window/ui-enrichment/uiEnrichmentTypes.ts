export interface AuthoritativeFactRecord {
  id: string;
  officialTitle: string;
  officialPrice: number;
  officialCurrency: 'CNY' | 'USD' | 'EUR';
  stockStatus: 'in_stock' | 'low_stock' | 'out_of_stock';
  verifiedWeekday?: string;
  effectiveDate?: string;
}

export interface ModelJudgmentInput {
  id: string;
  rank?: number;
  userNote?: string;
  comparisonHighlight?: string;
}

export interface EnrichedUiCardItem {
  id: string;
  officialTitle: string;
  officialPrice: number;
  officialCurrency: string;
  stockStatus: 'in_stock' | 'low_stock' | 'out_of_stock';
  sanitizedNote: string;
  comparisonHighlight?: string;
  rank: number;
  isEnriched: true;
}

export interface EnrichmentAuditLog {
  totalRequested: number;
  enrichedCount: number;
  droppedUnknownIds: string[];
  currencyFixedCount: number;
  temporalFixedCount: number;
  auditNotes: string[];
}

export interface EnrichedPresentationResult {
  presentationId: string;
  items: EnrichedUiCardItem[];
  auditLog: EnrichmentAuditLog;
  createdAt: number;
}
