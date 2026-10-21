/** Discover install toast resolver — maps install API fields to a single toast payload.

[INPUT]
- settings.skills.discover locale keys (POS: Install success/allowlist toast copy)

[OUTPUT]
- resolveSkillInstallToastMessage: Pure message keys/variant from API response
- formatSkillInstallToast: Localized title/description for toast()

[POS]
Discover / URL install feedback helper. Shared toast mapping for market install responses.
*/

export type SkillInstallToastResponse = {
  mounted?: boolean;
  mount_error?: string;
  mount_already_present?: boolean;
  allowlist_appended?: boolean;
  allowlist_append_error?: string;
  /** True when the operation was a marketplace version update (not fresh install). */
  marketUpdate?: boolean;
  pre_replace_batch_id?: string | null;
  snapshot_truncated?: boolean;
};

export type SkillInstallToastCallbacks = {
  onTrialRun?: () => void;
  onRollbackPreUpdate?: () => void;
};

export type SkillInstallToastMessage = {
  titleKey: string;
  titleParams?: { name: string };
  descriptionKey?: string;
  descriptionText?: string;
  variant?: 'destructive';
};

type TranslateFn = (key: string, params?: Record<string, string>) => string;

export function toSkillInstallToastResponse(
  response: SkillInstallToastResponse & {
    mounted?: boolean;
    mount_error?: string;
    mount_already_present?: boolean;
    allowlist_appended?: boolean;
    allowlist_append_error?: string;
    pre_replace_batch_id?: string | null;
    snapshot_truncated?: boolean;
  },
  marketUpdate: boolean,
): SkillInstallToastResponse {
  return {
    mounted: response.mounted,
    mount_error: response.mount_error,
    mount_already_present: response.mount_already_present,
    allowlist_appended: response.allowlist_appended,
    allowlist_append_error: response.allowlist_append_error,
    marketUpdate,
    pre_replace_batch_id: response.pre_replace_batch_id,
    snapshot_truncated: response.snapshot_truncated,
  };
}

function withReplaceSnapshotDescription(
  message: SkillInstallToastMessage,
  response: SkillInstallToastResponse,
): SkillInstallToastMessage {
  if (message.descriptionKey || message.descriptionText) {
    return message;
  }
  if (response.snapshot_truncated) {
    return { ...message, descriptionKey: 'snapshotTruncatedDesc' };
  }
  if (response.pre_replace_batch_id?.trim()) {
    return { ...message, descriptionKey: 'restorePreUpdateSkillMdDesc' };
  }
  return message;
}

/** Resolve a single install toast from discovery install API fields. */
export function resolveSkillInstallToastMessage(
  skillName: string,
  response: SkillInstallToastResponse,
): SkillInstallToastMessage {
  if (response.marketUpdate && !response.mount_error) {
    return {
      titleKey: 'updatedSuccess',
      titleParams: { name: skillName },
      descriptionKey: response.snapshot_truncated
        ? 'snapshotTruncatedDesc'
        : response.pre_replace_batch_id
          ? 'restorePreUpdateSkillMdDesc'
          : undefined,
    };
  }

  if (response.mounted && !response.mount_error) {
    if (response.allowlist_append_error) {
      return {
        titleKey: 'installedAllowlistAppendFailed',
        titleParams: { name: skillName },
        descriptionKey: 'installedAllowlistAppendFailedDesc',
        variant: 'destructive',
      };
    }

    const titleKey = response.mount_already_present ? 'installedAlreadyEnabled' : 'installedAndEnabled';

    if (response.allowlist_appended) {
      return {
        titleKey,
        titleParams: { name: skillName },
        descriptionKey: 'installedAllowlistAppendedDesc',
      };
    }

    return {
      titleKey,
      titleParams: { name: skillName },
    };
  }

  if (response.mount_error) {
    return {
      titleKey: 'installedEnableFailed',
      titleParams: { name: skillName },
      descriptionText: response.mount_error,
      variant: 'destructive',
    };
  }

  return {
    titleKey: 'installed',
  };
}

export function formatSkillInstallToast(
  skillName: string,
  response: SkillInstallToastResponse,
  t: TranslateFn,
  callbacks?: SkillInstallToastCallbacks,
): { title: string; description?: string; variant?: 'destructive'; action?: { label: string; onClick: () => void } } {
  const message = withReplaceSnapshotDescription(resolveSkillInstallToastMessage(skillName, response), response);

  const isSuccess = message.variant !== 'destructive';
  const batchId = response.pre_replace_batch_id?.trim();
  const action =
    isSuccess && batchId && callbacks?.onRollbackPreUpdate
      ? {
          label: t('restorePreUpdateSkillMd'),
          onClick: callbacks.onRollbackPreUpdate,
        }
      : isSuccess && callbacks?.onTrialRun
        ? {
            label: t('trialRunCTA') || '即刻试跑',
            onClick: callbacks.onTrialRun,
          }
        : undefined;

  return {
    title:
      message.titleKey === 'installed'
        ? `${t('installed')} ${skillName}`
        : t(message.titleKey, message.titleParams ?? { name: skillName }),
    description: message.descriptionText ?? (message.descriptionKey ? t(message.descriptionKey) : undefined),
    variant: message.variant,
    ...(action ? { action } : {}),
  };
}
