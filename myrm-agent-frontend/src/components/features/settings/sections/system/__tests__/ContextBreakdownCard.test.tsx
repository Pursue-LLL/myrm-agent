/** @vitest-environment jsdom */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ContextBreakdownCard from '../ContextBreakdownCard';
import type { ContextBreakdown } from '@/services/statistics';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

describe('ContextBreakdownCard Component', () => {
  it('renders null when breakdown is undefined', () => {
    const { container } = render(<ContextBreakdownCard breakdown={undefined} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders token distribution and health diagnosis', () => {
    const mockBreakdown: ContextBreakdown = {
      system_tokens: 3000,
      chat_tokens: 2000,
      tool_tokens: 5000,
      file_tokens: 1000,
      total_context_tokens: 11000,
      health_score: 90,
      diagnosis_status: 'healthy',
      diagnosis_message: 'Context is healthy and well-balanced.',
      hotspots: [
        {
          tool_name: 'bash_code_execute_tool',
          tokens: 4500,
          step_sequence: 3,
          status: 'auto_pruned',
          summary: 'pytest completed',
        },
      ],
    };

    render(<ContextBreakdownCard breakdown={mockBreakdown} />);

    expect(screen.getByText('title')).toBeInTheDocument();
    expect(screen.getByText('90/100')).toBeInTheDocument();
    expect(screen.getByText('Context is healthy and well-balanced.')).toBeInTheDocument();
    expect(screen.getByText('hotspotsTitle')).toBeInTheDocument();
    expect(screen.getByText(/bash_code_execute_tool/)).toBeInTheDocument();
    expect(screen.getByText('autoPruned')).toBeInTheDocument();
  });
});
