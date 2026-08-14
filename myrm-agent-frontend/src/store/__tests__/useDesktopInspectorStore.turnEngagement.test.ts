/**
 * Tests for desktop inspector turn engagement lifecycle (per-chat ownership).
 */
import { beforeEach, describe, expect, it } from 'vitest';

import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';

describe('useDesktopInspectorStore turn engagement', () => {
  beforeEach(() => {
    useDesktopInspectorStore.getState().reset();
  });

  it('markTurnEngaged records the owning chat id', () => {
    useDesktopInspectorStore.getState().markTurnEngaged('c1');
    expect(useDesktopInspectorStore.getState().engagedChatId).toBe('c1');
  });

  it('markTurnEngaged ignores an empty chat id', () => {
    useDesktopInspectorStore.getState().markTurnEngaged('');
    expect(useDesktopInspectorStore.getState().engagedChatId).toBeNull();
  });

  it('releaseTurnEngagement is a no-op for a manually opened panel when an unrelated turn ends', () => {
    const state = useDesktopInspectorStore.getState();
    state.openPanel();
    state.updateViewData({
      screenshotBase64: 'x',
      mimeType: 'image/png',
      refs: {},
      appName: 'Calculator',
      windowTitle: '',
      scope: 'app',
      needsPermission: false,
      viewportWidth: 100,
      viewportHeight: 100,
      sourceChatId: 'c1',
      updatedAt: Date.now(),
    });

    // A panel the user opened manually must survive unrelated turns.
    useDesktopInspectorStore.getState().releaseTurnEngagement('other-chat');

    expect(useDesktopInspectorStore.getState().engagedChatId).toBeNull();
    expect(useDesktopInspectorStore.getState().isOpen).toBe(true);
    expect(useDesktopInspectorStore.getState().viewData).not.toBeNull();
  });

  it('releaseTurnEngagement is a no-op for a different chat (parallel panes)', () => {
    useDesktopInspectorStore.getState().markTurnEngaged('c1');
    useDesktopInspectorStore.getState().setDesktopActive(true);
    useDesktopInspectorStore.getState().openPanel();

    // Pane c2's turn ends: it must not tear down pane c1's engaged panel.
    useDesktopInspectorStore.getState().releaseTurnEngagement('c2');

    const state = useDesktopInspectorStore.getState();
    expect(state.engagedChatId).toBe('c1');
    expect(state.isDesktopActive).toBe(true);
    expect(state.isOpen).toBe(true);
  });

  it('releaseTurnEngagement fully clears state after the owning chat ends', () => {
    useDesktopInspectorStore.getState().markTurnEngaged('c1');
    useDesktopInspectorStore.getState().setDesktopActive(true);
    useDesktopInspectorStore.getState().openPanel();
    useDesktopInspectorStore.getState().setInstructionText('click ok');
    useDesktopInspectorStore.getState().updateViewData({
      screenshotBase64: 'x',
      mimeType: 'image/png',
      refs: {},
      appName: 'Calculator',
      windowTitle: '',
      scope: 'app',
      needsPermission: false,
      viewportWidth: 100,
      viewportHeight: 100,
      sourceChatId: 'c1',
      updatedAt: Date.now(),
    });

    useDesktopInspectorStore.getState().releaseTurnEngagement('c1');

    const state = useDesktopInspectorStore.getState();
    expect(state.engagedChatId).toBeNull();
    expect(state.isDesktopActive).toBe(false);
    expect(state.isOpen).toBe(false);
    expect(state.viewData).toBeNull();
    expect(state.selectedElement).toBeNull();
    expect(state.instructionText).toBe('');
  });

  it('releaseTurnEngagement keeps another pane\'s manually opened panel when the ending turn produced no view', () => {
    const store = useDesktopInspectorStore.getState();
    // Pane A's turn engaged desktop events but its launch failed before any view
    // update; viewData still belongs to pane B's manually opened panel.
    store.markTurnEngaged('a');
    store.setDesktopActive(true);
    store.openPanel();
    store.updateViewData({
      screenshotBase64: 'x',
      mimeType: 'image/png',
      refs: {},
      appName: 'Calculator',
      windowTitle: '',
      scope: 'app',
      needsPermission: false,
      viewportWidth: 100,
      viewportHeight: 100,
      sourceChatId: 'b',
      updatedAt: Date.now(),
    });
    store.setInstructionText('draft');

    store.releaseTurnEngagement('a');

    const state = useDesktopInspectorStore.getState();
    expect(state.engagedChatId).toBeNull();
    expect(state.isOpen).toBe(true);
    expect(state.viewData).not.toBeNull();
    expect(state.isDesktopActive).toBe(true);
    // The panel stays open, so the user's instruction draft must not be dropped.
    expect(state.instructionText).toBe('draft');
  });

  it('releaseTurnEngagement clears state when the owning turn engaged but produced no view', () => {
    const store = useDesktopInspectorStore.getState();
    store.markTurnEngaged('c1');
    store.setDesktopActive(true);
    store.openPanel();
    store.setInstructionText('typing');

    store.releaseTurnEngagement('c1');

    const state = useDesktopInspectorStore.getState();
    expect(state.engagedChatId).toBeNull();
    expect(state.isDesktopActive).toBe(false);
    expect(state.isOpen).toBe(false);
    expect(state.viewData).toBeNull();
    expect(state.instructionText).toBe('');
  });

  it('releaseTurnEngagement reclaims viewData when an overwritten turn ends last (ghost control fix)', () => {
    const store = useDesktopInspectorStore.getState();
    // Pane A's turn drives the desktop and emits a view.
    store.markTurnEngaged('a');
    store.setDesktopActive(true);
    store.openPanel();
    store.updateViewData({
      screenshotBase64: 'x',
      mimeType: 'image/png',
      refs: {},
      appName: 'Calculator',
      windowTitle: '',
      scope: 'app',
      needsPermission: false,
      viewportWidth: 100,
      viewportHeight: 100,
      sourceChatId: 'a',
      updatedAt: Date.now(),
    });

    // Pane B's turn starts and overwrites the single engagement slot.
    store.markTurnEngaged('b');

    // B ends first: ownership is returned, A's view stays visible.
    store.releaseTurnEngagement('b');
    expect(useDesktopInspectorStore.getState().engagedChatId).toBeNull();
    expect(useDesktopInspectorStore.getState().viewData).not.toBeNull();

    // A ends last: even though the engagement slot is gone, A's view must be reclaimed.
    store.releaseTurnEngagement('a');
    const state = useDesktopInspectorStore.getState();
    expect(state.viewData).toBeNull();
    expect(state.isDesktopActive).toBe(false);
    expect(state.isOpen).toBe(false);
  });

  it('reset clears engagedChatId', () => {
    useDesktopInspectorStore.getState().markTurnEngaged('c1');
    useDesktopInspectorStore.getState().reset();
    expect(useDesktopInspectorStore.getState().engagedChatId).toBeNull();
  });
});
