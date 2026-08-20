import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EmptyState } from '../empty-state';
import {
  ListSkeleton,
  CardGridSkeleton,
  TableSkeleton,
  FormSkeleton,
  ListDetailSkeleton,
  MetricCardsSkeleton,
  TimelineSkeleton,
} from '../skeleton-templates';

describe('EmptyState Primitive', () => {
  it('renders title and description properly', () => {
    render(<EmptyState title="No Results Found" description="Try searching with different keywords" />);

    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText('No Results Found')).toBeInTheDocument();
    expect(screen.getByText('Try searching with different keywords')).toBeInTheDocument();
  });

  it('renders icon when provided', () => {
    const CustomIcon = ({ className }: { className?: string }) => (
      <svg data-testid="custom-icon" className={className} />
    );

    render(<EmptyState icon={CustomIcon} title="Empty List" />);

    expect(screen.getByTestId('custom-icon')).toBeInTheDocument();
  });

  it('renders action and secondaryAction buttons and responds to clicks', () => {
    const handleAction = vi.fn();
    const handleSecondary = vi.fn();

    render(
      <EmptyState
        title="No Documents"
        action={<button onClick={handleAction}>Create First</button>}
        secondaryAction={<button onClick={handleSecondary}>Learn More</button>}
      />,
    );

    const actionBtn = screen.getByText('Create First');
    const secondaryBtn = screen.getByText('Learn More');

    fireEvent.click(actionBtn);
    expect(handleAction).toHaveBeenCalledTimes(1);

    fireEvent.click(secondaryBtn);
    expect(handleSecondary).toHaveBeenCalledTimes(1);
  });

  it('applies variant classes correctly', () => {
    const { container } = render(<EmptyState variant="dashed" title="Dashed State" />);

    const el = container.firstChild as HTMLElement;
    expect(el.className).toContain('border-dashed');
  });

  it('renders error variant properly with alert styling', () => {
    const { container } = render(<EmptyState variant="error" title="Sync Failed" description="Network error" />);

    const el = container.firstChild as HTMLElement;
    expect(el.className).toContain('border-destructive');
    expect(screen.getByText('Sync Failed')).toBeInTheDocument();
  });
});

describe('Skeleton Templates', () => {
  it('renders ListSkeleton with default and custom count', () => {
    const { container } = render(<ListSkeleton count={4} />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThanOrEqual(4);
  });

  it('renders CardGridSkeleton properly', () => {
    render(<CardGridSkeleton count={2} columns={2} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders TableSkeleton properly', () => {
    render(<TableSkeleton rows={3} columns={3} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders FormSkeleton properly', () => {
    render(<FormSkeleton count={2} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders ListDetailSkeleton properly', () => {
    render(<ListDetailSkeleton />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders MetricCardsSkeleton properly', () => {
    render(<MetricCardsSkeleton count={4} />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
  });

  it('renders TimelineSkeleton properly', () => {
    render(<TimelineSkeleton count={3} />);
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
  });
});
