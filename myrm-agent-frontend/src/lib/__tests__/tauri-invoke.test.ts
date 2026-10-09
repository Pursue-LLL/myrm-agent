/**
 * [INPUT]: @/lib/tauri::invokeTauriCommand, tauriBackend
 * [OUTPUT]: Unit tests for the Tauri v2 command channel
 * [POS]: 守护命令调用经官方包的 v2 命令通道（v2 全局桥无顶层 invoke），并覆盖环境守卫与错误透传。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { invokeTauriCommand, tauriBackend } from '@/lib/tauri';

const coreInvoke = vi.hoisted(() => vi.fn<(command: string, args?: Record<string, unknown>) => Promise<unknown>>());

vi.mock('@tauri-apps/api/core', () => ({ invoke: coreInvoke }));

/** 复现 v2 `withGlobalTauri` 的真实形态：命令入口仅在 `core` 命名空间，顶层没有 `invoke`。 */
function installV2GlobalBridge(): void {
  Object.assign(window, { __TAURI__: { core: { invoke: vi.fn() }, event: { listen: vi.fn() } } });
}

describe('invokeTauriCommand', () => {
  beforeEach(() => {
    coreInvoke.mockReset();
  });

  afterEach(() => {
    Reflect.deleteProperty(window, '__TAURI__');
    vi.restoreAllMocks();
  });

  it('rejects outside the Tauri runtime without reaching the command channel', async () => {
    await expect(invokeTauriCommand('start_backend')).rejects.toThrow('Not running in Tauri environment');
    expect(coreInvoke).not.toHaveBeenCalled();
  });

  it('routes commands through the v2 core channel', async () => {
    installV2GlobalBridge();
    coreInvoke.mockResolvedValue('ok');

    await expect(invokeTauriCommand<string>('load_system_config', { reload: true })).resolves.toBe('ok');
    expect(coreInvoke).toHaveBeenCalledWith('load_system_config', { reload: true });
  });

  it('logs the failing command and rethrows the original error', async () => {
    installV2GlobalBridge();
    const failure = new Error('command not allowed');
    coreInvoke.mockRejectedValue(failure);
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

    await expect(invokeTauriCommand('save_system_config')).rejects.toBe(failure);
    expect(consoleError).toHaveBeenCalledWith('Failed to invoke Tauri command: save_system_config', failure);
  });
});

describe('tauriBackend', () => {
  beforeEach(() => {
    coreInvoke.mockReset();
    installV2GlobalBridge();
  });

  afterEach(() => {
    Reflect.deleteProperty(window, '__TAURI__');
  });

  it.each([
    ['start', 'start_backend'],
    ['stop', 'stop_backend'],
    ['checkHealth', 'check_backend_health'],
  ] as const)('%s invokes the registered %s command', async (method, command) => {
    coreInvoke.mockResolvedValue('ok');

    await tauriBackend[method]();

    expect(coreInvoke).toHaveBeenCalledWith(command, undefined);
  });
});
