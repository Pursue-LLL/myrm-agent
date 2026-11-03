import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

import ThinkBox from '../ThinkBox';

describe('ThinkBox', () => {
  it('titles the collapsible block through a translation and reveals the content on demand', () => {
    render(<ThinkBox content="step one" />);

    expect(screen.queryByText('step one')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'thinkingProcess' }));
    expect(screen.getByText('step one')).toBeInTheDocument();
  });
});
