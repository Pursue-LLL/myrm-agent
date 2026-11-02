import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { StagedArtifactView } from '@/store/chat/types';

import { StagedArtifactsNotice } from '../StagedArtifactsNotice';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));

const artifact = (overrides: Partial<StagedArtifactView> = {}): StagedArtifactView => ({
  artifact_id: 'a1',
  filename: 'draft.py',
  relative_path: '.myrm/staged_artifacts/draft.py',
  full_path: '/work/.myrm/staged_artifacts/draft.py',
  language: 'python',
  size_bytes: 2048,
  line_count: 1,
  created_at: '2026-11-02T00:00:00Z',
  original_hint: null,
  ...overrides,
});

describe('StagedArtifactsNotice', () => {
  it('renders nothing when no artifact was staged', () => {
    const { container } = render(<StagedArtifactsNotice stagedArtifacts={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('pluralizes the summary by the number of staged drafts', () => {
    const { rerender } = render(<StagedArtifactsNotice stagedArtifacts={[artifact()]} />);
    expect(screen.getByText('Auto-staged 1 unsaved artifact draft to the workspace')).toBeInTheDocument();

    rerender(<StagedArtifactsNotice stagedArtifacts={[artifact(), artifact({ artifact_id: 'a2' })]} />);
    expect(screen.getByText('Auto-staged 2 unsaved artifact drafts to the workspace')).toBeInTheDocument();
  });

  it('lists line count, size and the sandbox note after expanding', () => {
    render(<StagedArtifactsNotice stagedArtifacts={[artifact({ line_count: 12 })]} />);
    expect(screen.queryByText('draft.py')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button'));

    expect(screen.getByText('draft.py')).toBeInTheDocument();
    expect(screen.getByText('12 lines')).toBeInTheDocument();
    expect(screen.getByText('2.0 KB')).toBeInTheDocument();
    expect(screen.getByText(/preserved in the sandbox/)).toBeInTheDocument();
  });
});
