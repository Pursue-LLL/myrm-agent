import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { elapse, startFakeClock, stopFakeClock } from '@/test-utils/fakeClock';
import { expectNonNull } from '@/test-utils/expectDefined';
import type { ManagedPolicyEffective } from '@/lib/managedPolicyMatch';
import type { SecurityConfigValue } from '@/services/config/types';
import type { DefaultModelConfig } from '@/store/config/providerTypes';
import useProviderStore from '@/store/useProviderStore';
import YoloModeBanner from '../YoloModeBanner';

const kit = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  const store: { config: SecurityConfigValue | null } = { config: null };
  const manager = {
    get: vi.fn(() => store.config),
    // Like the real manager: the value is cached, then every subscriber runs synchronously.
    set: vi.fn((_key: 'securityConfig', value: SecurityConfigValue) => {
      store.config = value;
      for (const listener of [...listeners]) {
        listener();
      }
    }),
    subscribe: vi.fn((_key: 'securityConfig', listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    }),
  };
  const managed: { policy: ManagedPolicyEffective; active: boolean } = { policy: {}, active: false };
  return { listeners, store, manager, managed };
});

vi.mock('@/services/config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/config')>()),
  getConfigSyncManager: () => kit.manager,
}));
vi.mock('@/hooks/useManagedPolicyEffective', () => ({ useManagedPolicyEffective: () => kit.managed }));

const nowSeconds = () => Math.floor(Date.now() / 1000);

function configure(yolo: Partial<SecurityConfigValue> | null): void {
  kit.store.config = yolo && { permissions: {}, approvalTimeoutSeconds: 60, ...yolo };
}

function currentConfig(): SecurityConfigValue {
  expectNonNull(kit.store.config, 'security configuration');
  return kit.store.config;
}

/** Turns the active model into `slug`, which is what the organization policy is matched against. */
function useModel(slug: string): void {
  const current = useProviderStore.getState().defaultModelConfig;
  const next: DefaultModelConfig = {
    ...current,
    baseModel: { primary: { providerId: 'p', model: slug }, fallback: null },
  };
  useProviderStore.setState({ defaultModelConfig: next });
}

const disabledConfig = {
  yoloModeEnabled: false,
  yoloModeTimeout: undefined,
  yoloModeEnabledAt: undefined,
};

beforeEach(() => {
  startFakeClock();
  vi.setSystemTime(new Date('2026-11-10T12:00:00Z'));
  kit.listeners.clear();
  kit.store.config = null;
  kit.managed.policy = {};
  kit.managed.active = false;
  useModel('some-model');
});

afterEach(() => {
  cleanup();
  stopFakeClock();
  vi.clearAllMocks();
});

const disableButton = () => screen.getByRole('button', { name: 'disable' });

