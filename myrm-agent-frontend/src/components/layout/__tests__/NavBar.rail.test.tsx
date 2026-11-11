/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../NavBar (POS: 左侧导航栏：主标签、项目徽标、底部工具与设置入口)
 *
 * [OUTPUT]
 * Vitest: 三个主标签的选中态与目标地址、点击后的回调与移动端收起侧栏、项目徽标的求和与 99+ 封顶、
 * 展开侧栏按钮的出现条件、远程网关与设置入口、桌面端与移动端的定位、桌面端留白、服务端不渲染。
 *
 * [POS]
 * 路由、徽标、部署模式与桌面端留白由 navBarKit 提供替身；文案是真实英文。账号菜单见 NavBar.account.test.tsx。
 */
import { fireEvent, screen, within } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { kit, renderNavBar, resetNavBarKit } from './navBarKit';
import NavBar from '../NavBar';
import { TooltipProvider } from '@/components/primitives/tooltip';

const TABS = [
  { id: 'chat', name: 'Chat', defaultHref: '/' },
  { id: 'work', name: 'Work', defaultHref: '/work' },
  { id: 'projects', name: 'Projects', defaultHref: '/projects' },
] as const;

const tab = (name: (typeof TABS)[number]['name']) => screen.getByRole('link', { name });
const tabHrefs = () => TABS.map(({ name }) => tab(name).getAttribute('href'));
const badgeOn = (name: (typeof TABS)[number]['name']) => within(tab(name)).queryByText(/^\d+\+?$/);
const expandButtons = () => screen.queryAllByRole('button', { name: 'Expand Menu' });

