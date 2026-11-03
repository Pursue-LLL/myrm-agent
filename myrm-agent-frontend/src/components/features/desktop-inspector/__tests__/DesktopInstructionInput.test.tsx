/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import DesktopInstructionInput from '../DesktopInstructionInput';
import type { BrowserRefInfo } from '@/store/chat/types';

const info: BrowserRefInfo = { role: 'button', name: 'Save', nth: 1, position: null, bbox: null };

describe('DesktopInstructionInput selection badge', () => {
  it('labels the clear button from translations and clears the selection', () => {
    const onClearSelection = vi.fn();
    render(
      <DesktopInstructionInput
        selectedRefId="d1"
        selectedInfo={info}
        instructionText=""
        onInstructionChange={vi.fn()}
        onSubmit={vi.fn()}
        onClearSelection={onClearSelection}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'clearSelection' }));

    expect(onClearSelection).toHaveBeenCalledTimes(1);
  });
});
