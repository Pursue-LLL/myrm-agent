import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TurnRevertCard } from '../TurnRevertCard';
import { useTurnRevertReviewStore } from '../useTurnRevertReviewStore';
import type { TurnFileChange } from '../revertReviewTypes';

describe('TurnRevertCard', () => {
  beforeEach(() => {
    useTurnRevertReviewStore.getState().reset();
    vi.restoreAllMocks();
  });

  const mockChanges: TurnFileChange[] = [
    {
      path: 'src/components/Header.tsx',
      operation: 'update',
      has_original: true,
      timestamp: Date.now(),
      additions: 12,
      deletions: 3,
    },
    {
      path: 'src/utils/helpers.ts',
      operation: 'create',
      has_original: false,
      timestamp: Date.now(),
      additions: 25,
      deletions: 0,
    },
  ];

  it('renders nothing when changes array is empty', () => {
    const { container } = render(
      <TurnRevertCard sessionId="sess-1" messageId="msg-1" changes={[]} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders file summary badge with addition/deletion counts', () => {
    render(<TurnRevertCard sessionId="sess-1" messageId="msg-1" changes={mockChanges} />);
    expect(screen.getByText('已修改 2 个文件')).toBeDefined();
    expect(screen.getByText('+37')).toBeDefined();
    expect(screen.getByText('-3')).toBeDefined();
  });

  it('toggles file list expansion on click', () => {
    render(<TurnRevertCard sessionId="sess-1" messageId="msg-1" changes={mockChanges} />);
    const toggleBtn = screen.getByRole('button', { name: /展开文件变更列表/ });
    fireEvent.click(toggleBtn);

    expect(screen.getByText('Header.tsx')).toBeDefined();
    expect(screen.getByText('helpers.ts')).toBeDefined();
  });

  it('opens confirmation modal when clicking revert button', () => {
    render(<TurnRevertCard sessionId="sess-1" messageId="msg-1" changes={mockChanges} />);
    const revertBtn = screen.getByRole('button', { name: /一键撤销本轮文件改动/ });
    fireEvent.click(revertBtn);

    expect(screen.getByText('确认撤销本轮文件改动？')).toBeDefined();
    expect(screen.getByText('确认还原')).toBeDefined();
  });

  it('triggers revertTurn and updates state on confirm', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        reverted_files: ['src/components/Header.tsx', 'src/utils/helpers.ts'],
        warnings: [],
        skipped_files: [],
      }),
    });

    render(<TurnRevertCard sessionId="sess-1" messageId="msg-1" changes={mockChanges} />);
    const revertBtn = screen.getByRole('button', { name: /一键撤销本轮文件改动/ });
    fireEvent.click(revertBtn);

    const confirmBtn = screen.getByRole('button', { name: /确认还原/ });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByText('已成功撤销')).toBeDefined();
    });
  });
});
