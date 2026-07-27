/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Source } from '@/store/chat/types';

const recordEvidenceSurfaceMock = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/hooks/useSmoothStream', () => ({
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
  }: {
    open: boolean;
    level?: string;
    surface?: string;
  }) => (
    <div data-testid="kb-drawer" data-open={open ? '1' : '0'} data-level={level ?? ''} data-surface={surface ?? ''} />
  ),
}));

vi.mock('@/services/wikiEvidenceMetrics', () => ({
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
});
