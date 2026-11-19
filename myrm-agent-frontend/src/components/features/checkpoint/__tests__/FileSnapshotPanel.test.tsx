/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import FileSnapshotPanel from '../FileSnapshotPanel';

const stableT = (key: string): string => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: { workspaceDir: string }) => unknown) => selector({ workspaceDir: '/ws' }),
}));

vi.mock('../FileSnapshotList', () => ({
  default: () => <div data-testid="snapshot-list" />,
}));

describe('FileSnapshotPanel', () => {
  it('closes through a button that has an accessible name', () => {
    render(<FileSnapshotPanel />);

    fireEvent.click(screen.getByRole('button', { name: 'panelTitle' }));
    expect(screen.getByTestId('snapshot-list')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'close' }));
    expect(screen.queryByTestId('snapshot-list')).not.toBeInTheDocument();
  });
});
