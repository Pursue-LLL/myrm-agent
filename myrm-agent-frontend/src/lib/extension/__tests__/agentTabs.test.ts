/**
 * @vitest-environment node
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

type AgentTabs = typeof import('../../../../../myrm-agent-extension/src/background/agent_tabs.js');
type ExtensionState = typeof import('../../../../../myrm-agent-extension/src/background/state.js');

let adoptOpenedTab: AgentTabs['adoptOpenedTab'];
let state: ExtensionState['state'];
const persistedTabs = vi.fn();

beforeAll(async () => {
  // The extension's modules register browser listeners when loaded and persist the Agent's tabs through the browser.
  vi.stubGlobal('chrome', {
    windows: { onRemoved: { addListener: vi.fn() } },
    storage: { session: { set: persistedTabs } },
  });
  ({ adoptOpenedTab } = await import('../../../../../myrm-agent-extension/src/background/agent_tabs.js'));
  ({ state } = await import('../../../../../myrm-agent-extension/src/background/state.js'));
});

beforeEach(() => {
  state.authorizedDomains = ['intranet.example'];
  state.allowAllEligibleTabs = false;
  state.pausedTabIds = new Set();
  state.agentTabIds = new Set([1]);
  state.agentTabOpeners = new Map();
  persistedTabs.mockClear();
});

afterEach(() => {
  state.agentTabIds.clear();
});

describe('adoptOpenedTab: a tab an Agent tab opened', () => {
  it('becomes the Agent’s when it heads for an authorized site, remembering which tab opened it', () => {
    expect(adoptOpenedTab(2, 1, 'https://intranet.example/orders')).toBe(true);

    expect(state.agentTabIds.has(2)).toBe(true);
    expect(state.agentTabOpeners.get(2)).toBe(1);
    expect(persistedTabs).toHaveBeenCalledWith({ agentTabIds: [1, 2] });
  });

  it('becomes the Agent’s while it is still blank, since the Agent may take a blank page to the site it needs', () => {
    for (const [tabId, url] of [[2, ''], [3, 'about:blank']] as const) {
      expect(adoptOpenedTab(tabId, 1, url)).toBe(true);
    }
    expect([...state.agentTabIds]).toEqual([1, 2, 3]);
  });

  it('stays the user’s when it heads for a site the user did not authorize', () => {
    expect(adoptOpenedTab(2, 1, 'https://bank.example/account')).toBe(false);

    expect(state.agentTabIds.has(2)).toBe(false);
    expect(state.agentTabOpeners.has(2)).toBe(false);
    expect(persistedTabs).not.toHaveBeenCalled();
  });

  it('stays the user’s when the tab that opened it is not the Agent’s', () => {
    expect(adoptOpenedTab(2, 9, 'https://intranet.example/orders')).toBe(false);
    expect(state.agentTabIds.has(2)).toBe(false);
  });
});
