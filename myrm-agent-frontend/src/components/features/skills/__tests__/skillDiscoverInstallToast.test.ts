import { describe, expect, it } from 'vitest';

import {
  resolveSkillInstallToastMessage,
  type SkillInstallToastResponse,
} from '../skillDiscoverInstallToast';

const SKILL = 'Demo Skill';

describe('resolveSkillInstallToastMessage', () => {
  it('returns a single destructive toast when allowlist append fails', () => {
    const response: SkillInstallToastResponse = {
      mounted: true,
      allowlist_append_error: 'Failed to update agent skill allowlist after install',
    };

    expect(resolveSkillInstallToastMessage(SKILL, response)).toEqual({
      titleKey: 'installedAllowlistAppendFailed',
      titleParams: { name: SKILL },
      descriptionKey: 'installedAllowlistAppendFailedDesc',
      variant: 'destructive',
    });
  });

  it('returns success with allowlist appended description', () => {
    const response: SkillInstallToastResponse = {
      mounted: true,
      allowlist_appended: true,
    };

    expect(resolveSkillInstallToastMessage(SKILL, response)).toEqual({
      titleKey: 'installedAndEnabled',
      titleParams: { name: SKILL },
      descriptionKey: 'installedAllowlistAppendedDesc',
    });
  });

  it('returns plain enabled toast when mount succeeds without allowlist changes', () => {
    const response: SkillInstallToastResponse = {
      mounted: true,
    };

    expect(resolveSkillInstallToastMessage(SKILL, response)).toEqual({
      titleKey: 'installedAndEnabled',
      titleParams: { name: SKILL },
    });
  });
});
