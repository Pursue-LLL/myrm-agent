/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../VisualDesktopToggle (POS: 沙箱/本地 VNC 浮动面板与接管控制条)
 *
 * [OUTPUT]
 * Vitest: 桌面视图只在浏览器端按需加载、没有沙箱、关掉重开或重连后迟到的加载结果、套餐无 VNC 权益、
 * 沙箱之外直连本地桌面（含重连）、浮动入口关闭面板、持有控制时卸载、
 * 托管接管只在开始时打开一次、Skip/Done 与自动检测。
 *
 * [POS]
 * 与 visual-desktop-toggle.test.tsx 共用 visualDesktopToggleKit 的替身；这里覆盖面板的各种状态与边界。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  mocks,
  openPanel,
  prepareToggleKit,
  releaseToggleKit,
  resumeCalls,
  vncResponse,
} from './visualDesktopToggleKit';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useUserControlStore from '@/store/useUserControlStore';
import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';
import { VisualDesktop } from '../VisualDesktop';
import { VisualDesktopToggle } from '../VisualDesktopToggle';

type PendingLoad = Pick<ReturnType<typeof deferred<ReturnType<typeof vncResponse>>>, 'resolve' | 'reject'>;

const launcher = () => screen.getByRole('button', { name: 'toggleTitle' });
const desktop = () => screen.queryByTestId('visual-desktop');

