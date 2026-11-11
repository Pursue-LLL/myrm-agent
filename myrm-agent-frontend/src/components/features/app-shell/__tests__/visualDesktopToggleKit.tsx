/**
 * [INPUT]
 * - vitest::vi (POS: 模块替身登记)
 * - ../VisualDesktopToggle (POS: 被测组件)
 *
 * [OUTPUT]
 * - mocks: 替身句柄：沙箱读取、控制面请求、提示、部署模式、套餐权益、接管动作，以及组件模块求值时登记的懒加载入口
 * - prepareToggleKit / releaseToggleKit: 每个用例前的复位、之后的交还控制
 * - openPanel: 渲染并点开浮动入口
 * - resumeCalls: 已发出的「交还控制」请求
 * - vncResponse: 沙箱 VNC 地址响应的样例构造器
 *
 * [POS]
 * VisualDesktopToggle 行为测试的共享底座。必须先于 ../VisualDesktopToggle 导入：vi.mock 在本模块求值时登记。
 * 接管与用户控制用真实 store；网络、懒加载的桌面视图、提示、部署模式、套餐权益与接管动作换成替身。
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useUserControlStore from '@/store/useUserControlStore';
import { VisualDesktopToggle } from '../VisualDesktopToggle';

const mocks = vi.hoisted(() => ({
  fetchUserSandbox: vi.fn(),
  fetchSandboxVncUrl: vi.fn(),
  fetchWithTimeout: vi.fn(),
  toastError: vi.fn(),
  // Stable identity like next-intl's: a new `t` per render would re-trigger the component's load effect.
  t: (key: string) => key,
  sandbox: true,
  entitlements: { canUseVnc: true, isLoading: false },
  takeoverActions: { handleTakeoverComplete: vi.fn(), handleTakeoverSkip: vi.fn() },
  /** Each `dynamic()` call made while the component module loaded: its loader and its options. */
  lazyViews: [] as Array<{ load: () => Promise<{ default: unknown }>; options: unknown }>,
}));
export { mocks };

vi.mock('next-intl', () => ({
  useTranslations: () => mocks.t,
}));

vi.mock('next/dynamic', () => ({
  default: (load: () => Promise<{ default: unknown }>, options: unknown) => {
    mocks.lazyViews.push({ load, options });
    return (props: { wsUrl: string; viewOnly?: boolean }) => (
      <div data-testid="visual-desktop" data-ws-url={props.wsUrl} data-view-only={String(Boolean(props.viewOnly))} />
    );
  },
}));

vi.mock('../VisualDesktop', () => ({ VisualDesktop: () => null }));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: (...args: unknown[]) => mocks.fetchWithTimeout(...args),
}));

vi.mock('sonner', () => ({
  toast: { error: (...args: unknown[]) => mocks.toastError(...args) },
}));

vi.mock('@/lib/deploy-mode', () => ({ isSandbox: () => mocks.sandbox }));

vi.mock('@/hooks/billing/useFeatureEntitlements', () => ({
  useFeatureEntitlements: () => mocks.entitlements,
}));

vi.mock('@/hooks/approval/useBrowserTakeoverActions', () => ({
  useBrowserTakeoverActions: () => mocks.takeoverActions,
}));

vi.mock('@/lib/cp-sandbox', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/cp-sandbox')>()),
  fetchUserSandbox: mocks.fetchUserSandbox,
  fetchSandboxVncUrl: mocks.fetchSandboxVncUrl,
}));

export const vncResponse = (url = 'wss://vnc.example/sb-1') => ({ vnc_url: url, token: 'tok', sandbox_id: 'sb-1' });

/** A signed-in sandbox user on a plan with VNC, with an active sandbox and no takeover pending. */
export function prepareToggleKit() {
  vi.resetAllMocks();
  mocks.sandbox = true;
  mocks.entitlements = { canUseVnc: true, isLoading: false };
  mocks.fetchUserSandbox.mockResolvedValue({ id: 'sb-1', user_id: 'u-1', status: 'active', vnc_url: null });
  mocks.fetchWithTimeout.mockResolvedValue({
    ok: true,
    json: async () => ({ state: 'user_takeover', learned: false }),
  });
  useBrowserTakeoverStore.getState().completeTakeover();
}

export async function releaseToggleKit() {
  mocks.fetchWithTimeout.mockResolvedValue({ ok: true, json: async () => ({ learned: false }) });
  await useUserControlStore.getState().release();
  useBrowserTakeoverStore.getState().completeTakeover();
}

export function openPanel() {
  render(<VisualDesktopToggle />);
  fireEvent.click(screen.getByRole('button', { name: 'toggleTitle' }));
}

export const resumeCalls = () => mocks.fetchWithTimeout.mock.calls.filter(([url]) => url === '/webui/vnc/resume');
