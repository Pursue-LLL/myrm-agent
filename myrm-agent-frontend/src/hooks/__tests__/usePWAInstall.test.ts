import { renderHook, act } from '@testing-library/react';
import { usePWAInstall } from '../usePWAInstall';

describe('usePWAInstall', () => {
  let originalWindow: Window & typeof globalThis;

  beforeEach(() => {
    originalWindow = global.window;
    // Mock matchMedia
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(), // deprecated
        removeListener: vi.fn(), // deprecated
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  afterEach(() => {
    global.window = originalWindow;
    vi.restoreAllMocks();
  });

  it('should initialize with isInstallable false', () => {
    const { result } = renderHook(() => usePWAInstall());
    expect(result.current.isInstallable).toBe(false);
    expect(result.current.isInstalled).toBe(false);
  });

  it('should become installable when beforeinstallprompt is fired', () => {
    const { result } = renderHook(() => usePWAInstall());

    act(() => {
      const event = new Event('beforeinstallprompt') as any;
      event.preventDefault = vi.fn();
      window.dispatchEvent(event);
    });

    expect(result.current.isInstallable).toBe(true);
  });

  it('should handle appinstalled event', () => {
    const { result } = renderHook(() => usePWAInstall());

    act(() => {
      const event = new Event('appinstalled');
      window.dispatchEvent(event);
    });

    expect(result.current.isInstallable).toBe(false);
    expect(result.current.isInstalled).toBe(true);
  });

  it('should not be installable in Tauri mode', () => {
    // Mock Tauri environment
    (window as any).__TAURI_INTERNALS__ = {};

    const { result } = renderHook(() => usePWAInstall());

    act(() => {
      const event = new Event('beforeinstallprompt') as any;
      event.preventDefault = vi.fn();
      window.dispatchEvent(event);
    });

    // Should remain false because the listener shouldn't be attached
    expect(result.current.isInstallable).toBe(false);

    // Cleanup
    delete (window as any).__TAURI_INTERNALS__;
  });
});
