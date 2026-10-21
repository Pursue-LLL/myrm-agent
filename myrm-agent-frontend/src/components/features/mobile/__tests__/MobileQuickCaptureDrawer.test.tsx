/** @vitest-environment jsdom */
import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { StagingRecord } from '@/store/offline/offlineStagingStore';
import MobileQuickCaptureDrawer from '../MobileQuickCaptureDrawer';

type SubscriberFn = (records: StagingRecord[]) => void;

const { mockAddItem, mockSyncQueue, mockSubscribe, triggerSubscribers, stableT } = vi.hoisted(() => {
  const subs: SubscriberFn[] = [];
  return {
    mockAddItem: vi.fn().mockResolvedValue('rec-test-123'),
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
    const { container } = render(
      <MobileQuickCaptureDrawer open={false} onClose={defaultOnClose} />,
    );
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
});
