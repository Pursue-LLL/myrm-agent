/**
/**
 * 双向算力赠金裂变、Zero-Dox 匿名个性化推荐短链与反人肉隐私保护套件契约
 */

export interface ReferralProfile {
  referralId: string;
  slug: string;
  isCustomSlug: boolean;
  isZeroDoxVerified: boolean;
  createdAt: number;
}

export interface CreditLedger {
  rewardPerInviteUsd: number; // 默认 10 美元
  inviteeDiscountUsd: number; // 默认 15 美元立减
  cloudKickbackRate: number; // 10% 云端沙箱包月返佣
  totalEarnedUsd: number;
  availableBalanceUsd: number;
  totalCloudKickbackUsd: number;
  totalInvitedCount: number;
  activeCloudSubscribersCount: number;
}

export type EarningRecordType = 'direct_invite' | 'cloud_kickback' | 'template_clone';

export interface ReferralEarningRecord {
  id: string;
  type: EarningRecordType;
  amountUsd: number;
  inviteePseudonym: string; // 严格使用匿名代号，如 anon-7b3e，杜绝真实姓名
  timestamp: number;
  note: string;
}

export type FraudRiskStatus = 'healthy' | 'reviewing' | 'flagged';

export interface FraudRiskAudit {
  status: FraudRiskStatus;
  deviceFingerprintVerified: boolean;
  canvasEntropyPassed: boolean;
  subnetRiskScore: number; // 0 - 100，小于 20 表示极优健康
  lastAuditedAt: number;
}

export interface ZeroDoxValidationResult {
  isValid: boolean;
  reason?: string;
}

export interface ReferralFissionState {
  profile: ReferralProfile;
  ledger: CreditLedger;
  records: ReferralEarningRecord[];
  riskAudit: FraudRiskAudit;
  isEditingSlug: boolean;
  copiedNoticeVisible: boolean;
}
