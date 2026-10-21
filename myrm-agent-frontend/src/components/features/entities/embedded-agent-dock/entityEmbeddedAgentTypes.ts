/**
 * 业务实体内置专属智能体抽屉、推演步态透明账本与带签名免拷贝上下文信使契约定义
 */

export type BusinessEntityType = 'contact' | 'company' | 'deal' | 'project' | 'document';

export interface BusinessEntitySnapshot {
  id: string;
  type: BusinessEntityType;
  title: string;
  subtitle?: string;
  metadata: Record<string, string | number>;
}

export interface SignedRecordToken {
  tokenString: string;
  signature: string;
  issuedAt: number;
  entitySnapshot: BusinessEntitySnapshot;
}

export type DossierStepStatus = 'searching' | 'verified' | 'discarded' | 'pending_decision';

export interface DisambiguationOption {
  id: string;
  label: string;
  description: string;
}

export interface DossierStepRecord {
  id: string;
  timestamp: number;
  title: string;
  status: DossierStepStatus;
  evidenceSource?: string;
  discardedReason?: string; // 明确解释为何排除该线索
  disambiguationPrompt?: string;
  disambiguationOptions?: DisambiguationOption[];
  resolvedOptionId?: string;
}

export interface EntityEmbeddedChatMessage {
  id: string;
  sender: 'user' | 'agent' | 'system';
  text: string;
  timestamp: number;
}

export interface EntityEmbeddedAgentState {
  isDockOpen: boolean;
  activeEntity: BusinessEntitySnapshot | null;
  currentSignedToken: SignedRecordToken | null;
  stepLedger: DossierStepRecord[];
  chatHistory: EntityEmbeddedChatMessage[];
  isAnalyzing: boolean;
}
