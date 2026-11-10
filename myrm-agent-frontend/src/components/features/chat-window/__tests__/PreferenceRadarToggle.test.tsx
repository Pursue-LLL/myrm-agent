/** @vitest-environment jsdom */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { PreferenceRadarStateResponse, PreferenceRadarTuneRequest } from '@/services/memory/preferences';
import { deferred } from '@/test-utils/deferred';

import { PreferenceRadarToggle } from '../PreferenceRadarToggle';

const kit = vi.hoisted(() => ({
  getState: vi.fn<(sessionId: string) => Promise<unknown>>(),
  tune: vi.fn<(sessionId: string, request: PreferenceRadarTuneRequest) => Promise<unknown>>(),
}));

vi.mock('@/services/memory/preferences', () => ({
  getPreferenceRadarState: kit.getState,
  tunePreferenceRadar: kit.tune,
}));

const radarState = (overrides: Partial<PreferenceRadarStateResponse> = {}): PreferenceRadarStateResponse => ({
  session_id: 'chat-1',
  recency: 1,
  actionability: 1,
  technical_depth: 1,
  conciseness: 1,
  breadth: 1,
  locked: false,
  last_updated: '2026-03-15T12:00:00Z',
  effective_signal_weights: {},
  ...overrides,
});

const DIMENSIONS = ['recency', 'actionability', 'technical_depth', 'conciseness', 'breadth'];

const toggleButton = () => screen.getByTestId('preference-radar-toggle-button');
const drawer = () => screen.queryByTestId('preference-radar-drawer');
const slider = (dimension: string) => screen.getByTestId(`slider-${dimension}`) as HTMLInputElement;

async function open() {
  await act(async () => fireEvent.click(toggleButton()));
}

async function close() {
  await act(async () => fireEvent.click(toggleButton()));
}

const move = (dimension: string, value: number) =>
  act(async () => fireEvent.change(slider(dimension), { target: { value: String(value) } }));

beforeEach(() => {
  vi.resetAllMocks();
  kit.getState.mockResolvedValue(radarState());
  kit.tune.mockResolvedValue(radarState());
});

