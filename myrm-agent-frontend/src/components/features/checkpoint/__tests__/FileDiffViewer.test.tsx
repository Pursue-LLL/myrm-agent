/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import FileDiffViewer from '../FileDiffViewer';

const stableT = (key: string): string => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/services/checkpoint', () => ({
  restoreFileSnapshot: vi.fn(),
}));

describe('FileDiffViewer', () => {
  it('closes through a button that has an accessible name', () => {
    const onClose = vi.fn();
    render(<FileDiffViewer snapshotId="snap-1" changes={[]} onClose={onClose} />);

    fireEvent.click(screen.getByRole('button', { name: 'close' }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
