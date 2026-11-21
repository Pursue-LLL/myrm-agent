import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const kit = vi.hoisted(() => ({
  getConfig: vi.fn<(key: string) => Record<string, unknown> | undefined>(),
  setConfig: vi.fn<(key: string, value: Record<string, unknown>) => void>(),
  apiRequest: vi.fn<(path: string, init: { method: string; body: string }) => Promise<unknown>>(),
  showToast: vi.fn(),
  loadingToast: vi.fn(() => 'loading-toast'),
  dismissToast: vi.fn(),
}));

vi.mock('@/services/config', () => ({
  getConfigSyncManager: () => ({ get: kit.getConfig, set: kit.setConfig }),
}));
vi.mock('@/lib/api', () => ({ apiRequest: kit.apiRequest }));
vi.mock('@/services/i18nToastService', () => ({ showI18nToast: kit.showToast }));
vi.mock('sonner', () => ({ toast: { loading: kit.loadingToast, dismiss: kit.dismissToast } }));

import { executeFreezeSlashCommand, executeYoloSlashCommand } from '../securitySlashCommands';

const NOW_SECONDS = 1_767_225_600;
const DONE = { success: true, newInputValue: '' };

describe('executeYoloSlashCommand', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    vi.setSystemTime(NOW_SECONDS * 1000);
  });
  afterEach(() => vi.useRealTimers());

  /** A loaded security config; `retained` proves the command writes back the settings it does not own. */
  const loadConfig = (yoloModeEnabled: boolean) => {
    const config = { yoloModeEnabled, retained: 'kept' };
    kit.getConfig.mockReturnValue(config);
    return config;
  };

  it.each([
    { input: '/yolo', before: false, after: true },
    { input: '/yolo', before: true, after: false },
    { input: '/YOLO ON', before: false, after: true },
    { input: '/yolo on', before: true, after: true },
    { input: '/yolo off', before: true, after: false },
    { input: '/yolo off', before: false, after: false },
    { input: '/yolo not-an-argument', before: false, after: true },
  ])('$input with yolo mode $before leaves it $after', async ({ input, before, after }) => {
    const config = loadConfig(before);

    await expect(executeYoloSlashCommand(input)).resolves.toEqual(DONE);

    expect(kit.setConfig).toHaveBeenCalledWith('securityConfig', {
      ...config,
      yoloModeEnabled: after,
      yoloModeTimeout: undefined,
      yoloModeEnabledAt: after ? NOW_SECONDS : undefined,
    });
  });

  it.each([
    { input: '/yolo 45', seconds: 45 },
    { input: '/yolo 45s', seconds: 45 },
    { input: '/yolo 5m', seconds: 300 },
    { input: '/yolo on 2h', seconds: 7200 },
  ])('$input enables yolo mode for $seconds seconds', async ({ input, seconds }) => {
    const config = loadConfig(false);

    await executeYoloSlashCommand(input);

    expect(kit.setConfig).toHaveBeenCalledWith('securityConfig', {
      ...config,
      yoloModeEnabled: true,
      yoloModeTimeout: seconds,
      yoloModeEnabledAt: NOW_SECONDS,
    });
    expect(kit.showToast).toHaveBeenCalledWith(
      'commands.builtin.yoloEnabled',
      { timeout: ` (${seconds}s)` },
      { type: 'warning' },
    );
  });

  it('warns without a time limit when none is given, and confirms when it is switched off', async () => {
    loadConfig(false);
    await executeYoloSlashCommand('/yolo on');
    expect(kit.showToast).toHaveBeenLastCalledWith(
      'commands.builtin.yoloEnabled',
      { timeout: '' },
      { type: 'warning' },
    );

    loadConfig(true);
    await executeYoloSlashCommand('/yolo off');
    expect(kit.showToast).toHaveBeenLastCalledWith('commands.builtin.yoloDisabled', undefined, { type: 'success' });
  });

  it('changes nothing while the security config has not loaded', async () => {
    kit.getConfig.mockReturnValue(undefined);

    await expect(executeYoloSlashCommand('/yolo on')).resolves.toEqual({
      success: false,
      error: 'Security config not loaded yet',
    });

    expect(kit.setConfig).not.toHaveBeenCalled();
    expect(kit.showToast).not.toHaveBeenCalled();
  });
});

describe('executeFreezeSlashCommand', () => {
  const estopChanged = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    kit.apiRequest.mockResolvedValue({});
    window.addEventListener('estop-changed', estopChanged);
  });
  afterEach(() => window.removeEventListener('estop-changed', estopChanged));

  it('activates the emergency stop, says so and tells the rest of the app', async () => {
    await expect(executeFreezeSlashCommand('/freeze')).resolves.toEqual(DONE);

    expect(kit.apiRequest).toHaveBeenCalledWith('/security/estop', {
      method: 'POST',
      body: JSON.stringify({ action: 'activate', reason: 'User triggered /freeze' }),
    });
    expect(kit.showToast).toHaveBeenCalledWith('commands.builtin.freezeActivated', undefined, { type: 'warning' });
    expect(kit.dismissToast).toHaveBeenCalledWith('loading-toast');
    expect(estopChanged).toHaveBeenCalledOnce();
  });

  it.each(['/freeze off', '/freeze RESUME'])('%s lifts the emergency stop', async (input) => {
    await expect(executeFreezeSlashCommand(input)).resolves.toEqual(DONE);

    expect(kit.apiRequest).toHaveBeenCalledWith('/security/estop', {
      method: 'POST',
      body: JSON.stringify({ action: 'resume' }),
    });
    expect(kit.showToast).toHaveBeenCalledWith('commands.builtin.freezeResumed', undefined, { type: 'success' });
    expect(estopChanged).toHaveBeenCalledOnce();
  });

  it('reports the failure and does not announce a change that did not happen', async () => {
    kit.apiRequest.mockRejectedValue(new Error('server unreachable'));

    await expect(executeFreezeSlashCommand('/freeze')).resolves.toEqual({
      success: false,
      error: 'server unreachable',
    });

    expect(kit.showToast).toHaveBeenCalledWith('commands.builtin.freezeFailed', undefined, { type: 'error' });
    expect(kit.dismissToast).toHaveBeenCalledWith('loading-toast');
    expect(estopChanged).not.toHaveBeenCalled();
  });

  it('falls back to a generic message when the failure carries none', async () => {
    kit.apiRequest.mockRejectedValue('boom');

    await expect(executeFreezeSlashCommand('/freeze')).resolves.toEqual({ success: false, error: 'Unknown error' });
  });
});
