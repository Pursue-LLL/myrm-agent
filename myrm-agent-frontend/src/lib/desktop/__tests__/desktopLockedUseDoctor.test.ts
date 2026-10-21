import { describe, expect, it } from 'vitest';

import {
  findDesktopLockedUseReport,
  readLockedUseEnabledFromReport,
  resolveLockedUseDoctorBadgeKey,
  resolveLockedUseDoctorDetailKey,
  resolveLockedUseDoctorVisualTone,
  lockedUseDoctorNeedsSettingsLink,
} from '../desktopLockedUseDoctor';

describe('desktopLockedUseDoctor', () => {
  it('prefers server DesktopLockedUse report', () => {
    const report = findDesktopLockedUseReport({
      server: [{ component_name: 'DesktopLockedUse', status: 'warn', message: 'x' }],
      harness: [{ component_name: 'DesktopLockedUse', status: 'fail', message: 'y' }],
      repair_actions: [],
    });
    expect(report?.status).toBe('warn');
  });

  it('distinguishes bridge ready from away mode on', () => {
    const bridgeOnly = {
      component_name: 'DesktopLockedUse',
      status: 'pass' as const,
      code: 'OK_DESKTOP_LOCKED_USE_READY',
      message: 'ok',
      meta_data: { locked_use_enabled: false },
    };
    expect(readLockedUseEnabledFromReport(bridgeOnly)).toBe(false);
    expect(resolveLockedUseDoctorBadgeKey(bridgeOnly, false)).toBe('lockedUseDoctorBadgeBridgeReady');
    expect(resolveLockedUseDoctorVisualTone(bridgeOnly, false)).toBe('pass_bridge');
    expect(resolveLockedUseDoctorDetailKey(bridgeOnly)).toBe('lockedUseDoctorDetailAwayOff');

    const awayOn = { ...bridgeOnly, meta_data: { locked_use_enabled: true } };
    expect(resolveLockedUseDoctorBadgeKey(awayOn, false)).toBe('lockedUseDoctorBadgeAwayOn');
    expect(resolveLockedUseDoctorVisualTone(awayOn, false)).toBe('pass');
    expect(resolveLockedUseDoctorDetailKey(awayOn)).toBeNull();
  });

  it('maps fail codes to detail keys and settings link', () => {
    const fail = {
      component_name: 'DesktopLockedUse',
      status: 'fail' as const,
      code: 'ERR_DESKTOP_SHELL_UNAVAILABLE',
      message: 'internal',
    };
    expect(resolveLockedUseDoctorDetailKey(fail)).toBe('lockedUseDoctorDetailShellUnavailable');
    expect(lockedUseDoctorNeedsSettingsLink(fail)).toBe(true);
  });
});