describe('NavBar rail', () => {
  beforeEach(resetNavBarKit);
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('the primary tabs', () => {
    it.each(TABS)('lights only the $name tab when it is the active one', ({ id, name }) => {
      renderNavBar({ activeTab: id });

      for (const candidate of TABS) {
        const lit = candidate.name === name;
        expect(tab(candidate.name).getAttribute('aria-current')).toBe(lit ? 'page' : null);
      }
    });

    it('does not light the Chat tab on a settings page, because Settings is the destination there', () => {
      renderNavBar({ activeTab: 'chat', currentPathname: '/settings/models' });

      expect(tab('Chat')).not.toHaveAttribute('aria-current');
    });

    it.each(TABS)('sends the $name tab to $defaultHref until a page was visited in it', ({ name, defaultHref }) => {
      renderNavBar();

      expect(tab(name)).toHaveAttribute('href', defaultHref);
    });

    it('sends each tab back to the last page visited in it', () => {
      renderNavBar({ lastChatUrl: '/chat/abc', lastWorkUrl: '/work/w1', lastProjectsUrl: '/projects/p2' });

      expect(tabHrefs()).toEqual(['/chat/abc', '/work/w1', '/projects/p2']);
    });

    it('treats an empty or missing last page as never visited', () => {
      renderNavBar({ lastChatUrl: '', lastWorkUrl: null, lastProjectsUrl: undefined });

      expect(tabHrefs()).toEqual(['/', '/work', '/projects']);
    });

    it.each([
      { isMobile: true, closed: 1 },
      { isMobile: false, closed: 0 },
    ])('reports the chosen tab and closes the sidebar $closed time(s) when isMobile is $isMobile', (scenario) => {
      const { onTabChange, onCloseMobileSidebar } = renderNavBar({ isMobile: scenario.isMobile });

      fireEvent.click(tab('Work'));

      expect(onTabChange).toHaveBeenCalledExactlyOnceWith('work');
      expect(onCloseMobileSidebar).toHaveBeenCalledTimes(scenario.closed);
    });

    it('still switches tabs on a mobile rail that has no way to close the sidebar', () => {
      const { onTabChange } = renderNavBar({ isMobile: true, onCloseMobileSidebar: undefined });

      fireEvent.click(tab('Projects'));

      expect(onTabChange).toHaveBeenCalledExactlyOnceWith('projects');
    });
  });

  describe('the Projects badge', () => {
    it.each([
      { cronFailures: 3, pendingApprovals: 4, shown: '7' },
      { cronFailures: 0, pendingApprovals: 12, shown: '12' },
      { cronFailures: 60, pendingApprovals: 39, shown: '99' },
      { cronFailures: 60, pendingApprovals: 40, shown: '99+' },
    ])(
      'reads $shown for $cronFailures failed jobs and $pendingApprovals pending approvals',
      ({ cronFailures, pendingApprovals, shown }) => {
        Object.assign(kit.badges, { cronFailures, pendingApprovals });
        renderNavBar();

        expect(badgeOn('Projects')).toHaveTextContent(shown);
      },
    );

    it('is absent when nothing needs attention', () => {
      renderNavBar();

      expect(badgeOn('Projects')).toBeNull();
    });

    it('stays on the Projects tab only', () => {
      Object.assign(kit.badges, { cronFailures: 5, pendingApprovals: 5 });
      renderNavBar();

      expect(badgeOn('Chat')).toBeNull();
      expect(badgeOn('Work')).toBeNull();
    });
  });

  describe('the expand-sidebar button', () => {
    it.each([
      { when: 'the sidebar is collapsed', props: { isSidebarCollapsed: true }, shown: 1 },
      { when: 'the sidebar is expanded', props: { isSidebarCollapsed: false }, shown: 0 },
      { when: 'collapsed on a settings page', props: { isSidebarCollapsed: true, isSettingsPage: true }, shown: 0 },
      {
        when: 'collapsed but hidden by the page',
        props: { isSidebarCollapsed: true, hideSidebarToggle: true },
        shown: 0,
      },
    ])('shows $shown of it when $when', ({ props, shown }) => {
      renderNavBar(props);

      expect(expandButtons()).toHaveLength(shown);
    });

    it('asks to expand the sidebar when pressed', () => {
      const { onToggleSidebar } = renderNavBar({ isSidebarCollapsed: true });

      fireEvent.click(screen.getByRole('button', { name: 'Expand Menu' }));

      expect(onToggleSidebar).toHaveBeenCalledOnce();
    });
  });

  describe('the footer links', () => {
    it('opens settings and closes the mobile sidebar', () => {
      const { onCloseMobileSidebar } = renderNavBar({ isMobile: true });
      const settings = screen.getByRole('link', { name: 'Settings' });

      fireEvent.click(settings);

      expect(settings).toHaveAttribute('href', '/settings');
      expect(onCloseMobileSidebar).toHaveBeenCalledOnce();
    });

    it.each([
      { isSettingsPage: true, current: 'page' },
      { isSettingsPage: false, current: null },
    ])('marks the Settings link as current = $current when isSettingsPage is $isSettingsPage', (scenario) => {
      renderNavBar({ isSettingsPage: scenario.isSettingsPage });

      expect(screen.getByRole('link', { name: 'Settings' }).getAttribute('aria-current')).toBe(scenario.current);
    });

    it('has no remote server indicator without a remote gateway', () => {
      renderNavBar();

      expect(screen.queryByRole('link', { name: 'Connected to Remote Server' })).toBeNull();
    });

    it('points at the system settings while a remote gateway is active, closing the mobile sidebar when followed', () => {
      kit.deploy.remoteGateway = true;
      const { onCloseMobileSidebar } = renderNavBar({ isMobile: true });
      const indicator = screen.getByRole('link', { name: 'Connected to Remote Server' });

      fireEvent.click(indicator);

      expect(indicator).toHaveAttribute('href', '/settings/system');
      expect(onCloseMobileSidebar).toHaveBeenCalledOnce();
    });
  });

  describe('layout', () => {
    it('is pinned to the screen edge on desktop', () => {
      renderNavBar({ isMobile: false });

      expect(screen.getByRole('navigation')).toHaveClass('fixed', 'inset-y-0', 'left-0');
    });

    it('flows with its parent on mobile, so it moves together with the sidebar', () => {
      renderNavBar({ isMobile: true });

      const rail = screen.getByRole('navigation');
      expect(rail).toHaveClass('relative', 'h-full');
      expect(rail).not.toHaveClass('fixed');
    });

    it.each([
      { immersiveMac: true, isMobile: false, padded: true },
      { immersiveMac: true, isMobile: true, padded: false },
      { immersiveMac: false, isMobile: false, padded: false },
    ])(
      'leaves room for the window buttons: $padded when immersiveMac=$immersiveMac and isMobile=$isMobile',
      ({ immersiveMac, isMobile, padded }) => {
        kit.immersiveMac = immersiveMac;
        renderNavBar({ isMobile });

        const header = screen.getByRole('navigation').firstElementChild;
        expect(header?.classList.contains('pt-9')).toBe(padded);
      },
    );

    it('draws nothing on the server, because the rail depends on client-only state', () => {
      const html = renderToString(
        <TooltipProvider>
          <NavBar
            activeTab="chat"
            onTabChange={vi.fn()}
            isSidebarCollapsed={false}
            onToggleSidebar={vi.fn()}
            currentPathname="/"
          />
        </TooltipProvider>,
      );

      expect(html).toBe('');
    });
  });
});
