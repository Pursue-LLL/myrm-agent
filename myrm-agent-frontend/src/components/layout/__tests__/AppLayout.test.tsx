/**
 * The shell around every page.
 *
 * Real scenario: the app opens, the session is signed in and the slow start-up loads wait for an idle moment; on a
 * desktop window the page sits next to the navigation rail and the content sidebar, on a phone behind a drawer, on
 * the settings page and the paired-phone surface it takes the whole frame; notices (crash recovery, degraded
 * readiness) appear above the page and a dismissed readiness notice comes back the next time readiness degrades.
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import type { ComponentProps, ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type CrashRecoveryDialog from '@/components/features/app-shell/crash-recovery-dialog';
import type { ConfigReadinessDegradedBanner } from '@/components/features/app-shell/local-backend-unavailable-banner';
import { expectDefined, expectNonNull } from '@/test-utils/expectDefined';

import type ContentSidebar from '../ContentSidebar';
import type { MobileSidebarDrawer } from '../MobileSidebarDrawer';
import type NavBar from '../NavBar';
import type { useAppLayoutState } from '../useAppLayoutState';

type LayoutState = ReturnType<typeof useAppLayoutState>;

const kit = vi.hoisted(() => ({
  initAuth: vi.fn<() => void>(),
  loadFeatures: vi.fn<() => Promise<void>>(),
  loadProgression: vi.fn<() => Promise<void>>(),
  crash: { crashLoopActive: false, errorMessage: null as string | null, dismiss: vi.fn<() => void>() },
  layout: undefined as LayoutState | undefined,
  navBar: undefined as ComponentProps<typeof NavBar> | undefined,
  sidebar: undefined as ComponentProps<typeof ContentSidebar> | undefined,
  drawer: undefined as ComponentProps<typeof MobileSidebarDrawer> | undefined,
  crashDialog: undefined as ComponentProps<typeof CrashRecoveryDialog> | undefined,
  appHooks: {
    useTrayStatus: vi.fn<() => void>(),
    useTabBadge: vi.fn<() => void>(),
    useDesktopWakeRecovery: vi.fn<() => void>(),
    useConnectionsChangedReload: vi.fn<() => void>(),
    useVisibilityThrottling: vi.fn<() => void>(),
    useTrayEvents: vi.fn<() => void>(),
    useCurtainTexts: vi.fn<() => void>(),
    useGlobalShortcuts: vi.fn<() => void>(),
    useComputerUseEscapeAbort: vi.fn<() => void>(),
    useWuBalanceWatcher: vi.fn<() => void>(),
    useExtensionWebUiOriginSeed: vi.fn<() => void>(),
  },
}));

vi.mock('@/store/useAuthStore', () => ({ default: () => ({ initAuth: kit.initAuth }) }));
vi.mock('@/store/useFeatureGateStore', () => ({
  useFeatureGateStore: { getState: () => ({ loadFeatures: kit.loadFeatures }) },
}));
vi.mock('@/store/useProgressionStore', () => ({
  useProgressionStore: { getState: () => ({ load: kit.loadProgression }) },
}));
vi.mock('../useAppLayoutState', () => ({ NAVBAR_WIDTH: 60, useAppLayoutState: () => kit.layout }));
vi.mock('../NavBar', () => ({
  default: (props: ComponentProps<typeof NavBar>) => {
    kit.navBar = props;
    return <nav data-testid="navbar" />;
  },
}));
vi.mock('../ContentSidebar', () => ({
  default: (props: ComponentProps<typeof ContentSidebar>) => {
    kit.sidebar = props;
    return <aside data-testid="content-sidebar" />;
  },
}));
vi.mock('../MobileSidebarDrawer', () => ({
  MobileSidebarDrawer: (props: ComponentProps<typeof MobileSidebarDrawer>) => {
    kit.drawer = props;
    return <div data-testid="mobile-drawer" />;
  },
}));
vi.mock('@/hooks/tauri/useTrayStatus', () => ({ useTrayStatus: kit.appHooks.useTrayStatus }));
vi.mock('@/hooks/shell/useTabBadge', () => ({ useTabBadge: kit.appHooks.useTabBadge }));
vi.mock('@/hooks/tauri/useDesktopWakeRecovery', () => ({
  useDesktopWakeRecovery: kit.appHooks.useDesktopWakeRecovery,
}));
vi.mock('@/hooks/tauri/useConnectionsChangedReload', () => ({
  useConnectionsChangedReload: kit.appHooks.useConnectionsChangedReload,
}));
vi.mock('@/hooks/ui/useVisibilityThrottling', () => ({
  useVisibilityThrottling: kit.appHooks.useVisibilityThrottling,
}));
vi.mock('@/hooks/tauri/useTrayEvents', () => ({ useTrayEvents: kit.appHooks.useTrayEvents }));
vi.mock('@/hooks/tauri/useCurtainTexts', () => ({ useCurtainTexts: kit.appHooks.useCurtainTexts }));
vi.mock('@/hooks/shell/useGlobalShortcuts', () => ({ useGlobalShortcuts: kit.appHooks.useGlobalShortcuts }));
vi.mock('@/hooks/shell/useComputerUseEscapeAbort', () => ({
  useComputerUseEscapeAbort: kit.appHooks.useComputerUseEscapeAbort,
}));
vi.mock('@/hooks/billing/useWuBalanceWatcher', () => ({ useWuBalanceWatcher: kit.appHooks.useWuBalanceWatcher }));
vi.mock('@/hooks/extension/useExtensionWebUiOriginSeed', () => ({
  useExtensionWebUiOriginSeed: kit.appHooks.useExtensionWebUiOriginSeed,
}));
vi.mock('@/hooks/shell/useCrashLoopGuard', () => ({ useCrashLoopGuard: () => kit.crash }));
vi.mock('@/components/billing/BudgetExceededDialog', () => ({ default: () => <div data-testid="budget-dialog" /> }));
vi.mock('@/components/billing/UpgradeNudgeDialog', () => ({ default: () => <div data-testid="upgrade-dialog" /> }));
vi.mock('@/components/features/app-shell/crash-recovery-dialog', () => ({
  default: (props: ComponentProps<typeof CrashRecoveryDialog>) => {
    kit.crashDialog = props;
    return <div data-testid="crash-dialog" />;
  },
}));
vi.mock('@/components/features/app-shell/local-backend-unavailable-banner', () => ({
  default: () => <div data-testid="backend-banner" />,
  ConfigReadinessDegradedBanner: (props: ComponentProps<typeof ConfigReadinessDegradedBanner>) =>
    props.visible ? (
      <div data-testid="readiness-banner">
        <button type="button" onClick={props.onRetry}>
          retry
        </button>
        <button type="button" onClick={props.onDismiss}>
          dismiss
        </button>
      </div>
    ) : null,
}));
vi.mock('@/components/features/app-shell/cron-scheduler-health-banner', () => ({
  default: () => <div data-testid="cron-banner" />,
}));
vi.mock('@/components/features/app-shell/config-unreadable-banner', () => ({
  default: () => <div data-testid="config-banner" />,
}));
vi.mock('@/components/dev/E2ECompanionBridge', () => ({ default: () => <div data-testid="e2e-bridge" /> }));

import AppLayout from '../AppLayout';

function layoutState(overrides: Partial<LayoutState> = {}): LayoutState {
  return {
    pathname: '/',
    activeTab: 'chat',
    isSidebarCollapsed: false,
    isMobileSidebarOpen: false,
    setIsMobileSidebarOpen: vi.fn(),
    isNavButtonHidden: false,
    lastChatUrl: null,
    lastWorkUrl: null,
    lastProjectsUrl: null,
    sidebarWidth: 280,
    isSidebarDragging: false,
    handleSidebarResizeStart: vi.fn(),
    handleSidebarDoubleClick: vi.fn(),
    handleToggleSidebar: vi.fn(),
    handleTabChange: vi.fn(),
    isSettingsPage: false,
    isRemoteSurface: false,
    shouldShowContentSidebar: true,
    showMobileLayout: false,
    paddingLeft: '340px',
    ...overrides,
  };
}

function useLayout(overrides: Partial<LayoutState> = {}): LayoutState {
  kit.layout = layoutState(overrides);
  return kit.layout;
}

const page = (props: Partial<ComponentProps<typeof AppLayout>> = {}): ReactElement => (
  <AppLayout {...props}>
    <p>page content</p>
  </AppLayout>
);

const main = () => screen.getByTestId('app-layout');
const frame = (): Element => {
  const element = main().firstElementChild;
  expectNonNull(element, 'content frame');
  return element;
};
const drawer = (): ComponentProps<typeof MobileSidebarDrawer> => {
  expectDefined(kit.drawer, 'drawer');
  return kit.drawer;
};

beforeEach(() => {
  vi.resetAllMocks();
  kit.crash.crashLoopActive = false;
  kit.crash.errorMessage = null;
  kit.navBar = undefined;
  kit.sidebar = undefined;
  kit.drawer = undefined;
  kit.crashDialog = undefined;
  useLayout();
});

afterEach(() => {
  // The shell cancels its idle work when it unmounts, so it must unmount before the stubbed browser APIs go away.
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('AppLayout: start-up', () => {
  it('signs the session in once, then loads the feature gates and progression when the browser is idle', () => {
    let goIdle = (): void => undefined;
    vi.stubGlobal('requestIdleCallback', (callback: () => void) => {
      goIdle = callback;
      return 3;
    });
    vi.stubGlobal('cancelIdleCallback', vi.fn());

    render(page());
    expect(kit.initAuth).toHaveBeenCalledOnce();
    expect(kit.loadFeatures).not.toHaveBeenCalled();
    expect(kit.loadProgression).not.toHaveBeenCalled();

    act(() => goIdle());
    expect(kit.loadFeatures).toHaveBeenCalledOnce();
    expect(kit.loadProgression).toHaveBeenCalledOnce();
  });

  it('loads after a short timer where idle callbacks do not exist, but never for a shell that is already gone', () => {
    vi.useFakeTimers();
    // Stubbed after the fake clock, which would otherwise bring idle callbacks of its own.
    vi.stubGlobal('requestIdleCallback', undefined);

    render(page()).unmount();
    vi.advanceTimersByTime(10);
    expect(kit.loadFeatures).not.toHaveBeenCalled();

    render(page());
    vi.advanceTimersByTime(1);
    expect(kit.loadFeatures).toHaveBeenCalledOnce();
    expect(kit.loadProgression).toHaveBeenCalledOnce();
  });

  it('runs every app-wide background hook', () => {
    render(page());

    for (const [name, hook] of Object.entries(kit.appHooks)) {
      expect(hook, name).toHaveBeenCalled();
    }
  });

  it('puts the page between the banners and keeps the dialogs around it', () => {
    render(page());

    expect(within(main()).getByText('page content')).toBeInTheDocument();
    for (const id of ['backend-banner', 'cron-banner', 'config-banner']) {
      expect(within(main()).getByTestId(id), id).toBeInTheDocument();
    }
    for (const id of ['budget-dialog', 'upgrade-dialog', 'e2e-bridge', 'crash-dialog']) {
      expect(screen.getByTestId(id), id).toBeInTheDocument();
    }
  });
});

describe('AppLayout: desktop window', () => {
  it('shows the rail and the content sidebar, handing them the layout state', () => {
    const layout = useLayout({
      pathname: '/c-9',
      activeTab: 'chat',
      lastChatUrl: '/c-9',
      lastWorkUrl: '/work/2',
      lastProjectsUrl: '/projects/3',
      sidebarWidth: 300,
      isSidebarDragging: true,
    });

    render(page());

    expect(screen.queryByTestId('mobile-drawer')).toBeNull();
    expect(screen.queryByRole('button', { name: 'showSidebar' })).toBeNull();
    expect(kit.navBar).toMatchObject({
      activeTab: 'chat',
      onTabChange: layout.handleTabChange,
      isSidebarCollapsed: false,
      onToggleSidebar: layout.handleToggleSidebar,
      isSettingsPage: false,
      hideSidebarToggle: false,
      lastChatUrl: '/c-9',
      lastWorkUrl: '/work/2',
      lastProjectsUrl: '/projects/3',
      currentPathname: '/c-9',
    });
    expect(screen.getByTestId('content-sidebar')).toBeInTheDocument();
    expect(kit.sidebar).toMatchObject({
      isCollapsed: false,
      onToggleCollapse: layout.handleToggleSidebar,
      navbarWidth: 60,
      width: 300,
      isDragging: true,
      onResizeStart: layout.handleSidebarResizeStart,
      onResizeDoubleClick: layout.handleSidebarDoubleClick,
    });
  });

  it.each<[string, Partial<LayoutState>, boolean]>([
    ['a page with a sidebar', {}, false],
    ['a page without one', { shouldShowContentSidebar: false }, true],
    ['a collapsed sidebar', { isSidebarCollapsed: true }, true],
  ])('tells the rail whether its sidebar toggle is useless on %s', (_name, overrides, hidden) => {
    useLayout(overrides);

    render(page());

    const collapsed = overrides.isSidebarCollapsed === true;
    expect(kit.navBar?.hideSidebarToggle).toBe(hidden);
    expect(kit.navBar?.isSidebarCollapsed).toBe(collapsed);
    expect(screen.queryByTestId('content-sidebar') !== null).toBe(overrides.shouldShowContentSidebar !== false);
    if (overrides.shouldShowContentSidebar !== false) {
      expect(kit.sidebar?.isCollapsed).toBe(collapsed);
    }
  });

  it('pads the page by the rail and the sidebar, and animates that only while the sidebar is not being dragged', () => {
    useLayout({ paddingLeft: '340px' });
    const idle = render(page());
    expect(main().style.paddingLeft).toBe('340px');
    expect(main()).toHaveClass('transition-all');
    idle.unmount();

    useLayout({ paddingLeft: '412px', isSidebarDragging: true });
    render(page());
    expect(main().style.paddingLeft).toBe('412px');
    expect(main()).not.toHaveClass('transition-all');
  });

  it.each<[string, Partial<LayoutState>, string, string]>([
    ['an ordinary page', {}, 'max-w-screen-lg mx-auto px-4 pt-4 overflow-visible', 'min-h-screen'],
    ['the settings page', { isSettingsPage: true }, 'h-full overflow-y-auto', 'h-screen overflow-hidden'],
    ['the paired-phone surface', { isRemoteSurface: true }, 'lg:max-w-screen-lg lg:mx-auto', 'min-h-screen'],
  ])('frames %s', (_name, overrides, frameClass, mainClass) => {
    useLayout(overrides);

    render(page());

    expect(frame()).toHaveClass(frameClass);
    expect(main()).toHaveClass(mainClass);
    expect(kit.navBar?.isSettingsPage).toBe(overrides.isSettingsPage === true);
    if (overrides.isSettingsPage || overrides.isRemoteSurface) {
      expect(frame()).not.toHaveClass('px-4');
    }
  });
});

describe('AppLayout: phone', () => {
  it('replaces the rail and the sidebar by a drawer and a floating button that opens it', () => {
    const layout = useLayout({
      showMobileLayout: true,
      isMobileSidebarOpen: true,
      activeTab: 'projects',
      lastChatUrl: '/c-9',
      lastWorkUrl: '/work/2',
      lastProjectsUrl: '/projects/3',
      pathname: '/projects',
    });

    render(page());

    expect(screen.queryByTestId('navbar')).toBeNull();
    expect(screen.queryByTestId('content-sidebar')).toBeNull();
    expect(kit.drawer).toMatchObject({
      isOpen: true,
      activeTab: 'projects',
      onTabChange: layout.handleTabChange,
      isSettingsPage: false,
      shouldShowContentSidebar: true,
      lastChatUrl: '/c-9',
      lastWorkUrl: '/work/2',
      lastProjectsUrl: '/projects/3',
      currentPathname: '/projects',
    });

    fireEvent.click(screen.getByRole('button', { name: 'showSidebar' }));
    expect(layout.setIsMobileSidebarOpen).toHaveBeenLastCalledWith(true);

    act(() => drawer().onClose());
    expect(layout.setIsMobileSidebarOpen).toHaveBeenLastCalledWith(false);
  });

  it.each<[string, Partial<LayoutState>]>([
    ['the settings page', { isSettingsPage: true }],
    ['the paired-phone surface', { isRemoteSurface: true }],
  ])('has no floating button on %s, which bring their own navigation', (_name, overrides) => {
    useLayout({ showMobileLayout: true, ...overrides });

    render(page());

    expect(screen.queryByRole('button', { name: 'showSidebar' })).toBeNull();
    expect(screen.getByTestId('mobile-drawer')).toBeInTheDocument();
    expect(kit.drawer?.isSettingsPage).toBe(overrides.isSettingsPage === true);
  });

  it('slides the floating button away while it is hidden', () => {
    useLayout({ showMobileLayout: true, isNavButtonHidden: true });

    render(page());

    expect(screen.getByRole('button', { name: 'showSidebar' })).toHaveClass(
      'opacity-0',
      '-translate-y-full',
      'pointer-events-none',
    );
  });

  it('leaves no padding on the page', () => {
    useLayout({ showMobileLayout: true, paddingLeft: '0px' });

    render(page());

    expect(main().style.paddingLeft).toBe('0px');
  });
});

describe('AppLayout: notices', () => {
  it('lets the crash recovery dialog show the crash loop and dismiss it', () => {
    kit.crash.crashLoopActive = true;
    kit.crash.errorMessage = 'Renderer crashed';

    render(page());

    expect(kit.crashDialog).toMatchObject({
      visible: true,
      errorMessage: 'Renderer crashed',
      onDismiss: kit.crash.dismiss,
    });
  });

  it('keeps the crash recovery dialog away without a crash loop', () => {
    render(page());

    expect(kit.crashDialog).toMatchObject({ visible: false, errorMessage: null });
  });

  it('shows the degraded-readiness notice until it is dismissed, and again the next time readiness degrades', () => {
    const retry = vi.fn();
    const view = render(page({ configReadinessDegraded: true, onRetryConfigReadiness: retry }));
    expect(screen.getByTestId('readiness-banner')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    expect(retry).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole('button', { name: 'dismiss' }));
    expect(screen.queryByTestId('readiness-banner')).toBeNull();

    view.rerender(page({ configReadinessDegraded: true, onRetryConfigReadiness: retry }));
    expect(screen.queryByTestId('readiness-banner')).toBeNull();

    view.rerender(page({ configReadinessDegraded: false, onRetryConfigReadiness: retry }));
    expect(screen.queryByTestId('readiness-banner')).toBeNull();

    view.rerender(page({ configReadinessDegraded: true, onRetryConfigReadiness: retry }));
    expect(screen.getByTestId('readiness-banner')).toBeInTheDocument();
  });

  it('shows no readiness notice while readiness is fine', () => {
    render(page());

    expect(screen.queryByTestId('readiness-banner')).toBeNull();
  });
});
