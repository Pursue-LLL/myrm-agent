/** @vitest-environment jsdom */
import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest';
import type { StagingRecord } from '@/store/offline/offlineStagingStore';
import MobileQuickCaptureDrawer from '../MobileQuickCaptureDrawer';

type SubscriberFn = (records: StagingRecord[]) => void;

const { mockAddItem, mockSyncQueue, mockSubscribe, mockShowI18nToast, triggerSubscribers, stableT } = vi.hoisted(() => {
  const subs: SubscriberFn[] = [];
  return {
    mockAddItem: vi.fn().mockResolvedValue('rec-test-123'),
    mockShowI18nToast: vi.fn(),
    mockSyncQueue: vi.fn().mockResolvedValue(undefined),
    mockSubscribe: vi.fn((fn: SubscriberFn) => {
      subs.push(fn);
      fn([]);
      return () => {
        const idx = subs.indexOf(fn);
        if (idx !== -1) {
          subs.splice(idx, 1);
        }
      };
    }),
    triggerSubscribers: (records: StagingRecord[]) => {
      for (const fn of subs) {
        fn(records);
      }
    },
    stableT: (key: string) => {
      const translations: Record<string, string> = {
        title: '极速倾倒抽屉',
        e2eeShielded: 'AES-256 E2EE 加密保护',
        close: '关闭',
        offlineMode: '离线模式',
        onlineReady: '网络已连接',
        syncNow: '立即同步',
        stagedVaultItems: '暂存箱待同步项',
        noStagedItems: '暂无暂存笔记',
        untitled: '未命名笔记',
        titlePlaceholder: '标题 (可选)',
        contentPlaceholder: '随手记下灵感...',
        recording: '录音中...',
        voiceNote: '语音转写',
        saveToVault: '保存到暂存箱',
        savedNotice: '已加密保存至本地暂存箱',
        speechUnsupported: '不支持语音转写',
      };
      return translations[key] ?? key;
    },
  };
});

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: mockShowI18nToast,
}));

vi.mock('@/store/offline/offlineStagingStore', () => ({
  offlineStagingStore: {
    addItem: mockAddItem,
    syncQueue: mockSyncQueue,
    subscribe: mockSubscribe,
  },
}));

