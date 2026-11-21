import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import type { TTSState } from '../tts/types';
import { useTTS } from '../useTTS';

const mocks = vi.hoisted(() => ({ useBrowserTTS: vi.fn(), useApiTTS: vi.fn() }));

vi.mock('../tts/useBrowserTTS', () => ({ useBrowserTTS: mocks.useBrowserTTS }));
vi.mock('../tts/useApiTTS', () => ({ useApiTTS: mocks.useApiTTS }));

const makeEngine = (state: TTSState = 'idle') => ({
  state,
  speak: vi.fn(),
  pause: vi.fn(),
  resume: vi.fn(),
  stop: vi.fn(),
  supported: true,
});

let browser: ReturnType<typeof makeEngine>;
let api: ReturnType<typeof makeEngine>;

beforeEach(() => {
  browser = makeEngine();
  api = makeEngine();
  mocks.useBrowserTTS.mockReset().mockReturnValue(browser);
  mocks.useApiTTS.mockReset().mockReturnValue(api);
});

describe('useTTS', () => {
  describe('engine selection', () => {
    it('exposes the browser engine by default', () => {
      const { result } = renderHook(() => useTTS());

      expect(result.current.speak).toBe(browser.speak);
      expect(result.current.stop).toBe(browser.stop);
    });

    it('exposes the API engine in api mode and hands it the provider', () => {
      const { result } = renderHook(() => useTTS({ mode: 'api', provider: 'openai' }));

      expect(result.current.speak).toBe(api.speak);
      expect(mocks.useApiTTS).toHaveBeenCalledWith(expect.objectContaining({ provider: 'openai' }));
    });

    it('keeps running both engines whichever one is exposed', () => {
      renderHook(() => useTTS({ mode: 'api' }));

      expect(mocks.useBrowserTTS).toHaveBeenCalled();
      expect(mocks.useApiTTS).toHaveBeenCalled();
    });
  });

  describe('toggle', () => {
    it('speaks the text while idle', () => {
      const { result } = renderHook(() => useTTS());

      result.current.toggle('hello');

      expect(browser.speak).toHaveBeenCalledWith('hello');
      expect(browser.pause).not.toHaveBeenCalled();
      expect(browser.resume).not.toHaveBeenCalled();
    });

    it('pauses while playing', () => {
      browser.state = 'playing';
      const { result } = renderHook(() => useTTS());

      result.current.toggle('hello');

      expect(browser.pause).toHaveBeenCalledTimes(1);
      expect(browser.speak).not.toHaveBeenCalled();
    });

    it('resumes while paused', () => {
      browser.state = 'paused';
      const { result } = renderHook(() => useTTS());

      result.current.toggle('hello');

      expect(browser.resume).toHaveBeenCalledTimes(1);
      expect(browser.speak).not.toHaveBeenCalled();
    });

    it('drives the exposed engine only', () => {
      api.state = 'playing';
      const { result } = renderHook(() => useTTS({ mode: 'api' }));

      result.current.toggle('hello');

      expect(api.pause).toHaveBeenCalledTimes(1);
      expect(browser.pause).not.toHaveBeenCalled();
    });
  });
});