describe('PreferenceRadarToggle', () => {
  it('offers the button with its labels and asks nothing while the drawer is closed', () => {
    render(<PreferenceRadarToggle chatId="chat-1" />);

    expect(toggleButton()).toHaveAttribute('title', 'title');
    expect(toggleButton()).toHaveAttribute('aria-label', 'ariaLabel');
    expect(drawer()).toBeNull();
    expect(kit.getState).not.toHaveBeenCalled();
  });

  it('opens and closes the drawer with the button and its close button', async () => {
    render(<PreferenceRadarToggle chatId="chat-1" />);

    await open();
    expect(drawer()).toBeInTheDocument();

    await close();
    expect(drawer()).toBeNull();

    await open();
    await act(async () => fireEvent.click(screen.getByTestId('radar-close-button')));
    expect(drawer()).toBeNull();
  });

  it('shows what the server holds for this session each time the drawer opens', async () => {
    kit.getState.mockResolvedValueOnce(
      radarState({
        recency: 1.5,
        actionability: 0.6,
        technical_depth: 2.1,
        conciseness: 0.9,
        breadth: 2.7,
        locked: true,
      }),
    );
    render(<PreferenceRadarToggle chatId="chat-1" />);

    await open();

    expect(kit.getState).toHaveBeenCalledExactlyOnceWith('chat-1');
    expect(DIMENSIONS.map((dimension) => slider(dimension).value)).toEqual(['1.5', '0.6', '2.1', '0.9', '2.7']);
    expect(screen.getByText('1.50x')).toBeInTheDocument();
    expect(screen.getByText('lockedLabel')).toBeInTheDocument();

    await close();
    kit.getState.mockResolvedValueOnce(radarState({ recency: 2.25, locked: false }));
    await open();

    expect(kit.getState).toHaveBeenCalledTimes(2);
    expect(slider('recency').value).toBe('2.25');
    expect(screen.getByText('adaptiveLabel')).toBeInTheDocument();
  });

  it('shows neutral weights and stays usable when the state cannot be read', async () => {
    kit.getState.mockRejectedValue(new Error('offline'));
    render(<PreferenceRadarToggle chatId="chat-1" />);

    await open();

    expect(drawer()).toBeInTheDocument();
    expect(DIMENSIONS.map((dimension) => slider(dimension).value)).toEqual(['1', '1', '1', '1', '1']);
  });

  it('applies a moved weight at once and sends only that weight', async () => {
    render(<PreferenceRadarToggle chatId="chat-1" />);
    await open();

    await move('breadth', 2.5);

    expect(slider('breadth').value).toBe('2.5');
    expect(kit.tune).toHaveBeenCalledExactlyOnceWith('chat-1', { breadth: 2.5 });
  });

  it('keeps the other weights when one moves', async () => {
    kit.getState.mockResolvedValue(radarState({ recency: 2, breadth: 0.5 }));
    render(<PreferenceRadarToggle chatId="chat-1" />);
    await open();

    await move('conciseness', 1.8);

    expect(slider('recency').value).toBe('2');
    expect(slider('breadth').value).toBe('0.5');
    expect(slider('conciseness').value).toBe('1.8');
  });

  it('locks and unlocks the radar', async () => {
    render(<PreferenceRadarToggle chatId="chat-1" />);
    await open();

    await act(async () => fireEvent.click(screen.getByTestId('radar-toggle-lock')));
    expect(screen.getByText('lockedLabel')).toBeInTheDocument();
    expect(kit.tune).toHaveBeenLastCalledWith('chat-1', { locked: true });

    await act(async () => fireEvent.click(screen.getByTestId('radar-toggle-lock')));
    expect(screen.getByText('adaptiveLabel')).toBeInTheDocument();
    expect(kit.tune).toHaveBeenLastCalledWith('chat-1', { locked: false });
  });

  it('resets every weight to neutral', async () => {
    kit.getState.mockResolvedValue(radarState({ recency: 2, actionability: 0.5, breadth: 3 }));
    render(<PreferenceRadarToggle chatId="chat-1" />);
    await open();

    await act(async () => fireEvent.click(screen.getByTestId('radar-reset-button')));

    expect(DIMENSIONS.map((dimension) => slider(dimension).value)).toEqual(['1', '1', '1', '1', '1']);
    expect(kit.tune).toHaveBeenCalledExactlyOnceWith('chat-1', { reset_to_neutral: true });
  });

  it('applies a preset as a whole', async () => {
    render(<PreferenceRadarToggle chatId="chat-1" />);
    await open();

    await act(async () => fireEvent.click(screen.getByTestId('preset-code')));

    expect(slider('actionability').value).toBe('2.5');
    expect(slider('breadth').value).toBe('0.5');
    expect(kit.tune).toHaveBeenCalledExactlyOnceWith('chat-1', {
      recency: 1.5,
      actionability: 2.5,
      technical_depth: 2,
      conciseness: 1.8,
      breadth: 0.5,
    });
  });

  it('shows what the server really holds again when a change was not saved', async () => {
    kit.getState.mockResolvedValue(radarState({ recency: 1.2 }));
    render(<PreferenceRadarToggle chatId="chat-1" />);
    await open();
    kit.tune.mockRejectedValueOnce(new Error('rejected'));

    await move('recency', 2.8);

    expect(kit.getState).toHaveBeenCalledTimes(2);
    expect(slider('recency').value).toBe('1.2');
  });

  it('keeps a later change when the server answers an older request', async () => {
    const opening = deferred<unknown>();
    kit.getState.mockReturnValueOnce(opening.promise);
    render(<PreferenceRadarToggle chatId="chat-1" />);
    await open();

    await move('recency', 2.6);
    await act(async () => opening.resolve(radarState({ recency: 1.1, breadth: 0.4 })));

    expect(slider('recency').value).toBe('2.6');
    expect(slider('breadth').value).toBe('1');
  });

  it("does not show the previous session's radar for the next one", async () => {
    kit.getState.mockResolvedValue(radarState({ recency: 2.4, locked: true }));
    const { rerender } = render(<PreferenceRadarToggle chatId="chat-a" />);
    await open();
    expect(slider('recency').value).toBe('2.4');

    const pending = deferred<unknown>();
    kit.getState.mockReturnValueOnce(pending.promise);
    rerender(<PreferenceRadarToggle chatId="chat-b" />);
    expect(drawer()).toBeNull();
    await open();

    expect(slider('recency').value).toBe('1');
    expect(screen.getByText('adaptiveLabel')).toBeInTheDocument();
    await act(async () => pending.resolve(radarState({ recency: 0.7 })));
    expect(slider('recency').value).toBe('0.7');
    expect(kit.getState.mock.calls).toEqual([['chat-a'], ['chat-b']]);
  });

  it('drops the answer for a session the user has left', async () => {
    const slow = deferred<unknown>();
    kit.getState.mockReturnValueOnce(slow.promise);
    const { rerender } = render(<PreferenceRadarToggle chatId="chat-a" />);
    await open();

    rerender(<PreferenceRadarToggle chatId="chat-b" />);
    await open();
    await act(async () => slow.resolve(radarState({ recency: 2.9 })));

    expect(slider('recency').value).toBe('1');
  });

  it('tunes the session of the chat on screen', async () => {
    const { rerender } = render(<PreferenceRadarToggle chatId="chat-a" />);
    rerender(<PreferenceRadarToggle chatId="chat-b" />);
    await open();

    await move('recency', 2);

    expect(kit.tune).toHaveBeenCalledExactlyOnceWith('chat-b', { recency: 2 });
  });

  it.each([
    [undefined, 'default'],
    ['', 'default'],
    ['   ', 'default'],
    ['  chat-9 ', 'chat-9'],
  ])('uses the session %j as %j', async (chatId, expected) => {
    render(<PreferenceRadarToggle chatId={chatId} />);

    await open();

    expect(kit.getState).toHaveBeenCalledExactlyOnceWith(expected);
  });

  it('passes the class name on to the button wrapper', () => {
    const { container } = render(<PreferenceRadarToggle chatId="chat-1" className="custom-spot" />);

    expect(container.querySelector('.custom-spot')).toContainElement(toggleButton());
  });
});
