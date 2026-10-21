/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Source } from '@/store/chat/types';

const recordEvidenceSurfaceMock = vi.fn();

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/message-input/useSmoothStream', () => ({
  useSmoothStream: () => ({
    addChunk: vi.fn(),
    displayedContent: '',
    flush: vi.fn(),
    reset: vi.fn(),
  }),
}));

vi.mock('@/store/useConfigStore', () => ({
  default: () => false,
}));

vi.mock('@/components/features/markdown-render-tools/LinkPopover', () => ({
  default: ({ label }: { label: string }) => <span>{label}</span>,
}));

vi.mock('@/components/features/markdown-render-tools/CodeBlock', () => ({
  default: ({ value }: { value: string }) => <pre>{value}</pre>,
}));

vi.mock('@/components/features/markdown-render-tools/InlineHtmlWidget', () => ({
  default: ({ value }: { value: string }) => <div>{value}</div>,
}));

vi.mock('@/components/features/markdown-render-tools/MermaidChart', () => ({
  default: ({ chart }: { chart: string }) => <div>{chart}</div>,
}));

vi.mock('@/components/features/markdown-render-tools/MarkdownImage', () => ({
  default: () => <img alt="mock" />,
}));

vi.mock('@/components/features/markdown-render-tools/InlineDiffViewer', () => ({
  default: ({ diff }: { diff: string }) => <pre>{diff}</pre>,
}));

vi.mock('@/components/features/artifacts/VaultArtifactCard', () => ({
  default: ({ id }: { id: string }) => <div>{id}</div>,
}));

vi.mock('@/components/features/message-box/SourceChunkDrawer', () => ({
  default: ({
    open,
    level,
    surface,
    snapshotStatus,
    resourceUri,
    claimStatus,
    claimText,
  }: {
    open: boolean;
    level?: string;
    surface?: string;
    snapshotStatus?: string;
    resourceUri?: string;
    claimStatus?: string;
    claimText?: string;
  }) => (
    <div
      data-testid="kb-drawer"
      data-open={open ? '1' : '0'}
      data-level={level ?? ''}
      data-surface={surface ?? ''}
      data-snapshot-status={snapshotStatus ?? ''}
      data-resource-uri={resourceUri ?? ''}
      data-claim-status={claimStatus ?? ''}
      data-claim-text={claimText ?? ''}
    />
  ),
}));

vi.mock('@/services/wiki/evidenceMetrics', () => ({
  recordEvidenceSurface: (...args: unknown[]) => recordEvidenceSurfaceMock(...args),
}));

import MarkdownContent from '../MarkdownContent';

describe('MarkdownContent wiki evidence flow', () => {
  beforeEach(() => {
    recordEvidenceSurfaceMock.mockReset();
  });

  it('records evidence surface and opens kb drawer with level', () => {
    const sources: Source[] = [
      {
        index: 1,
        type: 'knowledge',
        kb_name: 'LLM-Wiki',
        filename: 'team-doc',
        section: 'Intro',
        snippet: 'Evidence snippet',
        level: 'L1',
      },
    ];

    render(
      <MarkdownContent
        content="Answer with evidence <citation data-source-index='0' data-num='1' />"
        sources={sources}
        messageId="msg-1"
      />,
    );

    expect(recordEvidenceSurfaceMock).toHaveBeenCalledWith('chat', 1, 'chat:msg-1');

    const citation = screen.getByText('1');
    fireEvent.click(citation);

    const drawer = screen.getByTestId('kb-drawer');
    expect(drawer.getAttribute('data-open')).toBe('1');
    expect(drawer.getAttribute('data-level')).toBe('L1');
    expect(drawer.getAttribute('data-surface')).toBe('chat');
  });

  it('opens kb drawer with snapshot status for stale claim evidence', () => {
    const sources: Source[] = [
      {
        index: 1,
        type: 'knowledge',
        kb_name: 'LLM-Wiki',
        filename: 'budget',
        section: 'Claim',
        snippet: 'Budget fact',
        level: 'L2',
        snapshot_status: 'stale',
        resource_uri: 'raw/budget.md@sha256:deadbeef',
        source_key: 'kb:LLM-Wiki:/concepts/budget.md:claim:claim.budget:evidence:raw/source.md:1-3',
      },
    ];

    render(
      <MarkdownContent
        content="Answer with evidence <citation data-source-index='0' data-num='1' />"
        sources={sources}
        messageId="msg-stale"
      />,
    );

    fireEvent.click(screen.getByText('1'));

    const drawer = screen.getByTestId('kb-drawer');
    expect(drawer.getAttribute('data-open')).toBe('1');
    expect(drawer.getAttribute('data-snapshot-status')).toBe('stale');
    expect(drawer.getAttribute('data-resource-uri')).toBe('raw/budget.md@sha256:deadbeef');
  });

  it('opens kb drawer with claim_status for contested claim evidence', () => {
    const sources: Source[] = [
      {
        index: 1,
        type: 'knowledge',
        kb_name: 'LLM-Wiki',
        filename: 'budget',
        section: 'Claim',
        snippet: 'Disputed budget line',
        level: 'L2',
        claim_status: 'contested',
        snapshot_status: 'verified',
      },
    ];

    render(
      <MarkdownContent
        content="Answer with evidence <citation data-source-index='0' data-num='1' />"
        sources={sources}
        messageId="msg-contested"
      />,
    );

    fireEvent.click(screen.getByText('1'));

    const drawer = screen.getByTestId('kb-drawer');
    expect(drawer.getAttribute('data-open')).toBe('1');
    expect(drawer.getAttribute('data-claim-status')).toBe('contested');
  });

  it('opens kb drawer with claim_text when structured claim differs from excerpt', () => {
    const sources: Source[] = [
      {
        index: 1,
        type: 'knowledge',
        kb_name: 'LLM-Wiki',
        filename: 'budget',
        section: 'Claim',
        snippet: 'line two\nline three',
        claim_text: 'Budget fact',
        level: 'L2',
      },
    ];

    render(
      <MarkdownContent
        content="Answer with evidence <citation data-source-index='0' data-num='1' />"
        sources={sources}
        messageId="msg-claim-text"
      />,
    );

    fireEvent.click(screen.getByText('1'));

    const drawer = screen.getByTestId('kb-drawer');
    expect(drawer.getAttribute('data-open')).toBe('1');
    expect(drawer.getAttribute('data-claim-text')).toBe('Budget fact');
  });
});
