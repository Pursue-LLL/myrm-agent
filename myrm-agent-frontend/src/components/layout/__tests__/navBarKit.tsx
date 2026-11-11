/**
 * [INPUT]
 * - vitest::vi (POS: 模块替身登记)
 * - ../NavBar (POS: 被测组件)
 *
 * [OUTPUT]
 * - kit: 替身句柄：路由、登录与退出动作、订阅、导航徽标、桌面端留白、部署模式
 * - resetNavBarKit: 恢复为未登录的本地模式，并给 Radix 弹层补上 ResizeObserver
 * - setAccount: 改写真实登录 store 里的用户与加载状态（订阅它的组件会照常重渲染）
 * - renderNavBar: 在 TooltipProvider 里渲染导航栏，返回三个回调的 spy
 * - signedIn: 登录用户的样例
 *
 * [POS]
 * NavBar 行为测试的共享底座。必须先于 ../NavBar 导入：vi.mock 在本模块求值时登记。
 * 登录 store 是真实的，只把登录与退出动作换成 spy；通知铃、后台任务面板与扩展槽自己管数据，换成最小替身；
 * 文案取真实英文，登录重定向路径走真实实现。
 */
import { act, cleanup, render } from '@testing-library/react';
import type { ComponentProps, ReactNode } from 'react';
import { vi } from 'vitest';
import { TooltipProvider } from '@/components/primitives/tooltip';
import useAuthStore from '@/store/useAuthStore';
import NavBar from '../NavBar';

interface AccountUser {
  id: string;
  email: string;
  display_name?: string;
  avatar_url?: string;
}

const kit = vi.hoisted(() => ({
  router: { push: vi.fn<(href: string) => void>() },
  auth: { logout: vi.fn<() => Promise<void>>(), loginMock: vi.fn<() => void>() },
  subscription: { isPro: false },
  badges: { cronFailures: 0, pendingApprovals: 0, extensionConnected: false },
  immersiveMac: false,
  deploy: { local: true, remoteGateway: false },
}));
export { kit };

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('next/navigation', () => ({ useRouter: () => kit.router }));
// Like the real Link, a click is handled in-app instead of loading another document.
vi.mock('next/link', () => ({
  default: ({ children, href, onClick, ...rest }: ComponentProps<'a'>) => (
    <a
      href={href}
      onClick={(event) => {
        onClick?.(event);
        event.preventDefault();
      }}
      {...rest}
    >
      {children}
    </a>
  ),
}));
vi.mock('@/hooks/billing/useSubscription', () => ({ useSubscription: () => kit.subscription }));
vi.mock('@/hooks/shell/useNavBadges', () => ({ useNavBadges: () => kit.badges }));
vi.mock('@/hooks/ui/useTrafficLightInsets', () => ({
  useTrafficLightInsets: () => ({ topInset: 0, leftInset: 0, isImmersiveMac: kit.immersiveMac }),
}));
vi.mock('@/lib/deploy-mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/deploy-mode')>()),
  isLocalMode: () => kit.deploy.local,
  isRemoteGatewayActive: () => kit.deploy.remoteGateway,
}));
vi.mock('@/lib/utils/componentPreloader', () => ({ preloadMonacoEditor: vi.fn() }));
vi.mock('@/components/features/notifications/NotificationBell', () => ({
  default: () => <button type="button" aria-label="Notifications" />,
}));
vi.mock('@/components/features/background-tasks/BackgroundTasksPanel', () => ({
  default: ({ trigger }: { trigger: ReactNode }) => <>{trigger}</>,
}));
vi.mock('@/components/features/extension-slots', () => ({ ExtensionSlot: () => null }));

export const signedIn: AccountUser = { id: 'u1', email: 'ada@example.com', display_name: 'Ada Lovelace' };

export function setAccount(account: { user?: AccountUser | null; isLoading?: boolean }): void {
  act(() => useAuthStore.setState(account));
}

export function resetNavBarKit(): void {
  cleanup();
  vi.clearAllMocks();
  act(() =>
    useAuthStore.setState({ user: null, isLoading: false, logout: kit.auth.logout, loginMock: kit.auth.loginMock }),
  );
  Object.assign(kit.subscription, { isPro: false });
  Object.assign(kit.badges, { cronFailures: 0, pendingApprovals: 0, extensionConnected: false });
  kit.immersiveMac = false;
  Object.assign(kit.deploy, { local: true, remoteGateway: false });
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
}

export function renderNavBar(props: Partial<ComponentProps<typeof NavBar>> = {}) {
  const spies = {
    onTabChange: vi.fn<(tab: ComponentProps<typeof NavBar>['activeTab']) => void>(),
    onToggleSidebar: vi.fn<() => void>(),
    onCloseMobileSidebar: vi.fn<() => void>(),
  };
  const tree = (extra: Partial<ComponentProps<typeof NavBar>> = {}) => (
    <TooltipProvider>
      <NavBar activeTab="chat" isSidebarCollapsed={false} currentPathname="/chat/c1" {...spies} {...props} {...extra} />
    </TooltipProvider>
  );
  const view = render(tree());
  return {
    ...view,
    ...spies,
    rerenderWith: (extra: Partial<ComponentProps<typeof NavBar>>) => view.rerender(tree(extra)),
  };
}
