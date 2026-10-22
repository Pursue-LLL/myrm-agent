import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useWidgetBridgeStore } from '../useWidgetBridgeStore';
import { HostContextBridge } from '../HostContextBridge';
import type { HostContextSnapshot, HostBridgeMessage } from '../widgetTypes';

describe('useWidgetBridgeStore & HostContextBridge', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useWidgetBridgeStore.getState().resetWidget();
    useWidgetBridgeStore.getState().setDisplayMode('floating_bubble');
    useWidgetBridgeStore.getState().setGeneratorModalOpen(false);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('initializes with default state', () => {
    const state = useWidgetBridgeStore.getState();
    expect(state.displayMode).toBe('floating_bubble');
    expect(state.isWidgetOpen).toBe(false);
    expect(state.isGeneratorModalOpen).toBe(false);
    expect(state.latestSnapshot).toBeNull();
    expect(state.allowedOrigins).toEqual(['*']);
    expect(state.messageHistory).toEqual([]);
  });

  it('updates displayMode and modal visibility', () => {
    useWidgetBridgeStore.getState().setDisplayMode('slideout_drawer');
    expect(useWidgetBridgeStore.getState().displayMode).toBe('slideout_drawer');

    useWidgetBridgeStore.getState().setWidgetOpen(true);
    expect(useWidgetBridgeStore.getState().isWidgetOpen).toBe(true);

    useWidgetBridgeStore.getState().setGeneratorModalOpen(true);
    expect(useWidgetBridgeStore.getState().isGeneratorModalOpen).toBe(true);
  });

  it('manages snapshot and message history', () => {
    const snapshot: HostContextSnapshot = {
      origin: 'https://admin.example.com',
      currentUrl: 'https://admin.example.com/dashboard',
      pageTitle: 'Admin Dashboard',
      selectedText: 'Order #1234',
    };

    useWidgetBridgeStore.getState().setLatestSnapshot(snapshot);
    expect(useWidgetBridgeStore.getState().latestSnapshot?.origin).toBe('https://admin.example.com');

    const msg: HostBridgeMessage = {
      action: 'sync_context',
      origin: 'https://admin.example.com',
    };
    useWidgetBridgeStore.getState().appendMessage(msg);
    expect(useWidgetBridgeStore.getState().messageHistory.length).toBe(1);
    expect(useWidgetBridgeStore.getState().messageHistory[0].action).toBe('sync_context');
  });

  it('generates embed snippet via API or fallback', async () => {
    const snippet = await useWidgetBridgeStore.getState().generateSnippet('chat_100', {
      mode: 'floating_bubble',
      theme: 'dark',
      allowedOrigin: 'https://partner.com',
      baseUrl: 'https://agent.myrm.io',
    });

    expect(snippet).toContain('data-chat-id="chat_100"');
    expect(snippet).toContain('data-mode="floating_bubble"');
    expect(snippet).toContain('data-theme="dark"');
  });

  it('validates origins correctly in HostContextBridge', () => {
    // Wildcard
    expect(HostContextBridge.isOriginAllowed('https://random.com', ['*'])).toBe(true);

    // Exact match
    const restricted = ['https://corp.internal', '*.sub.domain.com'];
    expect(HostContextBridge.isOriginAllowed('https://corp.internal', restricted)).toBe(true);
    expect(HostContextBridge.isOriginAllowed('https://other.com', restricted)).toBe(false);

    // Subdomain wildcard
    expect(HostContextBridge.isOriginAllowed('https://app.sub.domain.com', restricted)).toBe(true);
    expect(HostContextBridge.isOriginAllowed('https://evil.domain.com', restricted)).toBe(false);

    // Empty origin
    expect(HostContextBridge.isOriginAllowed('', restricted)).toBe(false);
  });
});
