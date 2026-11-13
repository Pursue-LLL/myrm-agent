/** @vitest-environment jsdom */
import React from 'react';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NavMoreMenu } from '../NavMoreMenu';
import { TooltipProvider } from '@/components/primitives/tooltip';
import { useWorkbenchStore } from '@/store/useWorkbenchStore';
import useConfigStore from '@/store/useConfigStore';

const { preloadMonacoEditor } = vi.hoisted(() => ({ preloadMonacoEditor: vi.fn() }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));

// Like the real Link: the caller's onClick runs first, then the navigation takes over the default action.
vi.mock('next/link', () => ({
  default: ({ children, href, onClick, ...rest }: React.ComponentProps<'a'>) => (
    <a
      href={href}
      {...rest}
      onClick={(event) => {
        onClick?.(event);
        event.preventDefault();
      }}
    >
      {children}
    </a>
  ),
}));

vi.mock('@/lib/utils/componentPreloader', () => ({ preloadMonacoEditor }));

function renderMenu(props: Partial<React.ComponentProps<typeof NavMoreMenu>> = {}) {
  const onNavigate = vi.fn();
  render(
    <TooltipProvider>
      <NavMoreMenu currentPathname="/" extensionConnected={false} onNavigate={onNavigate} {...props} />
    </TooltipProvider>,
  );
  return { onNavigate, user: userEvent.setup() };
}

async function openMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByTestId('nav-more-trigger'));
  return screen.findByTestId('nav-more-menu');
}

const rowsOf = (menu: HTMLElement) => Array.from(menu.querySelectorAll('[role^="menuitem"]'));

