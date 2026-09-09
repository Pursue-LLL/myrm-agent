// @vitest-environment jsdom
// @bun-test-dom
'use client';

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { useScopedArtifactStore } from '@/store/useScopedArtifactStore';
import { ScopedArtifactChip } from '@/components/features/chat-window/ScopedArtifactChip';

describe('ScopedArtifactStore & ScopedArtifactChip', () => {
  beforeEach(() => {
    useScopedArtifactStore.getState().clearTarget();
  });

  it('initially renders nothing when target is null', () => {
    const { container } = render(<ScopedArtifactChip />);
    expect(container.firstChild).toBeNull();
  });

  it('renders target information when set in store', () => {
    useScopedArtifactStore.getState().setTarget({
      artifactId: 'art-123',
      artifactName: 'financial_report.xlsx',
      kind: 'spreadsheet',
      scopeLabel: 'Sheet1!B2:D10',
      selectedSnippet: 'Revenue, 1000, 2000',
    });

    render(<ScopedArtifactChip />);

    expect(screen.getByText('financial_report.xlsx')).toBeDefined();
    expect(screen.getByText('Sheet1!B2:D10')).toBeDefined();
    expect(screen.getByText(/Revenue, 1000, 2000/)).toBeDefined();
  });

  it('clears target when close button is clicked', () => {
    useScopedArtifactStore.getState().setTarget({
      artifactId: 'art-code-1',
      artifactName: 'server.py',
      kind: 'code',
      scopeLabel: 'L10-L25',
      selectedSnippet: 'def process(): pass',
    });

    render(<ScopedArtifactChip />);

    const closeBtn = screen.getByLabelText('Remove scoped target');
    fireEvent.click(closeBtn);

    expect(useScopedArtifactStore.getState().target).toBeNull();
  });
});
