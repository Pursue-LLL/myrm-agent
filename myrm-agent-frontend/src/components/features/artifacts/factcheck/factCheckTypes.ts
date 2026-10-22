/**
 * Types and contracts for Fact Check & Controlled Fabrication Audit Suite.
 * Adheres to WorkBuddy fact verification paradigm with zero emojis.
 */

export interface PlaceholderItem {
  id: string;
  originalText: string;
  placeholderKey: string;
  contextSnippet: string;
  replacedValue?: string;
  status: 'pending' | 'replaced';
  index: number;
}

export interface VerifiedFactItem {
  id: string;
  factStatement: string;
  verifiedValue: string;
  sourceName: string;
  sourceUrl?: string;
  verifiedAt: string;
}

export interface FactCheckAuditReport {
  totalPlaceholders: number;
  pendingCount: number;
  replacedCount: number;
  placeholders: PlaceholderItem[];
  verifiedFacts: VerifiedFactItem[];
  hasFabrications: boolean;
}

export type FactCheckDrawerTab = 'placeholders' | 'verified';
