import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import { startFakeClock, stopFakeClock } from '@/test-utils/fakeClock';

import SubagentPromptButton from '../SubagentPromptButton';

const toast = vi.hoisted(() => vi.fn<(options: { title: string; variant?: string }) => void>());
vi.mock('@/hooks/shared/useToast', () => ({ toast }));

const sendMessage = vi.fn<(input: string) => Promise<boolean>>();

const elapse = (ms: number) => act(() => vi.advanceTimersByTime(ms));
/** The countdown arms its next second only after the previous one rendered, so it is stepped second by second. */
const countDown = (seconds: number) => {
  for (let second = 0; second < seconds; second += 1) {
    elapse(1000);
  }
};
const setPrompt = (visible: boolean) => act(() => useChatStore.setState({ subagentPromptVisible: visible }));
const promptButton = () => screen.queryByRole('button');

beforeEach(() => {
  startFakeClock();
  vi.resetAllMocks();
  sendMessage.mockResolvedValue(true);
  act(() =>
    useChatStore.setState({
      subagentPromptVisible: false,
      subagentPromptTimer: null,
      subagentPromptMessageId: null,
      sendMessage,
    }),
  );
});

afterEach(stopFakeClock);

describe('SubagentPromptButton appearing', () => {
  it('shows nothing while no prompt is due', () => {
    const { container } = render(<SubagentPromptButton />);

    expect(container).toBeEmptyDOMElement();
  });

  it('appears with the call to action and a five second countdown once the store shows it', () => {
    render(<SubagentPromptButton />);

    setPrompt(true);

    expect(promptButton()).toHaveTextContent('subagent.viewResults(5s)');
  });

  it('appears five seconds after a sub-agent finished, as long as no reply came in between', () => {
    render(<SubagentPromptButton />);

    act(() => useChatStore.getState().triggerSubagentPrompt('m1'));
    elapse(4999);
    expect(promptButton()).toBeNull();
    elapse(1);

    expect(promptButton()).toBeInTheDocument();
  });

  it('disappears when the store withdraws it', () => {
    render(<SubagentPromptButton />);
    setPrompt(true);

    setPrompt(false);

    expect(promptButton()).toBeNull();
  });
});

describe('SubagentPromptButton countdown', () => {
  it('counts down once per second', () => {
    render(<SubagentPromptButton />);
    setPrompt(true);

    elapse(999);
    expect(promptButton()).toHaveTextContent('(5s)');
    elapse(1);
    expect(promptButton()).toHaveTextContent('(4s)');
    countDown(3);
    expect(promptButton()).toHaveTextContent('(1s)');
  });

  it('keeps the button, without a countdown and without a running timer, after the countdown ended', () => {
    render(<SubagentPromptButton />);
    setPrompt(true);

    countDown(5);

    expect(promptButton()).toHaveTextContent(/^subagent\.viewResults$/);
    expect(vi.getTimerCount()).toBe(0);
    elapse(60_000);
    expect(promptButton()).toBeInTheDocument();
  });

  it('starts over each time the prompt reappears', () => {
    render(<SubagentPromptButton />);
    setPrompt(true);
    countDown(3);
    expect(promptButton()).toHaveTextContent('(2s)');

    setPrompt(false);
    setPrompt(true);

    expect(promptButton()).toHaveTextContent('(5s)');
  });

  it('leaves no timer behind when the prompt goes away or the component is removed', () => {
    const view = render(<SubagentPromptButton />);
    setPrompt(true);
    elapse(1000);
    expect(vi.getTimerCount()).toBe(1);

    setPrompt(false);
    expect(vi.getTimerCount()).toBe(0);

    setPrompt(true);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe('SubagentPromptButton asking for the results', () => {
  it('withdraws the prompt and its pending timer, then sends the localized request once', async () => {
    const seenWhenSent: boolean[] = [];
    sendMessage.mockImplementation(async () => {
      seenWhenSent.push(useChatStore.getState().subagentPromptVisible);
      return true;
    });
    render(<SubagentPromptButton />);
    act(() =>
      useChatStore.setState({
        subagentPromptVisible: true,
        subagentPromptTimer: setTimeout(() => undefined, 5000),
        subagentPromptMessageId: 'm1',
      }),
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button'));
    });

    expect(sendMessage).toHaveBeenCalledTimes(1);
    expect(sendMessage).toHaveBeenCalledWith('subagent.viewResults');
    expect(seenWhenSent).toEqual([false]);
    expect(useChatStore.getState()).toMatchObject({
      subagentPromptVisible: false,
      subagentPromptTimer: null,
      subagentPromptMessageId: null,
    });
    expect(promptButton()).toBeNull();
    expect(toast).not.toHaveBeenCalled();
  });

  it('tells the user when the request could not be sent, for instance while the agent is still busy', async () => {
    const busy = new Error('agent busy');
    sendMessage.mockRejectedValue(busy);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    render(<SubagentPromptButton />);
    setPrompt(true);

    await act(async () => {
      fireEvent.click(screen.getByRole('button'));
    });

    expect(warn).toHaveBeenCalledWith('Subagent results request was not sent:', busy);
    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith({ title: 'subagent.viewResultsFailed', variant: 'destructive' });
    expect(promptButton()).toBeNull();
  });

  it('adds no notice of its own when the store already reported a refused request', async () => {
    sendMessage.mockResolvedValue(false);
    render(<SubagentPromptButton />);
    setPrompt(true);

    await act(async () => {
      fireEvent.click(screen.getByRole('button'));
    });

    expect(sendMessage).toHaveBeenCalledTimes(1);
    expect(toast).not.toHaveBeenCalled();
  });
});
