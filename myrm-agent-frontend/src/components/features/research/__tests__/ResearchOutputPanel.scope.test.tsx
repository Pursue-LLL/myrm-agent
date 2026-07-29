/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const ingestArtifactMock = vi.fn();

const mockArtifact = {
  id: 'artifact-research-1',
  filename: 'market-report.md',
  type: 'document' as const,
  content_type: 'text/markdown',
  size: 2048,
  preview_url: '/preview/artifact-research-1',
  download_url: '/download/artifact-research-1',
};

const mockActiveTab = {
  artifact: mockArtifact,
  content: '# Market report',
  contentLoading: false,
  error: null,
  isGenerating: false,
  displayMode: 'preview' as const,
  viewingVersionIndex: -1,
  openedAt: Date.now(),
  lastAccessedAt: Date.now(),
};

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/lib/api', () => ({
  getStorageUrl: (url: string) => url,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign(
    (selector: (state: { agentConfig: { agentId?: string } | null }) => unknown) =>
      selector({ agentConfig: { agentId: 'research-agent' } }),
    {
      getState: () => ({ agentConfig: { agentId: 'research-agent' } }),
    },
  ),
}));

vi.mock('@/services/wikiService', () => ({
  wikiService: {
    ingestArtifact: (...args: unknown[]) => ingestArtifactMock(...args),
  },
}));

vi.mock('@/store/useArtifactPortalStore', () => ({
  useActiveTab: () => mockActiveTab,
  useArtifactContent: () => mockActiveTab.content,
  useArtifactLoading: () => false,
  useIsGenerating: () => false,
  useDisplayMode: () => mockActiveTab.displayMode,
  useOpenTabs: () => ({ tabs: [mockActiveTab] }),
}));

vi.mock('../../artifacts/ArtifactRenderer', () => ({
  default: () => <div data-testid="artifact-renderer" />,
}));

vi.mock('../../artifacts/portal/PortalTabs', () => ({
  default: () => <div data-testid="portal-tabs" />,
}));

import ResearchOutputPanel from '../ResearchOutputPanel';

describe('ResearchOutputPanel agent scope', () => {
  beforeEach(() => {
    ingestArtifactMock.mockReset();
    ingestArtifactMock.mockResolvedValue({ success: true, message: 'ok' });
  });

  it('ingests artifact into the active chat agent wiki scope', async () => {
    render(<ResearchOutputPanel />);

    fireEvent.click(screen.getByRole('button', { name: 'saveToWiki' }));

    await waitFor(() => {
      expect(ingestArtifactMock).toHaveBeenCalledWith('artifact-research-1', 'research-agent');
    });
  });
});