describe('VisualDesktopToggle states', () => {
  beforeEach(() => {
    prepareToggleKit();
    mocks.fetchSandboxVncUrl.mockResolvedValue(vncResponse());
  });

  afterEach(releaseToggleKit);

  it('loads the desktop view on demand, from its own module and in the browser only', async () => {
    const [view] = mocks.lazyViews;

    expect(view.options).toEqual({ ssr: false });
    await expect(view.load()).resolves.toEqual({ default: VisualDesktop });
  });

  describe('loading the sandbox desktop', () => {
    it('says so, with a reconnect action, when the user has no sandbox', async () => {
      mocks.fetchUserSandbox.mockResolvedValue(null);

      openPanel();

      expect(await screen.findByText('loadFailed')).toBeInTheDocument();
      expect(mocks.fetchSandboxVncUrl).not.toHaveBeenCalled();
      expect(desktop()).not.toBeInTheDocument();
    });

    /** Opens, closes and reopens the panel, so the first load is stale while the second one is in flight. */
    async function reopenWhileLoading() {
      const stale = deferred<ReturnType<typeof vncResponse>>();
      const current = deferred<ReturnType<typeof vncResponse>>();
      mocks.fetchSandboxVncUrl.mockReturnValueOnce(stale.promise).mockReturnValueOnce(current.promise);

      openPanel();
      await waitFor(() => expect(mocks.fetchSandboxVncUrl).toHaveBeenCalledTimes(1));
      fireEvent.click(screen.getByRole('button', { name: 'close' }));
      fireEvent.click(launcher());
      await waitFor(() => expect(mocks.fetchSandboxVncUrl).toHaveBeenCalledTimes(2));
      return { stale, current };
    }

    const staleOutcomes: Array<{ outcome: string; settle: (load: PendingLoad) => void }> = [
      { outcome: 'arrives', settle: (load) => load.resolve(vncResponse('wss://stale.example/sb-1')) },
      { outcome: 'fails', settle: (load) => load.reject(new Error('network')) },
    ];

    it.each(staleOutcomes)('keeps showing the connection in progress when a stale load $outcome', async (stale) => {
      const loads = await reopenWhileLoading();

      await act(async () => stale.settle(loads.stale));

      expect(screen.getByText('connecting')).toBeInTheDocument();
      expect(screen.queryByText('loadFailed')).not.toBeInTheDocument();
      expect(desktop()).not.toBeInTheDocument();

      await act(async () => loads.current.resolve(vncResponse()));
      expect(await screen.findByTestId('visual-desktop')).toHaveAttribute(
        'data-ws-url',
        'wss://vnc.example/sb-1?token=tok',
      );
    });

    it.each(staleOutcomes)(
      'keeps the live desktop when a stale load $outcome after the new one connected',
      async (stale) => {
        const loads = await reopenWhileLoading();
        await act(async () => loads.current.resolve(vncResponse()));
        await screen.findByTestId('visual-desktop');

        await act(async () => stale.settle(loads.stale));

        expect(screen.getByTestId('visual-desktop')).toHaveAttribute('data-ws-url', 'wss://vnc.example/sb-1?token=tok');
        expect(screen.queryByText('loadFailed')).not.toBeInTheDocument();
      },
    );

    it('ignores a reply that a reconnect has overtaken', async () => {
      const first = deferred<ReturnType<typeof vncResponse>>();
      const second = deferred<ReturnType<typeof vncResponse>>();
      mocks.fetchSandboxVncUrl.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
      openPanel();
      await waitFor(() => expect(mocks.fetchSandboxVncUrl).toHaveBeenCalledTimes(1));
      fireEvent.click(screen.getAllByRole('button', { name: 'reconnect' })[0]);
      await waitFor(() => expect(mocks.fetchSandboxVncUrl).toHaveBeenCalledTimes(2));

      await act(async () => second.resolve(vncResponse('wss://second.example/sb-1')));
      await act(async () => first.resolve(vncResponse('wss://first.example/sb-1')));

      expect(await screen.findByTestId('visual-desktop')).toHaveAttribute(
        'data-ws-url',
        'wss://second.example/sb-1?token=tok',
      );
    });
  });

  describe('plan and deployment', () => {
    it('hides the launcher altogether when the plan has no VNC access', () => {
      mocks.entitlements = { canUseVnc: false, isLoading: false };

      const { container } = render(<VisualDesktopToggle />);

      expect(container).toBeEmptyDOMElement();
    });

    it('keeps the launcher while the plan is still being looked up', () => {
      mocks.entitlements = { canUseVnc: false, isLoading: true };

      render(<VisualDesktopToggle />);

      expect(launcher()).toBeInTheDocument();
    });

    it('connects straight to the local desktop outside the sandbox, whatever the plan says', async () => {
      mocks.sandbox = false;
      mocks.entitlements = { canUseVnc: false, isLoading: false };

      openPanel();

      expect(await screen.findByTestId('visual-desktop')).toHaveAttribute('data-ws-url', 'ws://localhost:6080');
      expect(mocks.fetchUserSandbox).not.toHaveBeenCalled();
    });

    it('reconnects the local desktop without looking for a sandbox that is not there', async () => {
      mocks.sandbox = false;
      mocks.fetchUserSandbox.mockResolvedValue(null);
      openPanel();
      const before = await screen.findByTestId('visual-desktop');

      fireEvent.click(screen.getByRole('button', { name: 'reconnect' }));

      await waitFor(() => expect(screen.getByTestId('visual-desktop')).not.toBe(before));
      expect(screen.getByTestId('visual-desktop')).toHaveAttribute('data-ws-url', 'ws://localhost:6080');
      expect(mocks.fetchUserSandbox).not.toHaveBeenCalled();
    });
  });

  it('closes an open panel from the launcher', async () => {
    openPanel();
    await screen.findByTestId('visual-desktop');

    fireEvent.click(launcher());

    await waitFor(() => expect(desktop()).not.toBeInTheDocument());
  });

  describe('going away while holding control', () => {
    it('hands control back, so the agent is not left waiting', async () => {
      const view = render(<VisualDesktopToggle />);
      await useUserControlStore.getState().acquire('Solve the CAPTCHA');
      mocks.fetchWithTimeout.mockClear();

      view.unmount();

      await waitFor(() => expect(resumeCalls()).toHaveLength(1));
      expect(useUserControlStore.getState().held).toBe(false);
    });

    it('lets go quietly even when the hand back fails', async () => {
      const view = render(<VisualDesktopToggle />);
      await useUserControlStore.getState().acquire('Solve the CAPTCHA');
      mocks.fetchWithTimeout.mockResolvedValue({ ok: false, status: 503 });

      view.unmount();
      await waitFor(() => expect(resumeCalls()).toHaveLength(1));
      await settle();

      expect(mocks.toastError).not.toHaveBeenCalled();
    });
  });

  describe('a managed takeover', () => {
    const ask = (autoDetectCompletion: boolean) =>
      useBrowserTakeoverStore.getState().requestTakeover({
        reason: 'Solve the CAPTCHA',
        ui_mode: 'managed',
        auto_detect_completion: autoDetectCompletion,
      });

    it('opens for a takeover that starts while the page is up, and again for the next one', async () => {
      render(<VisualDesktopToggle />);
      expect(desktop()).not.toBeInTheDocument();

      act(() => ask(false));
      expect(await screen.findByTestId('visual-desktop')).toBeInTheDocument();

      act(() => useBrowserTakeoverStore.getState().completeTakeover());
      fireEvent.click(screen.getByRole('button', { name: 'close' }));
      await waitFor(() => expect(desktop()).not.toBeInTheDocument());

      act(() => ask(false));
      expect(await screen.findByTestId('visual-desktop')).toBeInTheDocument();
    });

    it('stays closed once the person closes it, and the launcher brings it back with Skip and Done', async () => {
      ask(false);
      render(<VisualDesktopToggle />);
      await screen.findByTestId('visual-desktop');

      fireEvent.click(screen.getByRole('button', { name: 'close' }));
      await settle();
      expect(desktop()).not.toBeInTheDocument();

      fireEvent.click(launcher());
      expect(await screen.findByRole('button', { name: 'takeoverDone' })).toBeInTheDocument();
    });

    it('does not pop open when the takeover ends while the panel is closed', async () => {
      ask(false);
      render(<VisualDesktopToggle />);
      await screen.findByTestId('visual-desktop');
      fireEvent.click(screen.getByRole('button', { name: 'close' }));
      await settle();

      act(() => useBrowserTakeoverStore.getState().completeTakeover());
      await settle();

      expect(desktop()).not.toBeInTheDocument();
    });

    it('puts Skip and Done in the hands of the person the agent is waiting on', async () => {
      ask(false);
      render(<VisualDesktopToggle />);
      expect(await screen.findByText('Solve the CAPTCHA')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'takeoverSkip' }));
      expect(mocks.takeoverActions.handleTakeoverSkip).toHaveBeenCalledTimes(1);
      expect(mocks.takeoverActions.handleTakeoverComplete).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole('button', { name: 'takeoverDone' }));
      expect(mocks.takeoverActions.handleTakeoverComplete).toHaveBeenCalledTimes(1);
    });

    it('explains the automatic check instead of offering Skip and Done when the page completes itself', async () => {
      ask(true);
      render(<VisualDesktopToggle />);

      expect(await screen.findByText('takeoverCaptchaAuto')).toBeInTheDocument();
      expect(screen.queryByText('Solve the CAPTCHA')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'takeoverSkip' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'takeoverDone' })).not.toBeInTheDocument();
    });
  });
});
