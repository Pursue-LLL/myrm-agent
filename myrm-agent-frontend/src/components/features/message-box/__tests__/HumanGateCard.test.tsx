import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const stableT = (key: string) => {
  const translations: Record<string, string> = {
    title: 'Human Decision Required',
    timedOut: 'Decision timed out (default applied):',
    confirmed: 'Decision confirmed:',
    completed: 'Completed',
    customPlaceholder: 'Or enter custom response...',
    emptyPlaceholder: 'Enter your decision / input...',
    submit: 'Submit',
    submitFailed: 'Failed to submit response. Please try again.',
    actionContinue: 'Continue',
    actionStop: 'Stop & Save',
    actionExtraRounds: '+10 Rounds',
    actionInstructions: 'Provide Guidance',
  };
  return translations[key] || key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const mockSubmitHumanGateResponse = vi.fn();
vi.mock('@/services/chat', () => ({
  submitHumanGateResponse: (...args: unknown[]) => mockSubmitHumanGateResponse(...args),
}));

const mockState = vi.hoisted(() => ({
  messages: [] as Array<{
    messageId: string;
    role: 'assistant' | 'user' | 'system';
    humanGate?: {
      status: 'waiting' | 'resolved';
      answer?: string;
      timedOut?: boolean;
    };
  }>,
  setMessages: (updater: (state: { messages: typeof mockState.messages }) => void) => {
    updater(mockState);
  },
}));

vi.mock('@/store/useChatStore', () => ({
  default: Object.assign((selector: (state: typeof mockState) => unknown) => selector(mockState), {
    getState: () => mockState,
    setState: (updater: (state: typeof mockState) => void) => {
      updater(mockState);
    },
  }),
}));

const mockToastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => mockToastError(...args),
  },
}));

import { HumanGateCard } from '../HumanGateCard';

describe('HumanGateCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockState.messages = [
      {
        messageId: 'msg-gate-1',
        role: 'assistant',
        humanGate: {
          status: 'waiting',
        },
      },
    ];
  });

  it('renders waiting state with question, options, and countdown', () => {
    render(
      <HumanGateCard
        messageId="msg-gate-1"
        question="Apply schema migration?"
        options={['continue', 'stop', 'custom_option']}
        timeoutSeconds={300}
        defaultAction="stop"
        status="waiting"
      />,
    );

    expect(screen.getByText('Human Decision Required')).toBeDefined();
    expect(screen.getByText('Apply schema migration?')).toBeDefined();
    expect(screen.getByText('Continue')).toBeDefined();
    expect(screen.getByText('Stop & Save')).toBeDefined();
    expect(screen.getByText('custom_option')).toBeDefined();
    expect(screen.getByText('Submit')).toBeDefined();
  });

  it('submits response when option button is clicked', async () => {
    const user = userEvent.setup();
    mockSubmitHumanGateResponse.mockResolvedValueOnce(undefined);

    render(
      <HumanGateCard
        messageId="msg-gate-1"
        question="Apply schema migration?"
        options={['continue', 'stop']}
        timeoutSeconds={300}
        defaultAction="stop"
        status="waiting"
      />,
    );

    const continueBtn = screen.getByText('Continue');
    await user.click(continueBtn);

    expect(mockSubmitHumanGateResponse).toHaveBeenCalledWith('msg-gate-1', 'continue');
    expect(mockState.messages[0].humanGate?.status).toBe('resolved');
    expect(mockState.messages[0].humanGate?.answer).toBe('continue');
  });

  it('submits custom input text when enter key is pressed', async () => {
    const user = userEvent.setup();
    mockSubmitHumanGateResponse.mockResolvedValueOnce(undefined);

    render(
      <HumanGateCard
        messageId="msg-gate-1"
        question="Please specify instructions"
        options={[]}
        timeoutSeconds={300}
        defaultAction=""
        status="waiting"
      />,
    );

    const input = screen.getByPlaceholderText('Enter your decision / input...');
    await user.type(input, 'Run tests first{Enter}');

    expect(mockSubmitHumanGateResponse).toHaveBeenCalledWith('msg-gate-1', 'Run tests first');
    expect(mockState.messages[0].humanGate?.status).toBe('resolved');
    expect(mockState.messages[0].humanGate?.answer).toBe('Run tests first');
  });

  it('renders resolved state when status is resolved', () => {
    render(
      <HumanGateCard
        messageId="msg-gate-1"
        question="Apply schema migration?"
        status="resolved"
        answer="continue"
        timedOut={false}
      />,
    );

    expect(screen.getByText(/Decision confirmed:/)).toBeDefined();
    expect(screen.getByText('continue')).toBeDefined();
    expect(screen.queryByText('Submit')).toBeNull();
  });

  it('renders timedOut resolved state with default action note', () => {
    render(
      <HumanGateCard
        messageId="msg-gate-1"
        question="Apply schema migration?"
        status="resolved"
        defaultAction="stop"
        timedOut={true}
      />,
    );

    expect(screen.getByText(/Decision timed out \(default applied\):/)).toBeDefined();
    expect(screen.getByText('stop')).toBeDefined();
  });

  it('shows error toast when submission fails', async () => {
    const user = userEvent.setup();
    mockSubmitHumanGateResponse.mockRejectedValueOnce(new Error('Network error'));

    render(
      <HumanGateCard
        messageId="msg-gate-1"
        question="Apply schema migration?"
        options={['continue']}
        status="waiting"
      />,
    );

    await user.click(screen.getByText('Continue'));
    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith('Network error');
    });
  });

  it('resets input and timer when question changes for multi-stage gates', async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <HumanGateCard
        messageId="msg-gate-1"
        question="Question 1: Proceed?"
        options={[]}
        timeoutSeconds={300}
        status="waiting"
      />,
    );

    const input = screen.getByPlaceholderText('Enter your decision / input...');
    await user.type(input, 'partial draft');
    expect((input as HTMLInputElement).value).toBe('partial draft');

    rerender(
      <HumanGateCard
        messageId="msg-gate-1"
        question="Question 2: Select tier?"
        options={[]}
        timeoutSeconds={300}
        status="waiting"
      />,
    );

    expect(screen.getByText('Question 2: Select tier?')).toBeDefined();
    expect((screen.getByPlaceholderText('Enter your decision / input...') as HTMLInputElement).value).toBe('');
  });
});
