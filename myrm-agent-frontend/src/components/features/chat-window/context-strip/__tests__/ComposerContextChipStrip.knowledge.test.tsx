'use client';

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ComposerContextChipStrip } from '../ComposerContextChipStrip';
import type { ContextChipItem, ComposerContextSummary } from '@/hooks/message-input/useComposerContextChips';

vi.mock('@/hooks/ui/useMediaQuery', () => ({
  useIsMobile: () => false,
}));

const stableT = (key: string) => {
  const map: Record<string, string> = {
    remove: '移除',
    overloadedNotice: '当前挂载的上下文较多',
  };
  return map[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('ComposerContextChipStrip Knowledge Base Chips', () => {
  const defaultSummary: ComposerContextSummary = {
    totalItems: 1,
    totalSkills: 0,
    totalMcp: 0,
    totalFiles: 0,
    isOverloaded: false,
  };

  it('renders knowledge base chip with correct label and remove button', () => {
    const handleRemove = vi.fn();
    const chips: ContextChipItem[] = [
      {
        id: 'knowledge-kb-1',
        category: 'knowledge',
        label: '核心政策库',
        detail: '知识库',
        tooltip: '核心政策库',
        iconType: 'knowledge',
        isRemovable: true,
        onRemove: handleRemove,
      },
    ];

    render(<ComposerContextChipStrip chips={chips} summary={defaultSummary} />);

    expect(screen.getByText('核心政策库')).toBeDefined();
    expect(screen.getByText('(知识库)')).toBeDefined();

    const removeBtn = screen.getByRole('button', { name: /移除: 核心政策库/i });
    fireEvent.click(removeBtn);
    expect(handleRemove).toHaveBeenCalledTimes(1);
  });
});
