/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import InspectorInstructionInput from '../InspectorInstructionInput';
import type { BrowserRefInfo } from '@/store/chat/types';

const info: BrowserRefInfo = { role: 'button', name: 'Save', nth: 1, position: null, bbox: null };

describe('InspectorInstructionInput selection badge', () => {
  it('labels the clear button from translations and clears the selection', () => {
    const onClearSelection = vi.fn();
    render(
      <InspectorInstructionInput
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
