/** @vitest-environment jsdom */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
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
  default: () => <div data-testid="kb-drawer" />,
}));

vi.mock('@/services/wikiEvidenceMetrics', () => ({
  recordEvidenceSurface: vi.fn(),
}));

vi.mock('../DeliverableReferenceLink', () => ({
  default: ({ label }: { label: string }) => <button type="button">{label}</button>,
}));

import MarkdownContent from '../MarkdownContent';

describe('MarkdownContent deliverable inline code', () => {
  it('linkifies workspace paths when not streaming', () => {
    render(
      <MarkdownContent
        content="Saved deliverable at `workspace/reports/q1-summary.md`."
        sources={[]}
        messageId="msg-deliverable-1"
        chatId="chat-1"
      />,
    );
    expect(screen.getByRole('button', { name: 'workspace/reports/q1-summary.md' })).toBeTruthy();
  });

  it('does not linkify during streaming', () => {
    render(
      <MarkdownContent
        content="Saved deliverable at `workspace/reports/q1-summary.md`."
        sources={[]}
        messageId="msg-deliverable-2"
        isStreaming
        chatId="chat-1"
      />,
    );
    expect(screen.queryByRole('button', { name: 'workspace/reports/q1-summary.md' })).toBeNull();
  });
});
