/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { TraceLLMCall } from '@/services/statistics';

const stableT = (key: string, values?: Record<string, unknown>) =>
  values ? `${key}:${Object.values(values).join('/')}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));
vi.mock('@/components/features/memory/replay/ModelViewportView', () => ({
  default: () => <div>viewport-body</div>,
}));

import TraceLLMCallItem from '../TraceLLMCallItem';

const BASE: TraceLLMCall = {
  sequence: 1,
  start_time: 0,
  model_name: 'gpt-test',
  duration_ms: 2000,
  ttft_ms: 500,
  prompt_tokens: 120,
  completion_tokens: 80,
  total_tokens: 200,
  message_count: 4,
  prompt_preview: 'hello',
};

describe('TraceLLMCallItem localized copy', () => {
  it('renders the token, latency and count labels from translations', () => {
    const { container } = render(<TraceLLMCallItem llmCall={BASE} />);

    expect(screen.getByText('llmTokens:200')).toBeInTheDocument();
    expect(screen.getByText('llmTtft:500')).toBeInTheDocument();
    expect(screen.getByText('llmGeneration:1500')).toBeInTheDocument();
    expect(screen.getByText('llmPrompt:120')).toBeInTheDocument();
    expect(screen.getByText('llmCompletion:80')).toBeInTheDocument();
    expect(screen.getByText('llmMessages:4')).toBeInTheDocument();
    expect(container.querySelector('[title="llmNetworkWaitTitle:500"]')).not.toBeNull();
    expect(container.querySelector('[title="llmGenerationTitle:1500"]')).not.toBeNull();
  });

  it('falls back to the translated unknown-model label and shows the retry badge', () => {
    render(<TraceLLMCallItem llmCall={{ ...BASE, model_name: null, retry_count: 2 }} />);

    expect(screen.getByText('llmUnknownModel')).toBeInTheDocument();
    expect(screen.getByText('llmRetry:3')).toBeInTheDocument();
  });

  it('toggles the model viewport label between inspect and hide', async () => {
    render(<TraceLLMCallItem llmCall={BASE} />);

    await userEvent.click(screen.getByText('llmViewportInspect'));

    expect(screen.getByText('llmViewportHide')).toBeInTheDocument();
    expect(screen.getByText('viewport-body')).toBeInTheDocument();
  });
});