describe('NavMoreMenu', () => {
  beforeAll(() => {
    // The tooltip arrow measures itself, and focus returns to the trigger when the menu closes, which reopens it.
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

  beforeEach(() => {
    preloadMonacoEditor.mockClear();
    useWorkbenchStore.setState({ isOpen: false });
    useConfigStore.setState({ enableEvalLab: false });
  });

  it('keeps the rail to one labelled button until it is opened', () => {
    renderMenu();

    expect(screen.getByTestId('nav-more-trigger')).toHaveAccessibleName('更多');
    expect(screen.queryByTestId('nav-more-menu')).toBeNull();
  });

  it('groups destinations and tools under their section titles, in reading order', async () => {
    const { user } = renderMenu();
    const menu = await openMenu(user);

    for (const title of ['检视', '扩展', '工具']) {
      expect(within(menu).getByText(title)).toBeDefined();
    }
    const order = [
      '活动',
      '系统诊断',
      '安全中心',
      '成长仪表盘',
      '批量目录',
      '研究工作台',
      '技能管理',
      'MCP',
      '浏览器扩展未连接',
      '工作台',
      '会话地图',
      '演示文稿',
      '工具选择',
      '小莫中枢',
    ];
    const rows = rowsOf(menu);
    expect(rows).toHaveLength(order.length);
    order.forEach((label, index) => expect(rows[index]).toHaveTextContent(label));
  });

  it('hides the eval lab until it is enabled', async () => {
    const { user } = renderMenu();

    expect(within(await openMenu(user)).queryByText('评测实验室')).toBeNull();
  });

  it('lists the eval lab last among the monitoring pages once it is enabled', async () => {
    useConfigStore.setState({ enableEvalLab: true });
    const { user } = renderMenu();
    const rows = rowsOf(await openMenu(user));

    expect(rows[4]).toHaveTextContent('评测实验室');
    expect(rows[4]).toHaveAttribute('href', '/eval-lab');
    expect(rows[5]).toHaveTextContent('批量目录');
  });

  it('renders destinations as real links that close the drawer and mark the current page', async () => {
    const { user, onNavigate } = renderMenu({ currentPathname: '/settings/mcp' });
    const menu = await openMenu(user);

    const mcp = within(menu).getByRole('menuitem', { name: 'MCP' });
    expect(mcp).toHaveAttribute('href', '/settings/mcp');
    expect(mcp).toHaveAttribute('aria-current', 'page');
    expect(within(menu).getByRole('menuitem', { name: '技能管理' })).not.toHaveAttribute('aria-current');

    await user.click(mcp);
    expect(onNavigate).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByTestId('nav-more-menu')).toBeNull());
  });

  it.each([
    ['/runs', true],
    ['/runs/abc', true],
    ['/research', true],
    ['/settings/extensionBridge', true],
    ['/health', true],
    ['/healthcheck', false],
    ['/settings/profile', false],
    ['/', false],
  ])('lights the entry for route %s: %s', (currentPathname, lit) => {
    renderMenu({ currentPathname });

    const trigger = screen.getByTestId('nav-more-trigger');
    if (lit) {
      expect(trigger).toHaveAttribute('aria-current', 'true');
    } else {
      expect(trigger).not.toHaveAttribute('aria-current');
    }
  });

  it('opens the research workbench from the extension section', async () => {
    const { user } = renderMenu({ currentPathname: '/research' });

    const research = within(await openMenu(user)).getByRole('menuitem', { name: '研究工作台' });

    expect(research).toHaveAttribute('href', '/research');
    expect(research).toHaveAttribute('aria-current', 'page');
  });

  it('shows the browser extension state on its own row', async () => {
    const { user } = renderMenu({ extensionConnected: true });
    const menu = await openMenu(user);

    expect(within(menu).getByRole('menuitem', { name: '浏览器扩展已连接' })).toHaveAttribute(
      'href',
      '/settings/extensionBridge',
    );
    expect(within(menu).queryByText('浏览器扩展未连接')).toBeNull();
  });

  it('warms the editor chunk only for the pages that need it', async () => {
    const { user } = renderMenu();
    const menu = await openMenu(user);

    await user.hover(within(menu).getByRole('menuitem', { name: '活动' }));
    expect(preloadMonacoEditor).not.toHaveBeenCalled();

    await user.hover(within(menu).getByRole('menuitem', { name: '技能管理' }));
    expect(preloadMonacoEditor).toHaveBeenCalledTimes(1);
  });

  it('toggles the docked workbench and marks it checked only while it is open', async () => {
    const { user } = renderMenu();
    let menu = await openMenu(user);

    const workbench = () => within(menu).getByRole('menuitemcheckbox', { name: /工作台/ });
    expect(workbench()).toHaveAttribute('aria-checked', 'false');
    // The other panels are modal and cover the menu, so they carry no checked state.
    for (const label of [/会话地图/, /演示文稿/, /工具选择/, /小莫中枢/]) {
      expect(within(menu).getByRole('menuitem', { name: label })).not.toHaveAttribute('aria-checked');
    }

    await user.click(workbench());
    expect(useWorkbenchStore.getState().isOpen).toBe(true);
    await waitFor(() => expect(screen.queryByTestId('nav-more-menu')).toBeNull());

    menu = await openMenu(user);
    expect(workbench()).toHaveAttribute('aria-checked', 'true');
  });

  it('leaves focus alone after a pointer pick, so no ring or tooltip is left on the entry', async () => {
    const { user } = renderMenu();
    const menu = await openMenu(user);

    await user.click(within(menu).getByRole('menuitem', { name: /会话地图/ }));
    await waitFor(() => expect(screen.queryByTestId('nav-more-menu')).toBeNull());

    expect(screen.getByTestId('nav-more-trigger')).not.toHaveFocus();
  });

  it('leaves focus alone after a click outside the menu', async () => {
    const { user } = renderMenu();
    await openMenu(user);

    fireEvent.pointerDown(document.body, { button: 0, pointerType: 'mouse' });

    await waitFor(() => expect(screen.queryByTestId('nav-more-menu')).toBeNull());
    expect(screen.getByTestId('nav-more-trigger')).not.toHaveFocus();
  });

  it.each([
    ['Escape', '{Escape}'],
    ['picking a row', '{ArrowDown}{Enter}'],
  ])('returns focus to the entry when the keyboard closes the menu by %s', async (_name, keys) => {
    const { user } = renderMenu();
    screen.getByTestId('nav-more-trigger').focus();
    await user.keyboard('{Enter}');
    await screen.findByTestId('nav-more-menu');

    await user.keyboard(keys);

    await waitFor(() => expect(screen.queryByTestId('nav-more-menu')).toBeNull());
    expect(screen.getByTestId('nav-more-trigger')).toHaveFocus();
  });

  it('lets the last input device decide: a click inside the menu does not stop Escape from restoring focus', async () => {
    const { user } = renderMenu();
    const menu = await openMenu(user);

    await user.click(within(menu).getByText('检视'));
    expect(screen.getByTestId('nav-more-menu')).toBeDefined();
    await user.keyboard('{Escape}');

    await waitFor(() => expect(screen.queryByTestId('nav-more-menu')).toBeNull());
    expect(screen.getByTestId('nav-more-trigger')).toHaveFocus();
  });

  it('starts every session from the keyboard default, whatever the previous pick was', async () => {
    const { user } = renderMenu();
    await user.click(within(await openMenu(user)).getByRole('menuitem', { name: /会话地图/ }));
    await waitFor(() => expect(screen.queryByTestId('nav-more-menu')).toBeNull());

    screen.getByTestId('nav-more-trigger').focus();
    await user.keyboard('{Enter}');
    await screen.findByTestId('nav-more-menu');
    // Escape arriving while focus is still outside the menu never passes through the menu's own key handler.
    fireEvent.keyDown(document.body, { key: 'Escape' });

    await waitFor(() => expect(screen.queryByTestId('nav-more-menu')).toBeNull());
    expect(screen.getByTestId('nav-more-trigger')).toHaveFocus();
  });

  it('dispatches the panel events for the remaining tools', async () => {
    const { user } = renderMenu();
    const cases = [
      [/会话地图/, 'myrm:open-session-map'],
      [/演示文稿/, 'myrm:open-presentation'],
      [/工具选择/, 'myrm:open-tool-picker'],
      [/小莫中枢/, 'myrm:open-system-assistant'],
    ] as const;
    const listeners = cases.map(([, name]) => ({ name, listener: vi.fn() }));
    listeners.forEach(({ name, listener }) => window.addEventListener(name, listener));

    try {
      for (const [index, [label]] of cases.entries()) {
        const menu = await openMenu(user);
        await user.click(within(menu).getByRole('menuitem', { name: label }));
        expect(listeners[index].listener).toHaveBeenCalledTimes(1);
        await waitFor(() => expect(screen.queryByTestId('nav-more-menu')).toBeNull());
      }
    } finally {
      listeners.forEach(({ name, listener }) => window.removeEventListener(name, listener));
    }
  });
});
