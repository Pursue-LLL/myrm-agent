import { describe, it, expect, beforeEach } from 'vitest';
import { useDashboardWorkspaceStore } from '../useDashboardWorkspaceStore';

describe('useDashboardWorkspaceStore', () => {
  beforeEach(() => {
    useDashboardWorkspaceStore.getState().clearAllWidgets();
    useDashboardWorkspaceStore.getState().closeDrawer();
    useDashboardWorkspaceStore.getState().setSearchQuery('');
    useDashboardWorkspaceStore.getState().setActiveTagFilter(null);
  });

  it('pins a new widget with default fallback properties', () => {
    const store = useDashboardWorkspaceStore.getState();
    store.pinWidget({
      id: 'w-1',
      title: 'Metrics Panel',
      language: 'html',
      content: '<div>Metrics</div>',
      sourceChatId: 'chat-100',
    });

    const state = useDashboardWorkspaceStore.getState();
    expect(state.widgets).toHaveLength(1);
    expect(state.widgets[0].id).toBe('w-1');
    expect(state.widgets[0].title).toBe('Metrics Panel');
    expect(state.widgets[0].colSpan).toBe('2');
    expect(state.widgets[0].autoRefreshInterval).toBe(0);
    expect(state.widgets[0].tags).toEqual(['html']);
    expect(state.isWidgetPinned('w-1')).toBe(true);
  });

  it('prevents duplicate pinning of the same widget ID', () => {
    const store = useDashboardWorkspaceStore.getState();
    store.pinWidget({
      id: 'w-1',
      title: 'Metrics Panel',
      language: 'html',
      content: '<div>Metrics</div>',
    });
    store.pinWidget({
      id: 'w-1',
      title: 'Duplicate Attempt',
      language: 'html',
      content: '<div>Different</div>',
    });

    const state = useDashboardWorkspaceStore.getState();
    expect(state.widgets).toHaveLength(1);
    expect(state.widgets[0].title).toBe('Metrics Panel');
  });

  it('unpins a widget properly', () => {
    const store = useDashboardWorkspaceStore.getState();
    store.pinWidget({
      id: 'w-1',
      title: 'Widget 1',
      language: 'svg',
      content: '<svg></svg>',
    });
    expect(useDashboardWorkspaceStore.getState().widgets).toHaveLength(1);

    store.unpinWidget('w-1');
    expect(useDashboardWorkspaceStore.getState().widgets).toHaveLength(0);
    expect(useDashboardWorkspaceStore.getState().isWidgetPinned('w-1')).toBe(false);
  });

  it('toggles pin state correctly', () => {
    const store = useDashboardWorkspaceStore.getState();
    const payload = {
      id: 'toggle-1',
      title: 'Toggle Item',
      language: 'html',
      content: '<p>Test</p>',
    };

    store.togglePinWidget(payload);
    expect(useDashboardWorkspaceStore.getState().isWidgetPinned('toggle-1')).toBe(true);

    store.togglePinWidget(payload);
    expect(useDashboardWorkspaceStore.getState().isWidgetPinned('toggle-1')).toBe(false);
  });

  it('updates widget layout colSpan and title safely', () => {
    const store = useDashboardWorkspaceStore.getState();
    store.pinWidget({
      id: 'w-span',
      title: 'Old Title',
      language: 'html',
      content: '<span>Span</span>',
    });

    store.updateWidgetColSpan('w-span', '3');
    expect(useDashboardWorkspaceStore.getState().widgets[0].colSpan).toBe('3');

    store.updateWidgetTitle('w-span', '  Updated Title  ');
    expect(useDashboardWorkspaceStore.getState().widgets[0].title).toBe('Updated Title');

    // Empty title protection
    store.updateWidgetTitle('w-span', '   ');
    expect(useDashboardWorkspaceStore.getState().widgets[0].title).toBe('Updated Title');
  });

  it('updates auto refresh interval, content, and refreshes timestamp', () => {
    const store = useDashboardWorkspaceStore.getState();
    store.pinWidget({
      id: 'w-refresh',
      title: 'Auto Refreshing Feed',
      language: 'html',
      content: '<div>Old Content</div>',
    });

    const originalTimestamp = useDashboardWorkspaceStore.getState().widgets[0].lastRefreshedAt;

    store.updateWidgetRefreshInterval('w-refresh', 30);
    expect(useDashboardWorkspaceStore.getState().widgets[0].autoRefreshInterval).toBe(30);

    store.updateWidgetContent('w-refresh', '<div>New Content</div>');
    expect(useDashboardWorkspaceStore.getState().widgets[0].content).toBe('<div>New Content</div>');

    store.refreshWidget('w-refresh');
    expect(useDashboardWorkspaceStore.getState().widgets[0].lastRefreshedAt).toBeGreaterThanOrEqual(
      originalTimestamp,
    );
  });

  it('controls drawer visibility toggles', () => {
    const store = useDashboardWorkspaceStore.getState();
    expect(store.isDrawerOpen).toBe(false);

    store.openDrawer();
    expect(useDashboardWorkspaceStore.getState().isDrawerOpen).toBe(true);

    store.toggleDrawer();
    expect(useDashboardWorkspaceStore.getState().isDrawerOpen).toBe(false);

    store.toggleDrawer();
    expect(useDashboardWorkspaceStore.getState().isDrawerOpen).toBe(true);

    store.closeDrawer();
    expect(useDashboardWorkspaceStore.getState().isDrawerOpen).toBe(false);
  });

  it('supports reordering widgets with bounds validation', () => {
    const store = useDashboardWorkspaceStore.getState();
    store.pinWidget({ id: '1', title: 'First', language: 'html', content: '1' });
    store.pinWidget({ id: '2', title: 'Second', language: 'html', content: '2' });
    store.pinWidget({ id: '3', title: 'Third', language: 'html', content: '3' });

    // Current order: 3, 2, 1 (pinned widgets prepend)
    expect(useDashboardWorkspaceStore.getState().widgets.map((w) => w.id)).toEqual(['3', '2', '1']);

    store.reorderWidgets(0, 2);
    expect(useDashboardWorkspaceStore.getState().widgets.map((w) => w.id)).toEqual(['2', '1', '3']);

    // Out of bounds no-op
    store.reorderWidgets(-1, 2);
    store.reorderWidgets(0, 99);
    store.reorderWidgets(1, 1);
    expect(useDashboardWorkspaceStore.getState().widgets.map((w) => w.id)).toEqual(['2', '1', '3']);
  });
});
