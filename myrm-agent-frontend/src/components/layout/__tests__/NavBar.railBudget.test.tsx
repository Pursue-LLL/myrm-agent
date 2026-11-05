/** @vitest-environment jsdom */
import React from 'react';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import NavBar from '../NavBar';
import { TooltipProvider } from '@/components/primitives/tooltip';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('next/link', () => ({
  default: ({ children, href, ...rest }: React.ComponentProps<'a'>) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('@/store/useAuthStore', () => ({
  default: () => ({ user: null, isLoading: false, logout: vi.fn(), loginMock: vi.fn() }),
}));
vi.mock('@/hooks/billing/useSubscription', () => ({ useSubscription: () => ({ isPro: false }) }));
vi.mock('@/hooks/shell/useNavBadges', () => ({
  useNavBadges: () => ({
    cronFailures: 0,
    pendingApprovals: 0,
    unreadNotifications: 0,
    activeGoals: 0,
    total: 0,
    extensionConnected: false,
  }),
}));
vi.mock('@/hooks/ui/useTrafficLightInsets', () => ({
  useTrafficLightInsets: () => ({ topInset: 0, leftInset: 0, isImmersiveMac: false }),
}));
vi.mock('@/lib/deploy-mode', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/deploy-mode')>()),
  isRemoteGatewayActive: () => false,
}));
vi.mock('@/lib/utils/componentPreloader', () => ({ preloadMonacoEditor: vi.fn() }));
// The bell and the task panel own their data; the rail only decides that each is one control.
vi.mock('@/components/features/notifications/NotificationBell', () => ({
  default: () => <button type="button" aria-label="NotificationBell" />,
}));
vi.mock('@/components/features/background-tasks/BackgroundTasksPanel', () => ({
  default: ({ trigger }: { trigger: React.ReactNode }) => <>{trigger}</>,
}));
vi.mock('@/components/features/extension-slots', () => ({ ExtensionSlot: () => null }));

async function railControlNames(isSidebarCollapsed: boolean): Promise<string[]> {
  render(
    <TooltipProvider>
      <NavBar
        activeTab="chat"
        onTabChange={vi.fn()}
        isSidebarCollapsed={isSidebarCollapsed}
        onToggleSidebar={vi.fn()}
        currentPathname="/"
      />
    </TooltipProvider>,
  );
  const rail = await screen.findByRole('navigation');
  return Array.from(rail.querySelectorAll<HTMLElement>('a[href], button')).map(
    (control) => control.getAttribute('aria-label') ?? control.textContent ?? '',
  );
}

describe('sidebar rail budget', () => {
  beforeAll(() => {
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
  });

  afterAll(() => {
    vi.unstubAllGlobals();
  });

  it('keeps eight always-on controls; a new page goes into the More menu, not onto the rail', async () => {
    const names = await railControlNames(false);

    expect(names, 'Add destinations to useNavMoreSections instead of adding a rail icon').toEqual([
      '访客',
      '聊天',
      '工作',
      '项目',
      '更多',
      '后台任务',
      'NotificationBell',
      '设置',
    ]);
  });

  it('adds only the expand button when the content sidebar is collapsed', async () => {
    const names = await railControlNames(true);

    expect(names).toHaveLength(9);
    expect(names).toContain('展开菜单');
  });
});
