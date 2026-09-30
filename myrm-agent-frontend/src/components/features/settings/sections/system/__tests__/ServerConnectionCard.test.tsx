import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ServerConnectionCard from '../ServerConnectionCard';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: string[]) => args.filter(Boolean).join(' '),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe('ServerConnectionCard switch guard', () => {
  it('blocks switching to a dead server and forces on repeat', async () => {
    const testing = await import('@testing-library/react');
    const { toast } = await import('@/lib/utils/toast');
    vi.clearAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    localStorage.clear();
    localStorage.setItem('myrm-remote-first-run-seen', '1');
    localStorage.setItem(
      'myrm-remote-gateway-roster',
      JSON.stringify({
        profiles: [{ id: 'p1', name: 'Pi', url: 'http://127.0.0.1:9', kind: 'server' }],
        activeId: null,
      }),
    );

    vi.resetModules();
    vi.doMock('@/lib/deploy-mode', async (importOriginal) => {
      const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
      return { ...actual, isTauriRuntime: () => true };
    });
    const { default: TauriCard } = await import('../ServerConnectionCard');
    const { unmount } = testing.render(<TauriCard />);

    // Card boots in local mode; flip to remote so the profile list renders.
    testing.fireEvent.click(testing.screen.getByLabelText('modeLocal'));
    testing.fireEvent.click((await testing.screen.findAllByText('save'))[0]);
    await testing.waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith('gateFailed');
    });
    // Still local: no pending switch committed.
    expect(localStorage.getItem('myrm-connection-pending-switch')).toBeNull();

    // Second click on the same dead URL forces the switch.
    testing.fireEvent.click(testing.screen.getAllByText('save')[0]);
    await testing.waitFor(() => {
      expect(localStorage.getItem('myrm-connection-pending-switch')).not.toBeNull();
    });
    unmount();
    vi.doUnmock('@/lib/deploy-mode');
    vi.unstubAllGlobals();
  });

  it('switches to a cloud profile without probing and shows busy state', async () => {
    const testing = await import('@testing-library/react');
    const { toast } = await import('@/lib/utils/toast');
    vi.clearAllMocks();
    // Even a dead network must not block cloud profiles (OAuth-verified).
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    localStorage.clear();
    localStorage.setItem('myrm-remote-first-run-seen', '1');
    localStorage.setItem(
      'myrm-remote-gateway-roster',
      JSON.stringify({
        profiles: [
          { id: 'p0', name: 'Local Pi', url: 'http://127.0.0.1:9', kind: 'server' },
          {
            id: 'c1',
            name: 'Cloud',
            url: 'https://cp.example/proxy/me',
            kind: 'cloud',
            cpBaseUrl: 'https://cp.example',
          },
        ],
        activeId: 'p0',
      }),
    );

    vi.resetModules();
    vi.doMock('@/lib/deploy-mode', async (importOriginal) => {
      const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
      return { ...actual, isTauriRuntime: () => true };
    });
    const { default: TauriCard } = await import('../ServerConnectionCard');
    const { unmount } = testing.render(<TauriCard />);

    // Boots remote (p0 active); the only save button belongs to the cloud profile.
    testing.fireEvent.click((await testing.screen.findAllByText('save'))[0]);
    // Single click connects: no gate failure, pending stays empty.
    await testing.waitFor(() => {
      expect(vi.mocked(toast.success)).toHaveBeenCalledWith('connected');
    });
    expect(vi.mocked(toast.error)).not.toHaveBeenCalledWith('gateFailed');
    expect(localStorage.getItem('myrm-connection-pending-switch')).toBeNull();
    const roster = JSON.parse(localStorage.getItem('myrm-remote-gateway-roster') ?? '{}');
    expect(roster.activeId).toBe('c1');
    expect(roster.profiles).toHaveLength(2);
    unmount();
    vi.doUnmock('@/lib/deploy-mode');
    vi.unstubAllGlobals();
  });

  it('disables the switch button while probing', async () => {
    const testing = await import('@testing-library/react');
    let resolveProbe: (value: Response) => void = () => {};
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        () =>
          new Promise<Response>((resolve) => {
            resolveProbe = resolve;
          }),
      ),
    );
    localStorage.clear();
    localStorage.setItem('myrm-remote-first-run-seen', '1');
    localStorage.setItem(
      'myrm-remote-gateway-roster',
      JSON.stringify({
        profiles: [{ id: 'p1', name: 'Pi', url: 'http://127.0.0.1:9', kind: 'server' }],
        activeId: null,
      }),
    );

    vi.resetModules();
    vi.doMock('@/lib/deploy-mode', async (importOriginal) => {
      const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
      return { ...actual, isTauriRuntime: () => true };
    });
    const { default: TauriCard } = await import('../ServerConnectionCard');
    const { unmount } = testing.render(<TauriCard />);

    testing.fireEvent.click(testing.screen.getByLabelText('modeLocal'));
    testing.fireEvent.click((await testing.screen.findAllByText('save'))[0]);
    // Probe in flight: button shows testing state and is disabled.
    const busy = await testing.screen.findByText('testing');
    expect((busy as HTMLButtonElement).disabled).toBe(true);
    resolveProbe(new Response('{}', { status: 200 }));
    await testing.waitFor(() => {
      expect(localStorage.getItem('myrm-connection-pending-switch')).not.toBeNull();
    });
    unmount();
    vi.doUnmock('@/lib/deploy-mode');
    vi.unstubAllGlobals();
  });

  it('rolls a dead switch back to a cloud profile by id without junk profiles', async () => {
    const testing = await import('@testing-library/react');
    const { toast } = await import('@/lib/utils/toast');
    vi.clearAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    localStorage.clear();
    localStorage.setItem('myrm-remote-first-run-seen', '1');
    localStorage.setItem(
      'myrm-remote-gateway-roster',
      JSON.stringify({
        profiles: [
          { id: 'c1', name: 'Cloud', url: 'cloud-slot', kind: 'cloud', cpBaseUrl: 'https://cp.example' },
          { id: 'p2', name: 'Pi', url: 'http://127.0.0.1:9', kind: 'server' },
        ],
        activeId: 'p2',
      }),
    );
    localStorage.setItem(
      'myrm-connection-pending-switch',
      JSON.stringify({ url: 'http://127.0.0.1:9', at: Date.now() }),
    );
    localStorage.setItem(
      'myrm-connection-last-good',
      JSON.stringify({ activeId: 'c1', url: 'https://cp.example/proxy/me' }),
    );

    vi.resetModules();
    vi.doMock('@/lib/deploy-mode', async (importOriginal) => {
      const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
      return { ...actual, isTauriRuntime: () => true };
    });
    const { default: TauriCard } = await import('../ServerConnectionCard');
    const { unmount } = testing.render(<TauriCard />);

    await testing.waitFor(() => {
      expect(vi.mocked(toast.error)).toHaveBeenCalledWith('restoredLastGood');
    });
    const roster = JSON.parse(localStorage.getItem('myrm-remote-gateway-roster') ?? '{}');
    // Restored to the cloud profile, and no duplicate was written.
    expect(roster.activeId).toBe('c1');
    expect(roster.profiles).toHaveLength(2);
    expect(localStorage.getItem('myrm-connection-pending-switch')).toBeNull();
    unmount();
    vi.doUnmock('@/lib/deploy-mode');
    vi.unstubAllGlobals();
  });
});

describe('ServerConnectionCard runtime gating', () => {
  it('renders nothing outside Tauri so web users never see the desktop card', () => {
    const { container } = render(<ServerConnectionCard />);
    expect(container.firstChild).toBeNull();
    expect(screen.queryByText('title')).toBeNull();
  });

  it('renders the connection card inside Tauri runtime', async () => {
    vi.resetModules();
    vi.doMock('@/lib/deploy-mode', async (importOriginal) => {
      const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
      return { ...actual, isTauriRuntime: () => true };
    });
    const { default: TauriCard } = await import('../ServerConnectionCard');
    const { container } = render(<TauriCard />);
    expect(container.firstChild).not.toBeNull();
    expect(screen.getByText('title')).toBeTruthy();
    vi.doUnmock('@/lib/deploy-mode');
  });
});
