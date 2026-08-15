/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { TraceError } from '@/services/statistics';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

import TraceErrorItem from '../TraceErrorItem';

function baseError(overrides?: Partial<TraceError>): TraceError {
  return {
    sequence: 1,
    error_type: 'rate_limit_error',
    error: 'rate limited',
    fault_side: null,
    diagnostic_result: null,
    ...overrides,
  };
}

describe('TraceErrorItem', () => {
  it('renders the error type and message', () => {
    render(<TraceErrorItem error={baseError()} isFirstIrrecoverable={false} />);
    expect(screen.getByText('rate_limit_error')).toBeInTheDocument();
    expect(screen.getByText('rate limited')).toBeInTheDocument();
  });

  it('shows the fault-side badge when fault_side is present', () => {
    render(<TraceErrorItem error={baseError({ fault_side: 'model' })} isFirstIrrecoverable={false} />);
    expect(screen.getByText('faultSides.model')).toBeInTheDocument();
  });

  it('omits the fault-side badge for unknown or absent fault_side', () => {
    const { rerender } = render(
      <TraceErrorItem error={baseError({ fault_side: 'unknown' })} isFirstIrrecoverable={false} />,
    );
    expect(screen.queryByText(/^faultSides\./)).not.toBeInTheDocument();

    rerender(<TraceErrorItem error={baseError({ fault_side: null })} isFirstIrrecoverable={false} />);
    expect(screen.queryByText(/^faultSides\./)).not.toBeInTheDocument();
  });

  it('marks the first irrecoverable error', () => {
    render(<TraceErrorItem error={baseError()} isFirstIrrecoverable />);
    expect(screen.getByText('firstIrrecoverable')).toBeInTheDocument();
  });

  it('renders up to 4 localized recovery steps from the diagnostic', () => {
    const error = baseError({
      diagnostic_result: {
        error_type: 'rate_limit_error',
        resolution_steps: ['step 1', 'step 2', 'step 3', 'step 4', 'step 5'],
      },
    });
    render(<TraceErrorItem error={error} isFirstIrrecoverable={false} />);
    expect(screen.getByText('recoverySteps')).toBeInTheDocument();
    expect(screen.getByText('1. step 1')).toBeInTheDocument();
    expect(screen.getByText('4. step 4')).toBeInTheDocument();
    expect(screen.queryByText('5. step 5')).not.toBeInTheDocument();
  });

  it('renders no recovery section when the diagnostic carries no steps', () => {
    render(<TraceErrorItem error={baseError()} isFirstIrrecoverable={false} />);
    expect(screen.queryByText('recoverySteps')).not.toBeInTheDocument();
  });
});