describe('MobileQuickCaptureDrawer', () => {
  const defaultOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when open is false', () => {
    const { container } = render(<MobileQuickCaptureDrawer open={false} onClose={defaultOnClose} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer header, e2ee badge, and inputs when open is true', () => {
    render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

    expect(screen.getByTestId('mobile-quick-capture-drawer')).toBeInTheDocument();
    expect(screen.getByText('极速倾倒抽屉')).toBeInTheDocument();
    expect(screen.getByText('AES-256 E2EE 加密保护')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('随手记下灵感...')).toBeInTheDocument();
  });

  it('triggers onClose when close button is clicked', () => {
    render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

    const closeButtons = screen.getAllByRole('button', { name: '关闭' });
    fireEvent.click(closeButtons[0]);
    expect(defaultOnClose).toHaveBeenCalledTimes(1);
  });

  it('allows toggling tags', () => {
    render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

    const ideaTag = screen.getByTestId('quick-capture-tag-Idea');
    expect(ideaTag).toBeInTheDocument();
    expect(ideaTag.className).toContain('bg-muted/40');

    // Select tag
    fireEvent.click(ideaTag);
    expect(ideaTag.className).toContain('bg-primary/15');

    // Deselect tag
    fireEvent.click(ideaTag);
    expect(ideaTag.className).toContain('bg-muted/40');
  });

  it('disables save button when content is empty and enables when content is typed', () => {
    render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

    const submitBtn = screen.getByTestId('quick-capture-submit-button');
    expect(submitBtn).toBeDisabled();

    const contentInput = screen.getByTestId('quick-capture-content-input');
    fireEvent.change(contentInput, { target: { value: 'My urgent thought' } });
    expect(submitBtn).not.toBeDisabled();
  });

  it('submits note to offlineStagingStore and shows success feedback', async () => {
    render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

    const titleInput = screen.getByTestId('quick-capture-title-input');
    const contentInput = screen.getByTestId('quick-capture-content-input');
    const ideaTag = screen.getByTestId('quick-capture-tag-Idea');
    const submitBtn = screen.getByTestId('quick-capture-submit-button');

    fireEvent.change(titleInput, { target: { value: 'Secret Note' } });
    fireEvent.change(contentInput, { target: { value: 'Decentralized AI node configuration' } });
    fireEvent.click(ideaTag);

    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(mockAddItem).toHaveBeenCalledWith({
      title: 'Secret Note',
      content: 'Decentralized AI node configuration',
      voiceTranscript: undefined,
      tags: ['Idea'],
    });

    // Inputs should be cleared
    expect((contentInput as HTMLTextAreaElement).value).toBe('');
    expect((titleInput as HTMLInputElement).value).toBe('');

    // Success notice is displayed
    expect(screen.getByText('已加密保存至本地暂存箱')).toBeInTheDocument();
  });

  describe('saving', () => {
    const SAVED_NOTICE = '已加密保存至本地暂存箱';

    async function save(text: string) {
      fireEvent.change(screen.getByTestId('quick-capture-content-input'), { target: { value: text } });
      await act(async () => {
        fireEvent.click(screen.getByTestId('quick-capture-submit-button'));
      });
    }

    afterEach(() => {
      vi.useRealTimers();
    });

    it('tells the user and keeps the draft when the note cannot be staged', async () => {
      mockAddItem.mockRejectedValueOnce(new Error('IndexedDB is unavailable'));
      render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);
      fireEvent.change(screen.getByTestId('quick-capture-title-input'), { target: { value: 'Plan' } });
      fireEvent.click(screen.getByTestId('quick-capture-tag-Todo'));

      await save('Call the vendor');

      expect(mockShowI18nToast).toHaveBeenCalledWith('mobile.quickCapture.saveFailed', undefined, { type: 'error' });
      expect((screen.getByTestId('quick-capture-content-input') as HTMLTextAreaElement).value).toBe('Call the vendor');
      expect((screen.getByTestId('quick-capture-title-input') as HTMLInputElement).value).toBe('Plan');
      expect(screen.getByTestId('quick-capture-tag-Todo').className).toContain('bg-primary/15');
      expect(screen.queryByText(SAVED_NOTICE)).toBeNull();
      expect(screen.getByTestId('quick-capture-submit-button')).not.toBeDisabled();
    });

    it('saves the same draft once the staging store works again', async () => {
      mockAddItem.mockRejectedValueOnce(new Error('IndexedDB is unavailable'));
      render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

      await save('Call the vendor');
      await act(async () => {
        fireEvent.click(screen.getByTestId('quick-capture-submit-button'));
      });

      expect(mockAddItem).toHaveBeenCalledTimes(2);
      expect(screen.getByText(SAVED_NOTICE)).toBeInTheDocument();
      expect(mockShowI18nToast).toHaveBeenCalledTimes(1);
    });

    it('hides the saved notice after 2.5 seconds', async () => {
      vi.useFakeTimers();
      render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

      await save('First note');
      expect(screen.getByText(SAVED_NOTICE)).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(2499);
      });
      expect(screen.getByText(SAVED_NOTICE)).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(screen.queryByText(SAVED_NOTICE)).toBeNull();
    });

    it('keeps the notice of a second save for its full time', async () => {
      vi.useFakeTimers();
      render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

      await save('First note');
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      await save('Second note');

      // The first save's timer would have run out here.
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(screen.getByText(SAVED_NOTICE)).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(1500);
      });
      expect(screen.queryByText(SAVED_NOTICE)).toBeNull();
    });

    it('leaves no notice timer behind when it is unmounted', async () => {
      vi.useFakeTimers();
      const { unmount } = render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

      await save('First note');
      const running = vi.getTimerCount();
      expect(running).toBeGreaterThan(0);

      unmount();

      expect(vi.getTimerCount()).toBeLessThan(running);
    });
  });

  it('toggles queue view and displays staged records', () => {
    render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

    const queueToggle = screen.getByTestId('quick-capture-queue-toggle');
    expect(queueToggle).toBeInTheDocument();

    const mockRecords: StagingRecord[] = [
      {
        id: 'staged-1',
        payload: { content: 'Offline draft note 1', title: 'Note 1' },
        envelope: {
          version: 1,
          ciphertext: 'enc',
          iv: 'iv',
          salt: 'salt',
          algorithm: 'AES-GCM-256',
          createdAt: 1760000000000,
        },
        status: 'staged',
        createdAt: 1760000000000,
        updatedAt: 1760000000000,
        retryCount: 0,
      },
    ];

    act(() => {
      triggerSubscribers(mockRecords);
    });

    // Toggle queue open
    fireEvent.click(queueToggle);

    expect(screen.getByTestId('staged-vault-queue-view')).toBeInTheDocument();
    expect(screen.getByText('Note 1')).toBeInTheDocument();
    expect(screen.getByText('Offline draft note 1')).toBeInTheDocument();
    expect(screen.getByText('staged')).toBeInTheDocument();
  });

  it('triggers manual sync when unsynced items exist and sync button is pressed', async () => {
    render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

    const mockRecords: StagingRecord[] = [
      {
        id: 'staged-2',
        payload: { content: 'Offline draft note 2' },
        envelope: {
          version: 1,
          ciphertext: 'enc',
          iv: 'iv',
          salt: 'salt',
          algorithm: 'AES-GCM-256',
          createdAt: 1760000000000,
        },
        status: 'staged',
        createdAt: 1760000000000,
        updatedAt: 1760000000000,
        retryCount: 0,
      },
    ];

    act(() => {
      triggerSubscribers(mockRecords);
    });

    const syncBtn = screen.getByTestId('quick-capture-manual-sync');
    expect(syncBtn).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(syncBtn);
    });

    expect(mockSyncQueue).toHaveBeenCalledTimes(1);
  });

  it('supports uncontrolled mode opened via myrm:open-quick-capture global event', () => {
    const { container } = render(<MobileQuickCaptureDrawer />);
    expect(container.firstChild).toBeNull();

    // Dispatch global event
    act(() => {
      window.dispatchEvent(new CustomEvent('myrm:open-quick-capture'));
    });

    expect(screen.getByTestId('mobile-quick-capture-drawer')).toBeInTheDocument();

    // Close
    const closeButtons = screen.getAllByRole('button', { name: '关闭' });
    act(() => {
      fireEvent.click(closeButtons[0]);
    });

    expect(screen.queryByTestId('mobile-quick-capture-drawer')).toBeNull();
  });

  describe('connectivity', () => {
    let onLine: MockInstance<() => boolean>;
    const stagedRecord = (): StagingRecord => ({
      id: 'staged-3',
      payload: { content: 'Draft written offline' },
      envelope: {
        version: 1,
        ciphertext: 'enc',
        iv: 'iv',
        salt: 'salt',
        algorithm: 'AES-GCM-256',
        createdAt: 1760000000000,
      },
      status: 'staged',
      createdAt: 1760000000000,
      updatedAt: 1760000000000,
      retryCount: 0,
    });
    const setConnectivity = (online: boolean) => {
      onLine.mockReturnValue(online);
      act(() => {
        window.dispatchEvent(new Event(online ? 'online' : 'offline'));
      });
    };

    beforeEach(() => {
      onLine = vi.spyOn(window.navigator, 'onLine', 'get').mockReturnValue(true);
    });
    afterEach(() => {
      onLine.mockRestore();
    });

    it('shows the browser as online when it is', () => {
      render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

      expect(screen.getByText('网络已连接')).toBeInTheDocument();
      expect(screen.queryByText('离线模式')).toBeNull();
    });

    it('shows offline mode from the first render when the browser starts offline', () => {
      onLine.mockReturnValue(false);

      render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

      expect(screen.getByText('离线模式')).toBeInTheDocument();
      expect(screen.queryByText('网络已连接')).toBeNull();
    });

    it('follows the browser going offline and coming back', () => {
      render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

      setConnectivity(false);
      expect(screen.getByText('离线模式')).toBeInTheDocument();

      setConnectivity(true);
      expect(screen.getByText('网络已连接')).toBeInTheDocument();
    });

    it('cannot sync staged notes while offline, and can once back online', () => {
      onLine.mockReturnValue(false);
      render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);
      act(() => {
        triggerSubscribers([stagedRecord()]);
      });

      expect(screen.getByTestId('quick-capture-manual-sync')).toBeDisabled();

      setConnectivity(true);
      expect(screen.getByTestId('quick-capture-manual-sync')).not.toBeDisabled();
    });

    it('stops listening to connectivity when unmounted', () => {
      const removed = vi.spyOn(window, 'removeEventListener');
      const { unmount } = render(<MobileQuickCaptureDrawer open={true} onClose={defaultOnClose} />);

      unmount();

      expect(removed.mock.calls.map(([type]) => type)).toEqual(expect.arrayContaining(['online', 'offline']));
      removed.mockRestore();
    });
  });
});
