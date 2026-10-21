import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import PowerStackLane from '../PowerStackLane';

const stableT = (key: string, params?: Record<string, string>) =>
  params?.provider ? `${key}:${params.provider}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

describe('PowerStackLane', () => {
  it('renders three columns and routes to existing settings pages', () => {
    render(<PowerStackLane />);
    expect(screen.getByText('title')).toBeTruthy();
    expect(screen.getByText('columns.external.title')).toBeTruthy();
    expect(screen.getByText('columns.orchestrator.title')).toBeTruthy();
    expect(screen.getByText('columns.local.title')).toBeTruthy();

    fireEvent.click(screen.getByText('columns.orchestrator.title'));
    expect(mockPush).toHaveBeenCalledWith('/settings/agents');
    fireEvent.click(screen.getByText('pricingLink'));
    expect(mockPush).toHaveBeenCalledWith('/pricing');
  });

  it('links the pinned setup guide to docs getting-started', () => {
    render(<PowerStackLane />);
    const guide = screen.getByText('setupGuideLink');
    expect(guide.getAttribute('href')).toContain('/getting-started/quickstart');
    expect(guide.getAttribute('target')).toBe('_blank');
  });
});
