import type { ApprovalPayloadData } from '@/store/useApprovalStore';

type ReviewConfig = NonNullable<ApprovalPayloadData['reviewConfigs']>[number];

/** What a spend approval would charge, and the digest that ties the approval to this exact action. */
export interface SpendConfig {
  amount?: number;
  currency: string;
  actionDigest?: string;
}

/** What the per-tool review configs of an approval say about how it is shown and decided. */
export interface ApprovalFlags {
  hasAnySmartDenied: boolean;
  /** Which limit turned auto mode off (`consecutive` or the total one); absent while auto mode is on. */
  autoModeSuspendedBreach?: string;
  isSociallyIrreversible: boolean;
  isIrreversibleDestructive: boolean;
  destructiveBlastRadius?: ReviewConfig['blastRadius'];
  destructiveSnapshotId?: string;
  /** Spend, social and irreversible actions are never offered a standing "always allow". */
  hasAnyHideAllowAlways: boolean;
  spendConfig: SpendConfig | null;
}

export function deriveApprovalFlags(payload: ApprovalPayloadData | undefined): ApprovalFlags {
  // A malformed payload degrades to "no flags" instead of throwing while the approval is on screen.
  const reviewConfigs = payload?.reviewConfigs;
  const configs = Array.isArray(reviewConfigs) ? reviewConfigs : [];

  const isSociallyIrreversible = configs.some((c) => c?.sociallyIrreversible === true);
  const isIrreversibleDestructive =
    payload?.irreversibleDestructive === true || configs.some((c) => c?.irreversibleDestructive === true);
  const spend = configs.find((c) => c?.isSpend === true);

  return {
    hasAnySmartDenied: configs.some((c) => c?.smartDenied === true),
    autoModeSuspendedBreach: configs.find(
      (c) => typeof c?.autoModeSuspended === 'string' && c.autoModeSuspended.length > 0,
    )?.autoModeSuspended,
    isSociallyIrreversible,
    isIrreversibleDestructive,
    destructiveBlastRadius: configs.find((c) => c?.blastRadius)?.blastRadius,
    destructiveSnapshotId: payload?.snapshotId || configs.find((c) => c?.snapshotId)?.snapshotId,
    hasAnyHideAllowAlways:
      isSociallyIrreversible ||
      isIrreversibleDestructive ||
      configs.some((c) => c?.hideAllowAlways === true || c?.isSpend === true),
    spendConfig: spend
      ? { amount: spend.spendAmount, currency: spend.spendCurrency || 'USD', actionDigest: spend.actionDigest }
      : null,
  };
}
