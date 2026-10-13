import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CatalogConnectionStatus } from './CatalogConnectionStatus';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('CatalogConnectionStatus', () => {
  it('renders the connected label with the success tone', () => {
    render(<CatalogConnectionStatus state="connected" />);

    expect(screen.getByText('connected')).toHaveClass('text-emerald-600');
  });

  it('renders the disabled label in the muted tone', () => {
    render(<CatalogConnectionStatus state="disabled" />);

    const label = screen.getByText('disabled');
    expect(label).toHaveClass('text-muted-foreground');
    expect(label).not.toHaveClass('text-emerald-600');
  });
});
