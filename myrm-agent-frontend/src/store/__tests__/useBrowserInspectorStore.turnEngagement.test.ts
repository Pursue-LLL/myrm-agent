/**
 * Tests for browser inspector turn engagement lifecycle (per-chat ownership).
 */
import { beforeEach, describe, expect, it } from 'vitest';

import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';

describe('useBrowserInspectorStore turn engagement', () => {
  beforeEach(() => {
    useBrowserInspectorStore.getState().reset();
  });

  it('markTurnEngaged records the owning chat id', () => {
    useBrowserInspectorStore.getState().markTurnEngaged('c1');
    expect(useBrowserInspectorStore.getState().engagedChatId).toBe('c1');
  });

  it('markTurnEngaged ignores an empty chat id', () => {
    useBrowserInspectorStore.getState().markTurnEngaged('');
    expect(useBrowserInspectorStore.getState().engagedChatId).toBeNull();
  });

  it('releaseTurnEngagement is a no-op for a manually opened panel when an unrelated turn ends', () => {
    const state = useBrowserInspectorStore.getState();
    state.openPanel();
    state.updateViewData({
      screenshotBase64: 'x',
      mimeType: 'image/jpeg',
      refs: {},
      pageUrl: 'https://example.com',
      pageTitle: 'Example',
      viewportWidth: 1280,
      viewportHeight: 720,
      sourceChatId: 'c1',
      updatedAt: Date.now(),
    });

    // A panel the user opened manually must survive unrelated turns.
    useBrowserInspectorStore.getState().releaseTurnEngagement('other-chat');

    expect(useBrowserInspectorStore.getState().engagedChatId).toBeNull();
    expect(useBrowserInspectorStore.getState().isOpen).toBe(true);
    expect(useBrowserInspectorStore.getState().viewData).not.toBeNull();
  });

  it('releaseTurnEngagement is a no-op for a different chat (parallel panes)', () => {
    useBrowserInspectorStore.getState().markTurnEngaged('c1');
    useBrowserInspectorStore.getState().setBrowserActive(true);
    useBrowserInspectorStore.getState().openPanel();

    // Pane c2's turn ends: it must not tear down pane c1's engaged panel.
    useBrowserInspectorStore.getState().releaseTurnEngagement('c2');

    const state = useBrowserInspectorStore.getState();
    expect(state.engagedChatId).toBe('c1');
    expect(state.isBrowserActive).toBe(true);
    expect(state.isOpen).toBe(true);
  });

  it('releaseTurnEngagement fully clears state after the owning chat ends', () => {
    useBrowserInspectorStore.getState().markTurnEngaged('c1');
    useBrowserInspectorStore.getState().setBrowserActive(true);
    useBrowserInspectorStore.getState().openPanel();
    useBrowserInspectorStore.getState().setInstructionText('click go');
    useBrowserInspectorStore.getState().updateViewData({
      screenshotBase64: 'x',
      mimeType: 'image/jpeg',
      refs: {},
      pageUrl: 'https://example.com',
      pageTitle: 'Example',
      viewportWidth: 1280,
      viewportHeight: 720,
      sourceChatId: 'c1',
      updatedAt: Date.now(),
    });

    useBrowserInspectorStore.getState().releaseTurnEngagement('c1');

    const state = useBrowserInspectorStore.getState();
    expect(state.engagedChatId).toBeNull();
    expect(state.isBrowserActive).toBe(false);
    expect(state.isOpen).toBe(false);
    expect(state.viewData).toBeNull();
    expect(state.selectedElement).toBeNull();
    expect(state.instructionText).toBe('');
  });

  it('releaseTurnEngagement keeps another pane\'s manually opened panel when the ending turn produced no view', () => {
    const store = useBrowserInspectorStore.getState();
    // Pane A's turn engaged browser events but its launch failed before any view
    // update; viewData still belongs to pane B's manually opened panel.
    store.markTurnEngaged('a');
    store.setBrowserActive(true);
    store.openPanel();
    store.updateViewData({
      screenshotBase64: 'x',
      mimeType: 'image/jpeg',
      refs: {},
      pageUrl: 'https://example.com',
      pageTitle: 'Example',
      viewportWidth: 1280,
      viewportHeight: 720,
      sourceChatId: 'b',
      updatedAt: Date.now(),
    });
    store.setInstructionText('draft');

    store.releaseTurnEngagement('a');

    const state = useBrowserInspectorStore.getState();
    expect(state.engagedChatId).toBeNull();
    expect(state.isOpen).toBe(true);
    expect(state.viewData).not.toBeNull();
    expect(state.isBrowserActive).toBe(true);
    // The panel stays open, so the user's instruction draft must not be dropped.
    expect(state.instructionText).toBe('draft');
  });

  it('releaseTurnEngagement clears state when the owning turn engaged but produced no view', () => {
    const store = useBrowserInspectorStore.getState();
    store.markTurnEngaged('c1');
    store.setBrowserActive(true);
    store.openPanel();
    store.setInstructionText('typing');

    store.releaseTurnEngagement('c1');

    const state = useBrowserInspectorStore.getState();
    expect(state.engagedChatId).toBeNull();
    expect(state.isBrowserActive).toBe(false);
    expect(state.isOpen).toBe(false);
    expect(state.viewData).toBeNull();
    expect(state.instructionText).toBe('');
  });

  it('releaseTurnEngagement reclaims viewData when an overwritten turn ends last (ghost control fix)', () => {
    const store = useBrowserInspectorStore.getState();
    // Pane A's turn drives the browser and emits a view.
    store.markTurnEngaged('a');
    store.setBrowserActive(true);
    store.openPanel();
    store.updateViewData({
      screenshotBase64: 'x',
      mimeType: 'image/jpeg',
      refs: {},
      pageUrl: 'https://example.com',
      pageTitle: 'Example',
      viewportWidth: 1280,
      viewportHeight: 720,
      sourceChatId: 'a',
      updatedAt: Date.now(),
    });

    // Pane B's turn starts and overwrites the single engagement slot.
    store.markTurnEngaged('b');

    // B ends first: ownership is returned, A's view stays visible.
    store.releaseTurnEngagement('b');
    expect(useBrowserInspectorStore.getState().engagedChatId).toBeNull();
    expect(useBrowserInspectorStore.getState().viewData).not.toBeNull();

    // A ends last: even though the engagement slot is gone, A's view must be reclaimed.
    store.releaseTurnEngagement('a');
    const state = useBrowserInspectorStore.getState();
    expect(state.viewData).toBeNull();
    expect(state.isBrowserActive).toBe(false);
    expect(state.isOpen).toBe(false);
  });

  it('reset clears engagedChatId', () => {
    useBrowserInspectorStore.getState().markTurnEngaged('c1');
    useBrowserInspectorStore.getState().reset();
    expect(useBrowserInspectorStore.getState().engagedChatId).toBeNull();
  });
});
