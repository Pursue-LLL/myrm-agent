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

  it('returns already-enabled toast when catalog was already enabled', () => {
    const response: SkillInstallToastResponse = {
      mounted: true,
      mount_already_present: true,
    };

    expect(resolveSkillInstallToastMessage(SKILL, response)).toEqual({
      titleKey: 'installedAlreadyEnabled',
      titleParams: { name: SKILL },
    });
  });

  it('returns destructive toast when catalog enable fails', () => {
    const response: SkillInstallToastResponse = {
      mounted: false,
      mount_error: 'Catalog enable rejected',
    };

    expect(resolveSkillInstallToastMessage(SKILL, response)).toEqual({
      titleKey: 'installedEnableFailed',
      titleParams: { name: SKILL },
      descriptionText: 'Catalog enable rejected',
      variant: 'destructive',
    });
  });

  it('returns plain installed toast when mount did not run', () => {
    const response: SkillInstallToastResponse = {};

    expect(resolveSkillInstallToastMessage(SKILL, response)).toEqual({
      titleKey: 'installed',
    });
  });
});
