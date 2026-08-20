/** Discover install toast resolver — maps install API fields to a single toast payload.

[INPUT]
- settings.skills.discover locale keys (POS: Install success/allowlist toast copy)

[OUTPUT]
- resolveSkillInstallToastMessage: Pure message keys/variant from API response
- formatSkillInstallToast: Localized title/description for toast()

[POS]
Discover install feedback helper. Keeps SkillDiscoverTab free of branching toast logic.
*/

export type SkillInstallToastResponse = {
  mounted?: boolean;
  mount_error?: string;
  mount_already_present?: boolean;
  allowlist_appended?: boolean;
  allowlist_append_error?: string;
};

export type SkillInstallToastMessage = {
  titleKey: string;
  titleParams?: { name: string };
  descriptionKey?: string;
  descriptionText?: string;
  variant?: 'destructive';
};

type TranslateFn = (key: string, params?: Record<string, string>) => string;

/** Resolve a single install toast from discovery install API fields. */
export function resolveSkillInstallToastMessage(
  skillName: string,
  response: SkillInstallToastResponse,
): SkillInstallToastMessage {
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
): { title: string; description?: string; variant?: 'destructive' } {
  const message = resolveSkillInstallToastMessage(skillName, response);

  return {
    title:
      message.titleKey === 'installed'
        ? `${t('installed')} ${skillName}`
        : t(message.titleKey, message.titleParams ?? { name: skillName }),
    description: message.descriptionText ?? (message.descriptionKey ? t(message.descriptionKey) : undefined),
    variant: message.variant,
  };
}
