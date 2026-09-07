import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import { TaskCardPlaceholder } from '../TaskCardPlaceholder';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params?.percent !== undefined) {
    return `${key}:${params.percent}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('TaskCardPlaceholder', () => {
  it('renders queued status and background hint by default', () => {
    render(<TaskCardPlaceholder />);
    expect(screen.getByText('queued')).toBeInTheDocument();
    expect(screen.getByText('backgroundHint')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'cancelTask' })).not.toBeInTheDocument();
  });

  it('renders progress text and bar when progress > 0', () => {
    render(<TaskCardPlaceholder progress={0.45} prompt="Generate a cat" />);
    expect(screen.getByText('generatingProgress:45')).toBeInTheDocument();
    expect(screen.getByText('Generate a cat')).toBeInTheDocument();
  });

  it('triggers onCancel with taskId and handles loading state', async () => {
    const handleCancel = vi.fn().mockImplementation(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10));
    });

    render(<TaskCardPlaceholder taskId="task-abc" onCancel={handleCancel} />);
    const cancelBtn = screen.getByRole('button', { name: 'cancelTask' });
    expect(cancelBtn).toBeInTheDocument();

    fireEvent.click(cancelBtn);
    expect(handleCancel).toHaveBeenCalledWith('task-abc');

    await waitFor(() => {
      expect(screen.getByText('cancelTask')).toBeInTheDocument();
    });
  });

  it('gracefully handles onCancel rejection without crashing', async () => {
    const handleCancel = vi.fn().mockRejectedValue(new Error('Network error'));

    render(<TaskCardPlaceholder taskId="task-err" onCancel={handleCancel} />);
    const cancelBtn = screen.getByRole('button', { name: 'cancelTask' });

    fireEvent.click(cancelBtn);
    expect(handleCancel).toHaveBeenCalledWith('task-err');

    await waitFor(() => {
      expect(screen.getByText('cancelTask')).toBeInTheDocument();
    });
  });
});
