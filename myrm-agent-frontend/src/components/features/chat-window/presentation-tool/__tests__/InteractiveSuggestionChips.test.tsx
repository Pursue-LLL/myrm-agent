import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { InteractiveSuggestionChips } from '../InteractiveSuggestionChips';
import { SuggestionChipItem } from '../presentationToolTypes';
import { usePresentationToolStore } from '../usePresentationToolStore';

describe('InteractiveSuggestionChips', () => {
  beforeEach(() => {
    usePresentationToolStore.getState().reset();
  });

  const mockChips: SuggestionChipItem[] = [
    {
      id: 'chip-1',
      label: '导出 Excel 报销表',
      actionQuery: '请帮我导出为 Excel 报销表',
      position: 1,
    },
    {
      id: 'chip-2',
      label: '查看合规风险项',
      actionQuery: '列出所有发票合规风险项',
      position: 2,
    },
  ];

  it('renders nothing when chips array is empty', () => {
    const { container } = render(<InteractiveSuggestionChips chips={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders chips with label and position badge accurately', () => {
    render(<InteractiveSuggestionChips chips={mockChips} />);

    expect(screen.getByTestId('interactive-suggestion-chips')).toBeDefined();
    expect(screen.getByText('建议追问:')).toBeDefined();
    expect(screen.getByText('导出 Excel 报销表')).toBeDefined();
    expect(screen.getByText('查看合规风险项')).toBeDefined();
    expect(screen.getByText('1')).toBeDefined();
    expect(screen.getByText('2')).toBeDefined();
  });

  it('handles chip click and triggers onChipSelected and store updates', () => {
    const onSelect = vi.fn();
    render(
      <InteractiveSuggestionChips
        chips={mockChips}
        onChipSelected={onSelect}
      />,
    );

    const firstChip = screen.getByText('导出 Excel 报销表');
    fireEvent.click(firstChip);

    expect(onSelect).toHaveBeenCalledWith(mockChips[0]);
    expect(usePresentationToolStore.getState().lastActionQuery).toBe(
      '请帮我导出为 Excel 报销表',
    );
  });
});
