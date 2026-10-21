/** @vitest-environment jsdom */

vi.mock('next-intl', async (importOriginal) => {
  const actual = await importOriginal<typeof import('next-intl')>();
  return {
    ...actual,
    useLocale: () => 'en',
  };
});

import React from 'react';
import { render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';

import { promptCacheEnMessages } from './promptCacheTestMessages';
import { PromptCacheConsolidationView } from '../command-center/PromptCacheConsolidationView';

function renderView(props: React.ComponentProps<typeof PromptCacheConsolidationView>) {
  return render(
    <NextIntlClientProvider locale="en" messages={promptCacheEnMessages}>
      <PromptCacheConsolidationView {...props} />
    </NextIntlClientProvider>,
  );
}

describe('PromptCacheConsolidationView', () => {
  const baseProps = {
    sessionId: 'session_test',
    preview: null,
    metrics: null,
    onSimulatePreview: vi.fn(async () => undefined),
    isLoading: false,
  };

  it('does not show placeholder 100% cache metrics when telemetry is missing', () => {
    renderView(baseProps);

    expect(screen.getByText('Prefix layout')).toBeInTheDocument();
    expect(screen.queryByText(/\b100%\b/)).not.toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('See the chat context ring for cache hit rate')).toBeInTheDocument();
  });

  it('renders in-flight delta count when metrics are present', () => {
    renderView({
      ...baseProps,
      metrics: {
        system_prompt_frozen: true,
        system_prompt_byte_hash: 'abc',
        kv_cache_hit_ratio: 0.42,
        in_flight_deltas_count: 3,
        recency_perception_delay_ms: 1.5,
        avoided_recomputation_tokens: 120,
      },
    });

    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getAllByText('System prefix unchanged this turn').length).toBeGreaterThan(0);
  });
});
