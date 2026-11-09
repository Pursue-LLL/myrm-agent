/** @vitest-environment jsdom */

/**
 * [INPUT]
 * - ../ArtifactCard::ArtifactCard
 * - @/components/features/dashboard-workspace/useDashboardWorkspaceStore::useDashboardWorkspaceStore
 *
 * [OUTPUT]
 * - Tests: the pin button adds and removes the artifact in the persisted workspace store.
 *
 * [POS]
 * The card used to write a store nothing rendered. This pins the button to the store the mounted
 * `DashboardWorkspaceDrawer` reads, so "pinned" means a widget actually shows up in the workspace.
 */

import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, expect, it, beforeEach, vi } from 'vitest';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn().mockResolvedValue({}),
  getApiUrl: () => 'http://localhost',
  getStorageUrl: (url: string) => url,
}));

// Effects in the card hydrate publications/preflight over fetch; answer them locally so the run
// never reaches the network.
beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }),
  );
});

vi.mock('@/store/useChatStore', () => {
  const state = { chatId: 'chat-1', workspaceDir: null, agentConfig: null };
  const hook = (selector: (s: typeof state) => unknown) => selector(state);
  return { default: Object.assign(hook, { getState: () => state }) };
});

import ArtifactCard from '../ArtifactCard';
import { useDashboardWorkspaceStore } from '@/components/features/dashboard-workspace/useDashboardWorkspaceStore';

// `svg` keeps the deploy-preflight effect from issuing a real network call; the pin button is type-agnostic.
const artifact = {
  id: 'art-1',
  type: 'svg',
  filename: 'report.svg',
  content: '<svg/>',
  size: 100,
} as never;

describe('ArtifactCard pin', () => {
  beforeEach(() => {
    act(() => {
      useDashboardWorkspaceStore.getState().clearAllWidgets();
      useDashboardWorkspaceStore.getState().closeDrawer();
    });
  });

  it('adds the artifact to the workspace store', () => {
    render(<ArtifactCard artifact={artifact} />);

    fireEvent.click(screen.getByTestId('artifact-pin-btn-art-1'));

    const widgets = useDashboardWorkspaceStore.getState().widgets;
    expect(widgets).toHaveLength(1);
    expect(widgets[0]).toMatchObject({
      id: 'art-1',
      title: 'report.svg',
      language: 'svg',
      content: '<svg/>',
      sourceChatId: 'chat-1',
    });
  });

  it('removes it again on a second click', () => {
    render(<ArtifactCard artifact={artifact} />);
    const button = screen.getByTestId('artifact-pin-btn-art-1');

    fireEvent.click(button);
    fireEvent.click(button);

    expect(useDashboardWorkspaceStore.getState().widgets).toHaveLength(0);
  });
});
