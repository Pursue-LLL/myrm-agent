/**
 * The voice session switches as a user meets them: they show what is saved, save what is clicked, and keep
 * working for the page when the browser refuses to store anything.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { VOICE_SETTING_KEYS, voiceDeviceSettings } from '@/hooks/voice/voiceDeviceSettings';
import VoiceSessionToggles from '../VoiceSessionToggles';

vi.mock('next-intl', () => {
  const t = (key: string) => key;
  return { useTranslations: () => t };
});

/** The switches in the order the card lists them. */
const SWITCH_KEYS = [
  VOICE_SETTING_KEYS.sessionEnabled,
  VOICE_SETTING_KEYS.fullDuplex,
  VOICE_SETTING_KEYS.agentBridge,
] as const;

function switchStates(): boolean[] {
  return screen.getAllByRole('switch').map((toggle) => toggle.getAttribute('aria-checked') === 'true');
}

function switchFor(key: (typeof SWITCH_KEYS)[number]): HTMLElement {
  return screen.getAllByRole('switch')[SWITCH_KEYS.indexOf(key)];
}

describe('VoiceSessionToggles', () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    for (const key of Object.values(VOICE_SETTING_KEYS)) {
      voiceDeviceSettings.remove(key);
    }
    localStorage.clear();
  });

  it('shows voice off and full duplex on when nothing is saved', () => {
    render(<VoiceSessionToggles />);

    expect(switchStates()).toEqual([false, true, false]);
  });

  it('shows what is saved', () => {
    localStorage.setItem(VOICE_SETTING_KEYS.sessionEnabled, 'true');
    localStorage.setItem(VOICE_SETTING_KEYS.fullDuplex, 'false');
    localStorage.setItem(VOICE_SETTING_KEYS.agentBridge, 'true');

    render(<VoiceSessionToggles />);

    expect(switchStates()).toEqual([true, false, true]);
  });

  it('renders the defaults on the server, whatever is stored on this device', () => {
    for (const key of SWITCH_KEYS) {
      localStorage.setItem(key, key === VOICE_SETTING_KEYS.fullDuplex ? 'false' : 'true');
    }
    const host = document.createElement('div');

    host.innerHTML = renderToString(<VoiceSessionToggles />);

    const states = [...host.querySelectorAll('[role="switch"]')].map(
      (toggle) => toggle.getAttribute('aria-checked') === 'true',
    );
    expect(states).toEqual([false, true, false]);
  });

  it('saves the switch that is clicked, in both directions', () => {
    render(<VoiceSessionToggles />);

    fireEvent.click(switchFor(VOICE_SETTING_KEYS.agentBridge));
    expect(localStorage.getItem(VOICE_SETTING_KEYS.agentBridge)).toBe('true');
    expect(switchStates()).toEqual([false, true, true]);

    fireEvent.click(switchFor(VOICE_SETTING_KEYS.agentBridge));
    expect(localStorage.getItem(VOICE_SETTING_KEYS.agentBridge)).toBe('false');
    expect(switchStates()).toEqual([false, true, false]);
  });

  it('turns full duplex off and back on', () => {
    render(<VoiceSessionToggles />);

    fireEvent.click(switchFor(VOICE_SETTING_KEYS.fullDuplex));
    expect(localStorage.getItem(VOICE_SETTING_KEYS.fullDuplex)).toBe('false');

    fireEvent.click(switchFor(VOICE_SETTING_KEYS.fullDuplex));
    expect(localStorage.getItem(VOICE_SETTING_KEYS.fullDuplex)).toBe('true');
  });

  it('keeps working for the page when the browser refuses to store anything', () => {
    const refuse = () => {
      throw new DOMException('blocked', 'SecurityError');
    };
    vi.stubGlobal('localStorage', { getItem: refuse, setItem: refuse, removeItem: refuse });

    render(<VoiceSessionToggles />);
    expect(switchStates()).toEqual([false, true, false]);

    fireEvent.click(switchFor(VOICE_SETTING_KEYS.sessionEnabled));

    expect(switchStates()).toEqual([true, true, false]);
    // What the chat's voice button reads, so the choice takes effect there too.
    expect(voiceDeviceSettings.read(VOICE_SETTING_KEYS.sessionEnabled)).toBe('true');
  });

  it('follows a change made elsewhere on the page', () => {
    render(<VoiceSessionToggles />);

    act(() => {
      voiceDeviceSettings.write(VOICE_SETTING_KEYS.agentBridge, 'true');
    });

    expect(switchStates()).toEqual([false, true, true]);
  });

  it('stops listening once it is gone', () => {
    const { unmount } = render(<VoiceSessionToggles />);
    const removed = vi.spyOn(window, 'removeEventListener');

    unmount();

    expect(removed.mock.calls.map(([type]) => type)).toContain('storage');
    removed.mockRestore();
  });
});
