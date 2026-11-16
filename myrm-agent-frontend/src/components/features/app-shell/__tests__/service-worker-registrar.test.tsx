/** @vitest-environment jsdom */
import { render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ServiceWorkerRegistrar, unregisterServiceWorkers } from '../service-worker-registrar';

type TauriWindow = Window & { __TAURI_INTERNALS__?: unknown };

interface ServiceWorkerContainerStub {
  register: ReturnType<typeof vi.fn>;
  getRegistrations: ReturnType<typeof vi.fn>;
}

function installServiceWorkerContainer(
  overrides: Partial<ServiceWorkerContainerStub> = {},
): ServiceWorkerContainerStub {
  const container: ServiceWorkerContainerStub = {
    register: vi.fn().mockResolvedValue({}),
    getRegistrations: vi.fn().mockResolvedValue([]),
    ...overrides,
  };
  Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: container });
  return container;
}

describe('unregisterServiceWorkers', () => {
  it('unregisters every existing development registration', async () => {
    const firstUnregister = vi.fn().mockResolvedValue(true);
    const secondUnregister = vi.fn().mockResolvedValue(true);
    const container = {
      getRegistrations: vi.fn().mockResolvedValue([{ unregister: firstUnregister }, { unregister: secondUnregister }]),
    } as unknown as ServiceWorkerContainer;

    await unregisterServiceWorkers(container);

    expect(container.getRegistrations).toHaveBeenCalledTimes(1);
    expect(firstUnregister).toHaveBeenCalledTimes(1);
    expect(secondUnregister).toHaveBeenCalledTimes(1);
  });

  it('handles an empty registration list', async () => {
    const container = {
      getRegistrations: vi.fn().mockResolvedValue([]),
    } as unknown as ServiceWorkerContainer;

    await expect(unregisterServiceWorkers(container)).resolves.toBeUndefined();
  });
});

describe('ServiceWorkerRegistrar', () => {
  afterEach(() => {
    Reflect.deleteProperty(navigator, 'serviceWorker');
    delete (window as TauriWindow).__TAURI_INTERNALS__;
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it('registers the Web Push worker at /sw.js with the default scope in production and renders nothing', () => {
    vi.stubEnv('NODE_ENV', 'production');
    const container = installServiceWorkerContainer();

    const { container: markup } = render(<ServiceWorkerRegistrar />);

    expect(container.register).toHaveBeenCalledExactlyOnceWith('/sw.js');
    expect(container.getRegistrations).not.toHaveBeenCalled();
    expect(markup.innerHTML).toBe('');
  });

  it('logs a failed registration instead of throwing', async () => {
    vi.stubEnv('NODE_ENV', 'production');
    const failure = new Error('script fetch failed');
    installServiceWorkerContainer({ register: vi.fn().mockRejectedValue(failure) });
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    render(<ServiceWorkerRegistrar />);

    await vi.waitFor(() =>
      expect(warn).toHaveBeenCalledExactlyOnceWith('[PWA] ServiceWorker registration failed:', failure),
    );
  });

  it('unregisters leftover workers in development and registers none', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    const unregister = vi.fn().mockResolvedValue(true);
    const container = installServiceWorkerContainer({
      getRegistrations: vi.fn().mockResolvedValue([{ unregister }]),
    });

    render(<ServiceWorkerRegistrar />);

    await vi.waitFor(() => expect(unregister).toHaveBeenCalledTimes(1));
    expect(container.register).not.toHaveBeenCalled();
  });

  it('logs a failed development cleanup instead of throwing', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    const failure = new Error('registrations unavailable');
    installServiceWorkerContainer({ getRegistrations: vi.fn().mockRejectedValue(failure) });
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    render(<ServiceWorkerRegistrar />);

    await vi.waitFor(() =>
      expect(warn).toHaveBeenCalledExactlyOnceWith('[PWA] Failed to unregister development ServiceWorker:', failure),
    );
  });

  it('leaves service workers alone inside the Tauri shell', () => {
    vi.stubEnv('NODE_ENV', 'production');
    (window as TauriWindow).__TAURI_INTERNALS__ = {};
    const container = installServiceWorkerContainer();

    render(<ServiceWorkerRegistrar />);

    expect(container.register).not.toHaveBeenCalled();
    expect(container.getRegistrations).not.toHaveBeenCalled();
  });

  it('does nothing where the browser has no service worker support', () => {
    vi.stubEnv('NODE_ENV', 'production');

    expect(() => render(<ServiceWorkerRegistrar />)).not.toThrow();
  });
});