describe('YoloModeBanner visibility', () => {
  it('shows nothing while YOLO is off', () => {
    configure({ yoloModeEnabled: false });
    const { container } = render(<YoloModeBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it('shows nothing when there is no security configuration at all', () => {
    const { container } = render(<YoloModeBanner />);

    expect(container).toBeEmptyDOMElement();
  });

  it('says that every tool is approved automatically while YOLO is on', () => {
    configure({ yoloModeEnabled: true });
    render(<YoloModeBanner />);

    expect(screen.getByText('message')).toBeInTheDocument();
    expect(disableButton()).toBeInTheDocument();
  });

  it('follows the configuration, appearing and disappearing as it changes', () => {
    configure({ yoloModeEnabled: false });
    const { container } = render(<YoloModeBanner />);

    act(() => kit.manager.set('securityConfig', { ...currentConfig(), yoloModeEnabled: true }));
    expect(screen.getByText('message')).toBeInTheDocument();

    act(() => kit.manager.set('securityConfig', { ...currentConfig(), yoloModeEnabled: false }));
    expect(container).toBeEmptyDOMElement();
  });

  it('stops listening when it goes away', () => {
    configure({ yoloModeEnabled: true });
    const { unmount } = render(<YoloModeBanner />);
    expect(kit.listeners.size).toBe(1);

    unmount();

    expect(kit.listeners.size).toBe(0);
  });
});

describe('YoloModeBanner countdown', () => {
  it('shows no countdown when YOLO has no time limit', () => {
    configure({ yoloModeEnabled: true });
    render(<YoloModeBanner />);

    expect(screen.getByText('message').textContent).toBe('message');
  });

  it.each([
    [59, '(59s)'],
    [60, '(1m 0s)'],
    [125, '(2m 5s)'],
    [3599, '(59m 59s)'],
    [3600, '(1h 0m)'],
    [3725, '(1h 2m)'],
    [5400, '(1h 30m)'],
  ])('writes %i seconds left as %s', (timeout, text) => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds(), yoloModeTimeout: timeout });
    render(<YoloModeBanner />);

    expect(screen.getByText(/message/)).toHaveTextContent(text);
  });

  it.each([
    ['a time limit of zero', { yoloModeEnabledAt: nowSeconds() - 5, yoloModeTimeout: 0 }],
    ['a start time of zero', { yoloModeEnabledAt: 0, yoloModeTimeout: 60 }],
    ['a time limit but no start time', { yoloModeTimeout: 60 }],
    ['a start time but no time limit', { yoloModeEnabledAt: nowSeconds() }],
  ])('counts nothing down and leaves YOLO on with %s', (_label, limit) => {
    configure({ yoloModeEnabled: true, ...limit });
    render(<YoloModeBanner />);

    expect(screen.getByText('message').textContent).toBe('message');
    expect(kit.manager.set).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('counts the time left from when YOLO was switched on', () => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds() - 40, yoloModeTimeout: 100 });
    render(<YoloModeBanner />);

    expect(screen.getByText(/message/)).toHaveTextContent('(1m 0s)');
  });

  it('counts whole seconds since YOLO was switched on, ignoring the fraction of a second', () => {
    vi.setSystemTime(new Date('2026-11-10T12:00:00.600Z'));
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds(), yoloModeTimeout: 60 });
    render(<YoloModeBanner />);

    expect(screen.getByText(/message/)).toHaveTextContent('(1m 0s)');
  });

  it('counts down every second', async () => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds(), yoloModeTimeout: 90 });
    render(<YoloModeBanner />);

    await elapse(1000);
    expect(screen.getByText(/message/)).toHaveTextContent('(1m 29s)');
    await elapse(29_000);
    expect(screen.getByText(/message/)).toHaveTextContent('(1m 0s)');
    await elapse(1000);
    expect(screen.getByText(/message/)).toHaveTextContent('(59s)');
  });

  it('restarts the countdown when the configuration gives YOLO a new time limit', async () => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds(), yoloModeTimeout: 100 });
    render(<YoloModeBanner />);
    await elapse(10_000);

    act(() =>
      kit.manager.set('securityConfig', {
        ...currentConfig(),
        yoloModeEnabledAt: nowSeconds(),
        yoloModeTimeout: 600,
      }),
    );

    expect(screen.getByText(/message/)).toHaveTextContent('(10m 0s)');
  });

  it('counts a new time limit from now even when the clock moved on while no limit was running', () => {
    configure({ yoloModeEnabled: true });
    render(<YoloModeBanner />);
    act(() => vi.setSystemTime(Date.now() + 30_000));

    act(() =>
      kit.manager.set('securityConfig', {
        ...currentConfig(),
        yoloModeEnabledAt: nowSeconds(),
        yoloModeTimeout: 600,
      }),
    );

    expect(screen.getByText(/message/)).toHaveTextContent('(10m 0s)');
  });

  it('switches YOLO off for good when the time is up', async () => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds(), yoloModeTimeout: 3 });
    const { container } = render(<YoloModeBanner />);

    await elapse(2000);
    expect(kit.manager.set).not.toHaveBeenCalled();
    await elapse(1000);

    expect(container).toBeEmptyDOMElement();
    expect(kit.manager.set).toHaveBeenCalledExactlyOnceWith('securityConfig', expect.objectContaining(disabledConfig));
    expect(kit.store.config).toMatchObject(disabledConfig);
  });

  it('switches YOLO off once even when several banners count the same limit down', async () => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds(), yoloModeTimeout: 2 });
    render(
      <>
        <YoloModeBanner />
        <YoloModeBanner />
      </>,
    );

    await elapse(2000);

    expect(kit.manager.set).toHaveBeenCalledTimes(1);
  });

  it('keeps no timer running once YOLO is off', async () => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds(), yoloModeTimeout: 3 });
    render(<YoloModeBanner />);
    await elapse(3000);

    await elapse(10_000);

    expect(kit.manager.set).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not run a timer when there is nothing to count down', () => {
    configure({ yoloModeEnabled: true });
    render(<YoloModeBanner />);

    expect(vi.getTimerCount()).toBe(0);
  });

  it('runs no timer for a time limit left over from an earlier session', () => {
    configure({ yoloModeEnabled: false, yoloModeEnabledAt: nowSeconds(), yoloModeTimeout: 60 });
    render(<YoloModeBanner />);

    expect(vi.getTimerCount()).toBe(0);
  });
});

describe('YoloModeBanner when the time was up before it appeared', () => {
  it('switches YOLO off at once instead of showing a banner with no time left', () => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds() - 100, yoloModeTimeout: 60 });
    const { container } = render(<YoloModeBanner />);

    expect(container).toBeEmptyDOMElement();
    expect(kit.store.config).toMatchObject(disabledConfig);
  });
});

