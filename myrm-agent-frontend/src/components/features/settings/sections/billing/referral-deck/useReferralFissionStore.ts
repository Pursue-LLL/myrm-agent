import { create } from 'zustand';
import type {
  CreditLedger,
  FraudRiskAudit,
  ReferralEarningRecord,
  ReferralFissionState,
  ReferralProfile,
  ZeroDoxValidationResult,
} from './referralDeckTypes';

const RESERVED_SLUGS = new Set([
  'admin',
  'administrator',
  'official',
  'myrm',
  'myrmagent',
  'system',
  'api',
  'auth',
  'login',
  'root',
  'support',
  'billing',
  'settings',
  'explore',
]);

const PII_PATTERNS = [
  /@/,
  /\.com$/i,
  /\.cn$/i,
  /\.net$/i,
  /\.io$/i,
  /\.org$/i,
  /^\+?\d{7,15}$/, // 手机号或长数字串
];

/**
 * 基于 CSPRNG 安全随机数生成无语义短哈希，彻底杜绝人肉开盒
 */
export function generateCsprngRandomSlug(length = 7): string {
  const chars = 'abcdefghjkmnpqrstuvwxyz23456789'; // 剔除易混淆的 0, o, 1, l, i
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
    const values = new Uint8Array(length);
    crypto.getRandomValues(values);
    let result = '';
    for (let i = 0; i < length; i++) {
      const byte = values[i] ?? 0;
      result += chars[byte % chars.length];
    }
    return result;
  }
  // 备用降级
  let fallback = '';
  for (let i = 0; i < length; i++) {
    fallback += chars[Math.floor(Math.random() * chars.length)];
  }
  return fallback;
}

/**
 * 严格校验自定义伪名 Slug 是否遵循 Zero-Dox 安全红线
 */
export function validateZeroDoxSlug(
  candidate: string,
  userPiiBlacklist: string[] = []
): ZeroDoxValidationResult {
  const normalized = candidate.trim().toLowerCase();

  if (normalized.length < 4 || normalized.length > 24) {
    return {
      isValid: false,
      reason: 'Slug 长度需保持在 4 ~ 24 个字符之间',
    };
  }

  for (const pattern of PII_PATTERNS) {
    if (pattern.test(normalized)) {
      return {
        isValid: false,
        reason: '检测到邮箱、域名或电话特征，触发 Zero-Dox 隐私保护阻断',
      };
    }
  }

  for (const pii of userPiiBlacklist) {
    const cleanPii = pii.trim().toLowerCase();
    if (cleanPii.length >= 3 && normalized.includes(cleanPii)) {
      return {
        isValid: false,
        reason: '严禁包含您的真实姓名、全名拼音或私有身份凭据，以防人肉开盒',
      };
    }
  }

  if (RESERVED_SLUGS.has(normalized)) {
    return {
      isValid: false,
      reason: '该标识符为系统保留关键字，请选用其他个性化代号',
    };
  }

  const validCharRegex = /^[a-z0-9_-]+$/;
  if (!validCharRegex.test(normalized)) {
    return {
      isValid: false,
      reason: '仅允许包含小写字母、数字、短破折号 (-) 与下划线 (_)',
    };
  }

  return { isValid: true };
}

/**
 * 将智能体模板短链与推荐短码无感编织为裂变推广链接
 */
export function weaveReferralIntoTemplateUrl(
  templateSlug: string,
  referralSlug: string,
  origin = 'https://myrmagent.ai'
): string {
  const cleanTemplate = templateSlug.replace(/^\/+/, '');
  return `${origin}/t/${cleanTemplate}?ref=${encodeURIComponent(referralSlug)}`;
}

interface ReferralFissionActions {
  updateCustomSlug: (newSlug: string, piiBlacklist?: string[]) => ZeroDoxValidationResult;
  resetToRandomSlug: () => void;
  setEditingSlug: (isEditing: boolean) => void;
  triggerCopyNotice: () => void;
  dismissNotice: () => void;
  recordSuccessfulReferral: (
    type: 'direct_invite' | 'cloud_kickback' | 'template_clone',
    inviteePseudonym?: string
  ) => void;
  resetState: () => void;
}

export type ReferralFissionStore = ReferralFissionState & ReferralFissionActions;

const initialSlug = generateCsprngRandomSlug(7);

const INITIAL_PROFILE: ReferralProfile = {
  referralId: `ref-${Date.now().toString(36)}`,
  slug: initialSlug,
  isCustomSlug: false,
  isZeroDoxVerified: true,
  createdAt: Date.now(),
};

