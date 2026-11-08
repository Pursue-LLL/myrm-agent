import { describe, expect, it } from 'vitest';
import type { ApprovalPayloadData } from '@/store/useApprovalStore';
import { deriveApprovalFlags } from '../approvalFlags';
import { noFlags } from './approvalKit';

type ReviewConfigs = NonNullable<ApprovalPayloadData['reviewConfigs']>;

const withConfigs = (...configs: ReviewConfigs): ApprovalPayloadData => ({ reviewConfigs: configs });

describe('deriveApprovalFlags', () => {
  it('raises no flag for a missing payload or missing review configs', () => {
    expect(deriveApprovalFlags(undefined)).toEqual(noFlags);
    expect(deriveApprovalFlags({})).toEqual(noFlags);
    expect(deriveApprovalFlags(withConfigs())).toEqual(noFlags);
    expect(deriveApprovalFlags(withConfigs({}, {}))).toEqual(noFlags);
  });

  it('degrades malformed review configs to no flags instead of throwing', () => {
    const notAnArray = { reviewConfigs: 'oops' } as unknown as ApprovalPayloadData;
    const withHoles = { reviewConfigs: [null, undefined, { smartDenied: true }] } as unknown as ApprovalPayloadData;

    expect(deriveApprovalFlags(notAnArray)).toEqual(noFlags);
    expect(deriveApprovalFlags(withHoles)).toEqual({ ...noFlags, hasAnySmartDenied: true });
  });

  it('counts only the boolean true as a raised flag', () => {
    const truthyButNotTrue = withConfigs({
      smartDenied: 'true',
      sociallyIrreversible: 1,
      irreversibleDestructive: 'yes',
      hideAllowAlways: 'true',
      isSpend: 1,
    } as unknown as ReviewConfigs[number]);

    expect(deriveApprovalFlags(truthyButNotTrue)).toEqual(noFlags);
    expect(deriveApprovalFlags({ irreversibleDestructive: 'yes' } as unknown as ApprovalPayloadData)).toEqual(noFlags);
  });

  it('reports a smart-denied tool from any config', () => {
    const flags = deriveApprovalFlags(withConfigs({}, { smartDenied: true }));

    expect(flags).toEqual({ ...noFlags, hasAnySmartDenied: true });
  });

  it('keeps standing grants off a socially irreversible action', () => {
    const flags = deriveApprovalFlags(withConfigs({}, { sociallyIrreversible: true }));

    expect(flags).toEqual({ ...noFlags, isSociallyIrreversible: true, hasAnyHideAllowAlways: true });
  });

  it.each([
    ['the payload', { irreversibleDestructive: true } satisfies ApprovalPayloadData],
    ['a config', withConfigs({}, { irreversibleDestructive: true })],
  ])('treats an action marked irreversible by %s as destructive and keeps standing grants off it', (_, payload) => {
    const flags = deriveApprovalFlags(payload);

    expect(flags).toEqual({ ...noFlags, isIrreversibleDestructive: true, hasAnyHideAllowAlways: true });
  });

  it('keeps standing grants off a config that hides them, and nothing else changes', () => {
    const flags = deriveApprovalFlags(withConfigs({ hideAllowAlways: true }));

    expect(flags).toEqual({ ...noFlags, hasAnyHideAllowAlways: true });
  });

  describe('spend', () => {
    it('describes the first spend config and keeps standing grants off it', () => {
      const flags = deriveApprovalFlags(
        withConfigs(
          { spendAmount: 1, actionDigest: 'not-a-spend' },
          { isSpend: true, spendAmount: 12.5, spendCurrency: 'EUR', actionDigest: 'digest-1' },
          { isSpend: true, spendAmount: 99, spendCurrency: 'JPY', actionDigest: 'digest-2' },
        ),
      );

      expect(flags.spendConfig).toEqual({ amount: 12.5, currency: 'EUR', actionDigest: 'digest-1' });
      expect(flags.hasAnyHideAllowAlways).toBe(true);
    });

    it('charges in USD when the config names no currency, and keeps a zero amount', () => {
      expect(deriveApprovalFlags(withConfigs({ isSpend: true, spendAmount: 0 })).spendConfig).toEqual({
        amount: 0,
        currency: 'USD',
        actionDigest: undefined,
      });
      expect(deriveApprovalFlags(withConfigs({ isSpend: true, spendCurrency: '' })).spendConfig).toEqual({
        amount: undefined,
        currency: 'USD',
        actionDigest: undefined,
      });
    });

    it('has no spend config when no config is a spend', () => {
      expect(deriveApprovalFlags(withConfigs({ isSpend: false, spendAmount: 5 })).spendConfig).toBeNull();
    });
  });

  describe('auto mode suspension', () => {
    it('names the limit of the first config that carries one', () => {
      const flags = deriveApprovalFlags(
        withConfigs(
          {},
          { autoModeSuspended: '' },
          { autoModeSuspended: 'consecutive' },
          { autoModeSuspended: 'total' },
        ),
      );

      expect(flags.autoModeSuspendedBreach).toBe('consecutive');
    });

    it('ignores an empty or non-string value', () => {
      const flags = deriveApprovalFlags(
        withConfigs({ autoModeSuspended: '' }, { autoModeSuspended: true as unknown as string }),
      );

      expect(flags.autoModeSuspendedBreach).toBeUndefined();
    });
  });

  describe('destructive details', () => {
    const blastRadius = { command: 'rm -rf build', destructiveCount: 3 };

    it('takes the blast radius of the first config that has one', () => {
      const flags = deriveApprovalFlags(withConfigs({}, { blastRadius }, { blastRadius: { command: 'other' } }));

      expect(flags.destructiveBlastRadius).toEqual(blastRadius);
    });

    it('prefers the snapshot of the payload over those of the configs', () => {
      const flags = deriveApprovalFlags({ snapshotId: 'snap-payload', ...withConfigs({ snapshotId: 'snap-config' }) });

      expect(flags.destructiveSnapshotId).toBe('snap-payload');
    });

    it('falls back to the first config snapshot when the payload has none or an empty one', () => {
      const configs = withConfigs({}, { snapshotId: 'snap-1' }, { snapshotId: 'snap-2' });

      expect(deriveApprovalFlags(configs).destructiveSnapshotId).toBe('snap-1');
      expect(deriveApprovalFlags({ ...configs, snapshotId: '' }).destructiveSnapshotId).toBe('snap-1');
    });
  });
});
