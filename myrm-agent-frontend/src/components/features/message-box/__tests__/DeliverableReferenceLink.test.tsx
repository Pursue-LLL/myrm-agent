/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const openArtifactDeliverable = vi.hoisted(() =>
  vi.fn<(...args: unknown[]) => Promise<undefined>>(async () => undefined),
);
const openWorkspaceDeliverable = vi.hoisted(() =>
  vi.fn<(...args: unknown[]) => Promise<undefined>>(async () => undefined),
);

const stableT = (key: string) => (key === 'awaitingArtifact' ? 'Waiting for artifact sync' : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/deliverable/openWorkspaceDeliverable', () => ({
  openArtifactDeliverable,
  openWorkspaceDeliverable,
}));

import DeliverableReferenceLink from '../DeliverableReferenceLink';

describe('DeliverableReferenceLink', () => {
  beforeEach(() => {
    openArtifactDeliverable.mockClear();
    openWorkspaceDeliverable.mockClear();
  });

  it('opens portal via short_file_id artifact match', async () => {
    render(
      <DeliverableReferenceLink
        reference={{ kind: 'file_id', id: '@file_001' }}
        label="@file_001"
        messageArtifacts={[
          {
            id: 'artifact-uuid-1',
            filename: 'report.md',
            type: 'document',
            content_type: 'text/markdown',
            size: 12,
            preview_url: '/api/v1/files/artifact-uuid-1',
            download_url: '/api/v1/files/artifact-uuid-1?download=1',
            short_file_id: '@file_001',
          },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '@file_001' }));

    await waitFor(() => {
      expect(openArtifactDeliverable).toHaveBeenCalledTimes(1);
    });
    const firstCall = openArtifactDeliverable.mock.calls[0]?.[0] as { short_file_id: string } | undefined;
    expect(firstCall?.short_file_id).toBe('@file_001');
  });

  it('disables @file link when artifact not yet synced', () => {
    render(
      <DeliverableReferenceLink
        reference={{ kind: 'file_id', id: '@file_002' }}
        label="@file_002"
        messageArtifacts={[]}
      />,
    );

    const button = screen.getByRole('button', { name: '@file_002' });
    expect(button).toBeDisabled();
    expect(button.getAttribute('title')).toBe('Waiting for artifact sync');
    expect(openArtifactDeliverable).not.toHaveBeenCalled();
  });
});
