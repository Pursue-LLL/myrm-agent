/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

import ArtifactErrorBoundary from '../ArtifactErrorBoundary';

function Boom(): never {
  throw new Error('render exploded');
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ArtifactErrorBoundary localized fallback', () => {
  it('renders the translated title, default message and retry button when a child throws', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    render(
      <ArtifactErrorBoundary>
        <Boom />
      </ArtifactErrorBoundary>,
    );

    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('defaultMessage')).toBeInTheDocument();
    expect(screen.getByText('retry')).toBeInTheDocument();
    expect(screen.getByText('render exploded')).toBeInTheDocument();
  });

  it('prefers the caller-provided fallback message over the default one', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    render(
      <ArtifactErrorBoundary fallbackMessage="Custom message">
        <Boom />
      </ArtifactErrorBoundary>,
    );

    expect(screen.getByText('Custom message')).toBeInTheDocument();
    expect(screen.queryByText('defaultMessage')).not.toBeInTheDocument();
  });

  it('calls onReset when the retry button is pressed', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const onReset = vi.fn();
    render(
      <ArtifactErrorBoundary onReset={onReset}>
        <Boom />
      </ArtifactErrorBoundary>,
    );

    await userEvent.click(screen.getByText('retry'));

    expect(onReset).toHaveBeenCalledTimes(1);
  });
});
