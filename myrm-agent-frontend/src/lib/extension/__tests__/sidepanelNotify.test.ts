/**
 * @vitest-environment node
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type NotifyModule = typeof import('../../../../../myrm-agent-extension/src/sidepanel/approval_notify.js');

interface BrowserState {
  stored?: Record<string, unknown>;
  windowFocused?: boolean;
  pageHidden?: boolean;
}

/** Stubs the browser around a fresh copy of the module (it keeps the click-listener and withdrawal state). */
async function loadNotify({ stored = {}, windowFocused = false, pageHidden = false }: BrowserState = {}) {
  const clickListeners: Array<(id: string) => void | Promise<void>> = [];
  const chromeStub = {
    i18n: { getMessage: (key: string) => key },
    runtime: { getURL: (path: string) => `chrome-extension://myrm/${path}` },
    storage: { local: { get: vi.fn(async () => stored) } },
    windows: { getCurrent: vi.fn(async () => ({ id: 7, focused: windowFocused })), update: vi.fn(async () => ({})) },
    notifications: {
      create: vi.fn(async () => 'approval-pending'),
      clear: vi.fn(),
      onClicked: { addListener: vi.fn((listener) => clickListeners.push(listener)) },
    },
  };
  vi.stubGlobal('chrome', chromeStub);
  vi.stubGlobal('document', { hidden: pageHidden });
  vi.resetModules();
  const notify: NotifyModule = await import('../../../../../myrm-agent-extension/src/sidepanel/approval_notify.js');
  return { notify, chromeStub, clickListeners };
}

beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('shouldNotifyApproval', () => {
  it.each([
    { enabled: true, windowFocused: false, pageHidden: false, expected: true },
    { enabled: true, windowFocused: true, pageHidden: true, expected: true },
    { enabled: true, windowFocused: false, pageHidden: true, expected: true },
    { enabled: true, windowFocused: true, pageHidden: false, expected: false },
    { enabled: false, windowFocused: false, pageHidden: true, expected: false },
  ])(
    'enabled=$enabled windowFocused=$windowFocused pageHidden=$pageHidden → $expected',
    async ({ expected, ...state }) => {
      const { notify } = await loadNotify();

      expect(notify.shouldNotifyApproval(state)).toBe(expected);
    },
  );
});

describe('notifyApprovalPending', () => {
  it('raises one notification when the browser window is not in front, saying when the request is settled', async () => {
    const { notify, chromeStub } = await loadNotify({ windowFocused: false });

    await notify.notifyApprovalPending('rejected at 10:02:30');

    expect(chromeStub.notifications.create).toHaveBeenCalledTimes(1);
    expect(chromeStub.notifications.create).toHaveBeenCalledWith('approval-pending', {
      type: 'basic',
      iconUrl: 'chrome-extension://myrm/icons/icon128.png',
      title: 'notifyApprovalTitle',
      message: 'notifyApprovalBody\nrejected at 10:02:30',
    });
  });

  it('leaves out the deadline line when the request has none', async () => {
    const { notify, chromeStub } = await loadNotify({ windowFocused: false });

    await notify.notifyApprovalPending('');

    expect(chromeStub.notifications.create).toHaveBeenCalledWith(
      'approval-pending',
      expect.objectContaining({ message: 'notifyApprovalBody' }),
    );
  });

  it('stays quiet while the user is looking at the browser window', async () => {
    const { notify, chromeStub } = await loadNotify({ windowFocused: true, pageHidden: false });

    await notify.notifyApprovalPending('');

    expect(chromeStub.notifications.create).not.toHaveBeenCalled();
  });

  it('speaks up when the browser is in front but the panel is not showing', async () => {
    const { notify, chromeStub } = await loadNotify({ windowFocused: true, pageHidden: true });

    await notify.notifyApprovalPending('');

    expect(chromeStub.notifications.create).toHaveBeenCalledTimes(1);
  });

  it('is on until the user turns it off in the popup', async () => {
    const off = await loadNotify({ stored: { approvalNotifyEnabled: false } });
    await off.notify.notifyApprovalPending('');
    expect(off.chromeStub.notifications.create).not.toHaveBeenCalled();

    const untouched = await loadNotify({ stored: {} });
    await untouched.notify.notifyApprovalPending('');
    expect(untouched.chromeStub.notifications.create).toHaveBeenCalledTimes(1);
    expect(untouched.chromeStub.storage.local.get).toHaveBeenCalledWith(untouched.notify.APPROVAL_NOTIFY_KEY);
  });

  it('drops a notification that was still being prepared when the approval was answered', async () => {
    const { notify, chromeStub } = await loadNotify({ windowFocused: false });

    const pending = notify.notifyApprovalPending('');
    notify.clearApprovalNotification();
    await pending;

    expect(chromeStub.notifications.create).not.toHaveBeenCalled();
  });

  it('withdraws the notification once the approval is answered', async () => {
    const { notify, chromeStub } = await loadNotify();

    notify.clearApprovalNotification();

    expect(chromeStub.notifications.clear).toHaveBeenCalledWith('approval-pending');
  });

  it('brings the browser window forward when the notification is clicked, and ignores other notifications', async () => {
    const { notify, chromeStub, clickListeners } = await loadNotify({ windowFocused: false });
    await notify.notifyApprovalPending('');
    expect(clickListeners).toHaveLength(1);

    await clickListeners[0]('clip-success-123');
    expect(chromeStub.windows.update).not.toHaveBeenCalled();

    await clickListeners[0]('approval-pending');
    expect(chromeStub.notifications.clear).toHaveBeenCalledWith('approval-pending');
    expect(chromeStub.windows.update).toHaveBeenCalledWith(7, { focused: true });
  });

  it('listens for the click once however many approvals arrive', async () => {
    const { notify, clickListeners } = await loadNotify({ windowFocused: false });

    await notify.notifyApprovalPending('');
    await notify.notifyApprovalPending('');

    expect(clickListeners).toHaveLength(1);
  });

  it('fails soft: a browser that refuses the lookup does not break the approval', async () => {
    const { notify, chromeStub } = await loadNotify();
    chromeStub.windows.getCurrent.mockRejectedValueOnce(new Error('no window'));

    await expect(notify.notifyApprovalPending('')).resolves.toBeUndefined();

    expect(chromeStub.notifications.create).not.toHaveBeenCalled();
    expect(console.warn).toHaveBeenCalled();
  });

  it('does nothing in a browser without the notifications API', async () => {
    const { notify, chromeStub } = await loadNotify();
    delete (chromeStub as { notifications?: unknown }).notifications;

    await expect(notify.notifyApprovalPending('')).resolves.toBeUndefined();
    expect(() => notify.clearApprovalNotification()).not.toThrow();
  });
});