describe('YoloModeBanner when the browser slows its timers', () => {
  it('shows the real time left after a long pause, not one second less than before', async () => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds(), yoloModeTimeout: 600 });
    render(<YoloModeBanner />);

    act(() => vi.setSystemTime(Date.now() + 300_000));
    await elapse(1000);

    expect(screen.getByText(/message/)).toHaveTextContent('(4m 59s)');
  });

  it('switches YOLO off when the pause outlasted the time that was left', async () => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds(), yoloModeTimeout: 60 });
    const { container } = render(<YoloModeBanner />);

    act(() => vi.setSystemTime(Date.now() + 600_000));
    await elapse(1000);

    expect(container).toBeEmptyDOMElement();
    expect(kit.store.config).toMatchObject(disabledConfig);
  });
});

describe('YoloModeBanner in strict mode', () => {
  it('switches YOLO off once when the time was already up, however often React replays its effects', () => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds() - 100, yoloModeTimeout: 60 });
    render(
      <StrictMode>
        <YoloModeBanner />
      </StrictMode>,
    );

    expect(kit.manager.set).toHaveBeenCalledTimes(1);
  });

  it('switches YOLO off once, however often React replays its updates', async () => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds(), yoloModeTimeout: 2 });
    render(
      <StrictMode>
        <YoloModeBanner />
      </StrictMode>,
    );

    await elapse(2000);

    expect(kit.manager.set).toHaveBeenCalledTimes(1);
  });
});

describe('YoloModeBanner Disable button', () => {
  it('switches YOLO off, clears its time limit and hides the banner', () => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds(), yoloModeTimeout: 600 });
    const { container } = render(<YoloModeBanner />);

    fireEvent.click(disableButton());

    expect(container).toBeEmptyDOMElement();
    expect(kit.manager.set).toHaveBeenCalledExactlyOnceWith('securityConfig', expect.objectContaining(disabledConfig));
    expect(vi.getTimerCount()).toBe(0);
  });

  it('keeps the rest of the security configuration as it was', () => {
    configure({ yoloModeEnabled: true, approvalTimeoutSeconds: 123, networkBlocklist: ['bad.example'] });
    render(<YoloModeBanner />);

    fireEvent.click(disableButton());

    expect(kit.store.config).toMatchObject({ approvalTimeoutSeconds: 123, networkBlocklist: ['bad.example'] });
  });
});

describe('YoloModeBanner under an organization policy', () => {
  const amber = (container: HTMLElement) => container.firstElementChild;

  it('says so when the organization has turned YOLO off everywhere', () => {
    configure({ yoloModeEnabled: true });
    kit.managed.active = true;
    kit.managed.policy = { disableYolo: true };
    const { container } = render(<YoloModeBanner />);

    expect(screen.getByText('orgGlobalDisabledMessage')).toBeInTheDocument();
    expect(amber(container)).toHaveClass('bg-amber-500/15');
    expect(container.querySelector('.lucide-zap')).toBeNull();
  });

  it('says so when the policy still asks for approval for the model in use', () => {
    configure({ yoloModeEnabled: true });
    kit.managed.active = true;
    kit.managed.policy = { forceAutoReviewForModels: ['gpt-*'] };
    useModel('gpt-5');
    const { container } = render(<YoloModeBanner />);

    expect(screen.getByText('orgConstrainedMessage')).toBeInTheDocument();
    expect(amber(container)).toHaveClass('bg-amber-500/15');
    expect(container.querySelector('.lucide-zap')).toBeNull();
  });

  it('also applies a policy that ignores the allowlist for that model', () => {
    configure({ yoloModeEnabled: true });
    kit.managed.active = true;
    kit.managed.policy = { ignoreAllowlistForModels: ['claude-*'] };
    useModel('claude-sonnet');
    render(<YoloModeBanner />);

    expect(screen.getByText('orgConstrainedMessage')).toBeInTheDocument();
  });

  it('leaves the message alone for a model the policy does not name', () => {
    configure({ yoloModeEnabled: true });
    kit.managed.active = true;
    kit.managed.policy = { forceAutoReviewForModels: ['gpt-*'] };
    useModel('claude-sonnet');
    const { container } = render(<YoloModeBanner />);

    expect(screen.getByText('message')).toBeInTheDocument();
    expect(amber(container)).toHaveClass('bg-amber-500/10');
    expect(container.querySelector('.lucide-zap')).not.toBeNull();
  });

  it('ignores a policy that is not in force', () => {
    configure({ yoloModeEnabled: true });
    kit.managed.active = false;
    kit.managed.policy = { disableYolo: true, forceAutoReviewForModels: ['*'] };
    render(<YoloModeBanner />);

    expect(screen.getByText('message')).toBeInTheDocument();
  });

  it('keeps the countdown next to the policy message', () => {
    configure({ yoloModeEnabled: true, yoloModeEnabledAt: nowSeconds(), yoloModeTimeout: 30 });
    kit.managed.active = true;
    kit.managed.policy = { disableYolo: true };
    render(<YoloModeBanner />);

    expect(screen.getByText(/orgGlobalDisabledMessage/)).toHaveTextContent('(30s)');
  });
});
