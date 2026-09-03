/** @vitest-environment jsdom */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { isValidElement } from 'react';

import { linkifyErrorText } from '../utils';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: unknown) => unknown) => selector({ sendMessage: vi.fn(), messages: [] }),
}));

import ProgressSteps from '../ProgressSteps';
import type { ProgressItem } from '@/store/chat/types';

type AnchorElement = React.ReactElement<React.AnchorHTMLAttributes<HTMLAnchorElement>>;

function errorStep(overrides?: Partial<ProgressItem>): ProgressItem {
  return {
    step_key: 'tool_execution_failed',
    status: 'error',
    error: true,
    ...overrides,
  };
}

describe('linkifyErrorText', () => {
  it('converts a URL into a React anchor element', () => {
    const nodes = linkifyErrorText('Check https://platform.openai.com/api-keys now');
    expect(nodes).toHaveLength(3);
    expect(nodes[0]).toBe('Check ');
    expect(isValidElement(nodes[1])).toBe(true);
    const anchor = nodes[1] as AnchorElement;
    expect(anchor.props.href).toBe('https://platform.openai.com/api-keys');
    expect(anchor.props.target).toBe('_blank');
    expect(anchor.props.rel).toBe('noopener noreferrer');
    expect(nodes[2]).toBe(' now');
  });

  it('handles multiple URLs', () => {
    const nodes = linkifyErrorText('Go to https://a.com and http://b.com please');
    const anchors = nodes.filter(isValidElement);
    expect(anchors).toHaveLength(2);
    expect((anchors[0] as AnchorElement).props.href).toBe('https://a.com');
    expect((anchors[1] as AnchorElement).props.href).toBe('http://b.com');
  });

  it('returns plain text when no URLs present', () => {
    const nodes = linkifyErrorText('No URL here');
    expect(nodes).toHaveLength(1);
    expect(nodes[0]).toBe('No URL here');
    expect(nodes.filter(isValidElement)).toHaveLength(0);
  });

  it('handles URLs with query params and hash', () => {
    const nodes = linkifyErrorText('Visit http://x.com/path?q=1#sec');
    const anchors = nodes.filter(isValidElement);
    expect(anchors).toHaveLength(1);
    expect((anchors[0] as AnchorElement).props.href).toBe('http://x.com/path?q=1#sec');
  });

  it('stops URL at closing parenthesis', () => {
    const nodes = linkifyErrorText('(https://example.com) details');
    const anchors = nodes.filter(isValidElement);
    expect(anchors).toHaveLength(1);
    expect((anchors[0] as AnchorElement).props.href).toBe('https://example.com');
  });

  it('handles multi-line text', () => {
    const text = '1. Check key\n2. Visit https://openai.com\n3. Retry';
    const nodes = linkifyErrorText(text);
    const anchors = nodes.filter(isValidElement);
    expect(anchors).toHaveLength(1);
    expect((anchors[0] as AnchorElement).props.href).toBe('https://openai.com');
  });

  it('does NOT render HTML tags from malicious error text (XSS prevention)', () => {
    const malicious = 'Error <script>alert(1)</script> see https://safe.com';
    const nodes = linkifyErrorText(malicious);
    const strings = nodes.filter((n): n is string => typeof n === 'string');
    const joined = strings.join('');
    expect(joined).toContain('<script>alert(1)</script>');
    expect(nodes.filter(isValidElement)).toHaveLength(1);
  });

  it('returns empty string segment for URL-only text', () => {
    const nodes = linkifyErrorText('https://only-url.com');
    expect(nodes).toHaveLength(3);
    const anchors = nodes.filter(isValidElement);
    expect(anchors).toHaveLength(1);
    expect((anchors[0] as AnchorElement).props.href).toBe('https://only-url.com');
  });
});

describe('ProgressSteps fault-side badge', () => {
  it('renders the localized fault badge when an error step carries fault_side', async () => {
    render(<ProgressSteps messageId="m-1" steps={[errorStep({ fault_side: 'model' })]} loading={false} />);
    await userEvent.click(screen.getByTestId('progress-steps-toggle'));
    expect(screen.getByText('faultSides.model')).toBeInTheDocument();
  });

  it('omits the fault badge when fault_side is unknown or absent', async () => {
    const { rerender } = render(
      <ProgressSteps messageId="m-1" steps={[errorStep({ fault_side: 'unknown' })]} loading={false} />,
    );
    await userEvent.click(screen.getByTestId('progress-steps-toggle'));
    expect(screen.queryByText(/^faultSides\./)).not.toBeInTheDocument();

    rerender(<ProgressSteps messageId="m-1" steps={[errorStep()]} loading={false} />);
    await userEvent.click(screen.getByTestId('progress-steps-toggle'));
    expect(screen.queryByText(/^faultSides\./)).not.toBeInTheDocument();
  });

  it('renders blocked step status without error state', async () => {
    const blockedStep: ProgressItem = {
      step_key: 'todo_blocked_task',
      tool_name: 'todo_write',
      status: 'blocked',
      is_plan: true,
      items: 'Waiting for external resource',
    };
    render(<ProgressSteps messageId="m-1" steps={[blockedStep]} loading={false} />);
    await userEvent.click(screen.getByTestId('progress-steps-toggle'));
    expect(screen.getByText('progress.kanban')).toBeInTheDocument();
  });
});
