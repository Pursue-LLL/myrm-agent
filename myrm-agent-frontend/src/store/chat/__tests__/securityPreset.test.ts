import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  disarmYoloForPreset,
  disableYolo,
  isYoloEnabled,
  normalizeSecurityPreset,
  resolvePresetWithYoloMutex,
} from '@/store/chat/securityPreset';

const mockGet = vi.hoisted(() => vi.fn());
const mockSet = vi.hoisted(() => vi.fn());

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({
    get: mockGet,
    set: mockSet,
    subscribe: vi.fn(),
  }),
}));

describe('normalizeSecurityPreset', () => {
  it('passes through all three valid presets', () => {
    expect(normalizeSecurityPreset('hitl')).toBe('hitl');
    expect(normalizeSecurityPreset('accept_edits')).toBe('accept_edits');
    expect(normalizeSecurityPreset('explore')).toBe('explore');
  });

  it('falls back to hitl for null/undefined/unknown values', () => {
    expect(normalizeSecurityPreset(null)).toBe('hitl');
    expect(normalizeSecurityPreset(undefined)).toBe('hitl');
    expect(normalizeSecurityPreset('auto' as never)).toBe('hitl');
  });
});

describe('disarmYoloForPreset', () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockSet.mockReset();
  });

  it('does nothing for hitl preset', () => {
    disarmYoloForPreset('hitl');
    expect(mockGet).not.toHaveBeenCalled();
    expect(mockSet).not.toHaveBeenCalled();
  });

  it('disarms YOLO when enabling accept_edits with YOLO active', () => {
    mockGet.mockReturnValue({
      yoloModeEnabled: true,
      yoloModeTimeout: 600,
      yoloModeEnabledAt: '2026-01-01T00:00:00Z',
    });
    disarmYoloForPreset('accept_edits');
    expect(mockSet).toHaveBeenCalledWith('securityConfig', {
      yoloModeEnabled: false,
      yoloModeTimeout: undefined,
      yoloModeEnabledAt: undefined,
    });
  });

  it('leaves config untouched when YOLO is already off', () => {
    mockGet.mockReturnValue({ yoloModeEnabled: false });
    disarmYoloForPreset('explore');
    expect(mockSet).not.toHaveBeenCalled();
  });

  it('tolerates missing securityConfig', () => {
    mockGet.mockReturnValue(undefined);
    disarmYoloForPreset('explore');
    expect(mockSet).not.toHaveBeenCalled();
  });
});

describe('isYoloEnabled', () => {
  beforeEach(() => {
    mockGet.mockReset();
  });

  it('returns true when yoloModeEnabled is true', () => {
    mockGet.mockReturnValue({ yoloModeEnabled: true });
    expect(isYoloEnabled()).toBe(true);
  });

  it('returns false when yoloModeEnabled is false or missing', () => {
    mockGet.mockReturnValue({ yoloModeEnabled: false });
    expect(isYoloEnabled()).toBe(false);

    mockGet.mockReturnValue({});
    expect(isYoloEnabled()).toBe(false);

    mockGet.mockReturnValue(undefined);
    expect(isYoloEnabled()).toBe(false);
  });
});

describe('disableYolo', () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockSet.mockReset();
  });

  it('clears YOLO fields when YOLO is active', () => {
    mockGet.mockReturnValue({
      yoloModeEnabled: true,
      yoloModeTimeout: 600,
      yoloModeEnabledAt: '2026-01-01T00:00:00Z',
    });
    disableYolo();
    expect(mockSet).toHaveBeenCalledWith('securityConfig', {
      yoloModeEnabled: false,
      yoloModeTimeout: undefined,
      yoloModeEnabledAt: undefined,
    });
  });

  it('leaves config untouched when YOLO is already off or config missing', () => {
    mockGet.mockReturnValue({ yoloModeEnabled: false });
    disableYolo();
    expect(mockSet).not.toHaveBeenCalled();

    mockGet.mockReturnValue(undefined);
    disableYolo();
    expect(mockSet).not.toHaveBeenCalled();
  });
});

describe('resolvePresetWithYoloMutex', () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockSet.mockReset();
  });

  it('returns null and keeps YOLO when clicking current preset with YOLO off', () => {
    mockGet.mockReturnValue({ yoloModeEnabled: false });
    expect(resolvePresetWithYoloMutex('hitl', 'hitl')).toBeNull();
    expect(mockSet).not.toHaveBeenCalled();
  });

  it('returns next preset when switching with YOLO off', () => {
    mockGet.mockReturnValue({ yoloModeEnabled: false });
    expect(resolvePresetWithYoloMutex('hitl', 'accept_edits')).toBe('accept_edits');
    expect(mockSet).not.toHaveBeenCalled();
  });

  it('disarms YOLO when clicking current hitl with YOLO active and keeps preset unchanged', () => {
    mockGet.mockReturnValue({ yoloModeEnabled: true });
    expect(resolvePresetWithYoloMutex('hitl', 'hitl')).toBeNull();
    expect(mockSet).toHaveBeenCalledWith('securityConfig', {
      yoloModeEnabled: false,
      yoloModeTimeout: undefined,
      yoloModeEnabledAt: undefined,
    });
  });

  it('disarms YOLO and returns next preset when switching with YOLO active', () => {
    mockGet.mockReturnValue({ yoloModeEnabled: true });
    expect(resolvePresetWithYoloMutex('hitl', 'accept_edits')).toBe('accept_edits');
    expect(mockSet).toHaveBeenCalled();
  });
});
