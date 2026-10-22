import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { OmniReferenceChip } from '../OmniReferenceChip';
import type { ResolvedContextSlice } from '../omniReferenceTypes';

describe('OmniReferenceChip', () => {
  const mockSlice: ResolvedContextSlice = {
    dimension: 'artifact',
    target_id: 'art_123',
    label: '性能压测柱状图',
    content_slice: 'Throughput: 120 tokens/sec\nLatency: 280ms',
    is_truncated: false,
    token_estimate: 24,
    provenance_uri: 'myrm://artifact/art_123',
  };

  it('renders chip label and icon', () => {
    render(
      <OmniReferenceChip
        dimension="artifact"
        targetId="art_123"
        label="性能压测柱状图"
        slice={mockSlice}
      />
    );

    expect(screen.getByTestId('omni-chip-artifact-art_123')).toBeInTheDocument();
    expect(screen.getByText('性能压测柱状图')).toBeInTheDocument();
  });

  it('toggles slice preview popover and displays provenance uri when clicked', () => {
    const mockClick = vi.fn();
    render(
      <OmniReferenceChip
        dimension="artifact"
        targetId="art_123"
        label="性能压测柱状图"
        slice={mockSlice}
        onClick={mockClick}
      />
    );

    const labelBtn = screen.getByText('性能压测柱状图');
    fireEvent.click(labelBtn);

    expect(mockClick).toHaveBeenCalled();
    expect(screen.getByTestId('omni-chip-popover')).toBeInTheDocument();
    expect(screen.getByText(/Throughput: 120 tokens\/sec/)).toBeInTheDocument();
    expect(screen.getByText('myrm://artifact/art_123')).toBeInTheDocument();
  });

  it('triggers onRemove callback when remove button is clicked', () => {
    const mockRemove = vi.fn();
    render(
      <OmniReferenceChip
        dimension="session"
        targetId="sess_999"
        label="历史会话"
        onRemove={mockRemove}
      />
    );

    const removeBtn = screen.getByTestId('chip-remove-session-sess_999');
    fireEvent.click(removeBtn);

    expect(mockRemove).toHaveBeenCalled();
  });
});
