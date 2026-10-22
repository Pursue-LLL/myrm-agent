import { describe, it, expect, beforeEach } from 'vitest';
import {
  useReferralFissionStore,
  generateCsprngRandomSlug,
  validateZeroDoxSlug,
  weaveReferralIntoTemplateUrl,
} from '../useReferralFissionStore';

describe('useReferralFissionStore & Zero-Dox Utilities', () => {
  beforeEach(() => {
    useReferralFissionStore.getState().resetState();
  });

  describe('generateCsprngRandomSlug', () => {
    it('generates a clean random string with specified length', () => {
      const slug7 = generateCsprngRandomSlug(7);
      expect(slug7).toHaveLength(7);
      expect(slug7).toMatch(/^[a-z2-9]+$/);
      // 确认排除了容易混淆的字符
      expect(slug7).not.toContain('0');
      expect(slug7).not.toContain('o');
      expect(slug7).not.toContain('1');
      expect(slug7).not.toContain('l');
    });
  });

  describe('validateZeroDoxSlug', () => {
    it('approves compliant pseudonymous slugs', () => {
      const res1 = validateZeroDoxSlug('geek-pilot');
      expect(res1.isValid).toBe(true);

      const res2 = validateZeroDoxSlug('cyber_ninja_99');
      expect(res2.isValid).toBe(true);
    });

    it('rejects slugs that are too short or too long', () => {
      const tooShort = validateZeroDoxSlug('abc');
      expect(tooShort.isValid).toBe(false);
      expect(tooShort.reason).toContain('长度');

      const tooLong = validateZeroDoxSlug('a'.repeat(25));
      expect(tooLong.isValid).toBe(false);
    });

    it('rejects system reserved keywords', () => {
      const res = validateZeroDoxSlug('admin');
      expect(res.isValid).toBe(false);
      expect(res.reason).toContain('系统保留');

      const res2 = validateZeroDoxSlug('myrm');
      expect(res2.isValid).toBe(false);
    });

    it('blocks email, domain and phone PII to prevent doxxing', () => {
      const emailLike = validateZeroDoxSlug('john@gmail.com');
      expect(emailLike.isValid).toBe(false);

      const dotCom = validateZeroDoxSlug('alice-tech.com');
      expect(dotCom.isValid).toBe(false);
      expect(dotCom.reason).toContain('Zero-Dox');

      const phoneLike = validateZeroDoxSlug('13800138000');
      expect(phoneLike.isValid).toBe(false);
    });

    it('intercepts user real name and sensitive PII blacklist', () => {
      const blacklist = ['JohnSmith', 'zhangsan', 'yululiu'];

      const leakAttempt = validateZeroDoxSlug('zhangsan-ai', blacklist);
      expect(leakAttempt.isValid).toBe(false);
      expect(leakAttempt.reason).toContain('真实姓名');
    });
  });

  describe('weaveReferralIntoTemplateUrl', () => {
    it('seamlessly weaves referral slug into agent template url', () => {
      const url = weaveReferralIntoTemplateUrl('fullstack-architect', 'k7m9xp');
      expect(url).toBe('https://myrmagent.ai/t/fullstack-architect?ref=k7m9xp');
    });
  });

  describe('useReferralFissionStore actions', () => {
    it('updates custom slug when valid and rejects when invalid', () => {
      const store = useReferralFissionStore.getState();

      const invalidAttempt = store.updateCustomSlug('root');
      expect(invalidAttempt.isValid).toBe(false);
      expect(useReferralFissionStore.getState().profile.isCustomSlug).toBe(false);

      const validAttempt = store.updateCustomSlug('algo-master');
      expect(validAttempt.isValid).toBe(true);
      expect(useReferralFissionStore.getState().profile.slug).toBe('algo-master');
      expect(useReferralFissionStore.getState().profile.isCustomSlug).toBe(true);
    });

    it('resets custom slug back to CSPRNG random slug', () => {
      const store = useReferralFissionStore.getState();
      store.updateCustomSlug('my-custom-alias');
      expect(useReferralFissionStore.getState().profile.slug).toBe('my-custom-alias');

      store.resetToRandomSlug();
      expect(useReferralFissionStore.getState().profile.isCustomSlug).toBe(false);
      expect(useReferralFissionStore.getState().profile.slug).not.toBe('my-custom-alias');
    });

    it('records successful referral and increases credit ledger', () => {
      const store = useReferralFissionStore.getState();
      const initialBalance = store.ledger.availableBalanceUsd;
      const initialCount = store.ledger.totalInvitedCount;

      store.recordSuccessfulReferral('direct_invite', 'anon-999');

      const updated = useReferralFissionStore.getState();
      expect(updated.ledger.availableBalanceUsd).toBe(initialBalance + 10);
      expect(updated.ledger.totalInvitedCount).toBe(initialCount + 1);
      expect(updated.records[0]?.inviteePseudonym).toBe('anon-999');
    });
  });
});
