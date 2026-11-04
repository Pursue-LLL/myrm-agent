import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  CardGridSkeleton,
  FormSkeleton,
  ListDetailSkeleton,
  ListSkeleton,
  MetricCardsSkeleton,
  TableSkeleton,
  TimelineSkeleton,
} from '../skeleton-templates';

describe('skeleton templates', () => {
  it.each([
    ['ListSkeleton', ListSkeleton, 'loadingList'],
    ['CardGridSkeleton', CardGridSkeleton, 'loadingCards'],
    ['TableSkeleton', TableSkeleton, 'loadingTable'],
    ['FormSkeleton', FormSkeleton, 'loadingForm'],
    ['ListDetailSkeleton', ListDetailSkeleton, 'loadingWorkspace'],
    ['MetricCardsSkeleton', MetricCardsSkeleton, 'loadingMetrics'],
    ['TimelineSkeleton', TimelineSkeleton, 'loadingTimeline'],
  ])('%s announces its loading state through a translated label', (_name, Skeleton, key) => {
    render(<Skeleton />);

    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-busy', 'true');
    expect(status).toHaveAttribute('aria-label', key);
  });
});