const INITIAL_LEDGER: CreditLedger = {
  rewardPerInviteUsd: 10,
  inviteeDiscountUsd: 15,
  cloudKickbackRate: 0.1,
  totalEarnedUsd: 65,
  availableBalanceUsd: 45,
  totalCloudKickbackUsd: 15,
  totalInvitedCount: 5,
  activeCloudSubscribersCount: 2,
};

const INITIAL_RECORDS: ReferralEarningRecord[] = [
  {
    id: 'rec-001',
    type: 'direct_invite',
    amountUsd: 10,
    inviteePseudonym: 'anon-7f2a',
    timestamp: Date.now() - 86400000 * 2,
    note: '新用户通过您的短链注册云端沙箱',
  },
  {
    id: 'rec-002',
    type: 'cloud_kickback',
    amountUsd: 5,
    inviteePseudonym: 'anon-3c9d',
    timestamp: Date.now() - 86400000,
    note: '受邀伙伴续费专业云端沙箱，获得 10% 算力返佣',
  },
  {
    id: 'rec-003',
    type: 'template_clone',
    amountUsd: 10,
    inviteePseudonym: 'anon-8e1b',
    timestamp: Date.now() - 3600000 * 4,
    note: '通过您分享的「全栈架构师」智能体模板完成转化',
  },
];

const INITIAL_RISK: FraudRiskAudit = {
  status: 'healthy',
  deviceFingerprintVerified: true,
  canvasEntropyPassed: true,
  subnetRiskScore: 4,
  lastAuditedAt: Date.now(),
};

export const useReferralFissionStore = create<ReferralFissionStore>((set, get) => ({
  profile: INITIAL_PROFILE,
  ledger: INITIAL_LEDGER,
  records: INITIAL_RECORDS,
  riskAudit: INITIAL_RISK,
  isEditingSlug: false,
  copiedNoticeVisible: false,

  updateCustomSlug: (newSlug: string, piiBlacklist: string[] = []) => {
    const validation = validateZeroDoxSlug(newSlug, piiBlacklist);
    if (!validation.isValid) {
      return validation;
    }

    const normalized = newSlug.trim().toLowerCase();
    set((state) => ({
      profile: {
        ...state.profile,
        slug: normalized,
        isCustomSlug: true,
        isZeroDoxVerified: true,
      },
      isEditingSlug: false,
    }));

    return { isValid: true };
  },

  resetToRandomSlug: () => {
    const randomSlug = generateCsprngRandomSlug(7);
    set((state) => ({
      profile: {
        ...state.profile,
        slug: randomSlug,
        isCustomSlug: false,
        isZeroDoxVerified: true,
      },
      isEditingSlug: false,
    }));
  },

  setEditingSlug: (isEditing: boolean) => {
    set({ isEditingSlug: isEditing });
  },

  triggerCopyNotice: () => {
    set({ copiedNoticeVisible: true });
  },

  dismissNotice: () => {
    set({ copiedNoticeVisible: false });
  },

  recordSuccessfulReferral: (
    type: 'direct_invite' | 'cloud_kickback' | 'template_clone',
    inviteePseudonym?: string
  ) => {
    const pseudonym = inviteePseudonym || `anon-${Math.random().toString(36).slice(2, 6)}`;
    const amount = type === 'cloud_kickback' ? 5 : 10;
    const newRecord: ReferralEarningRecord = {
      id: `rec-${Date.now()}`,
      type,
      amountUsd: amount,
      inviteePseudonym: pseudonym,
      timestamp: Date.now(),
      note:
        type === 'cloud_kickback'
          ? '云端沙箱包月续费 10% 算力返佣'
          : '受邀伙伴完成注册并激活工作区',
    };

    set((state) => ({
      ledger: {
        ...state.ledger,
        totalEarnedUsd: state.ledger.totalEarnedUsd + amount,
        availableBalanceUsd: state.ledger.availableBalanceUsd + amount,
        totalCloudKickbackUsd:
          type === 'cloud_kickback'
            ? state.ledger.totalCloudKickbackUsd + amount
            : state.ledger.totalCloudKickbackUsd,
        totalInvitedCount:
          type !== 'cloud_kickback'
            ? state.ledger.totalInvitedCount + 1
            : state.ledger.totalInvitedCount,
      },
      records: [newRecord, ...state.records],
    }));
  },

  resetState: () => {
    set({
      profile: {
        ...INITIAL_PROFILE,
        slug: generateCsprngRandomSlug(7),
      },
      ledger: INITIAL_LEDGER,
      records: INITIAL_RECORDS,
      riskAudit: INITIAL_RISK,
      isEditingSlug: false,
      copiedNoticeVisible: false,
    });
  },
}));
