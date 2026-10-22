import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  MixedFleetPresetCard,
  FleetStatusSnapshotData,
} from '../MixedFleetPresetCard';

describe('MixedFleetPresetCard', () => {
  const mockSnapshot: FleetStatusSnapshotData = {
    chat_id: 'chat-mixed-test-01',
    local_brain: {
      node_id: 'node-local-test',
      role: 'local_brain',
      display_name: 'Local Brain (Privacy & Memory)',
      is_online: true,
      last_heartbeat: '2026-10-15T12:00:00Z',
      supported_capabilities: ['local_memory', 'knowledge_base'],
    },
    remote_executor: {
      node_id: 'node-remote-test',
      role: 'remote_executor',
      display_name: 'Remote Executor (24/7 Cloud Sandbox)',
      is_online: true,
      endpoint_url: 'https://remote.internal',
      last_heartbeat: '2026-10-15T12:00:00Z',
      supported_capabilities: ['long_running_jobs'],
    },
    active_manifest: {
      manifest_id: 'mf-handoff-test-01',
      chat_id: 'chat-mixed-test-01',
      source_role: 'local_brain',
      target_role: 'remote_executor',
      task_instruction: '持续抓取竞品动态并编译分析周报',
      handoff_markdown: '# Mixed Fleet Handoff Manifest',
      context_files: ['rules.json'],
      execution_status: 'dispatched',
      created_at: '2026-10-15T12:00:05Z',
      synced_at: null,
      output_summary: null,
      error_detail: null,
    },
    total_handoffs: 1,
  };

  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((url: string) => {
        if (url.includes('/mixed-fleet/snapshot')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({ data: mockSnapshot }),
          });
        }
        if (url.includes('/mixed-fleet/dispatch')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                ...mockSnapshot.active_manifest,
                manifest_id: 'mf-handoff-new-02',
              },
            }),
          });
        }
        if (url.includes('/sync')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                ...mockSnapshot.active_manifest,
                synced_at: '2026-10-15T12:05:00Z',
              },
            }),
          });
        }
        if (url.includes('/heartbeat')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                ...mockSnapshot.remote_executor,
                is_online: false,
              },
            }),
          });
        }
        if (url.includes('/complete')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: {
                ...mockSnapshot.active_manifest,
                execution_status: 'completed',
                output_summary: '24/7 远端沙箱运行完成，生成结构化分析工件',
              },
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({ data: {} }),
        });
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders card with initial snapshot and handles dismiss', async () => {
    const handleDismiss = vi.fn();

    await act(async () => {
      render(
        <MixedFleetPresetCard
          chatId="chat-mixed-test-01"
          initialSnapshot={mockSnapshot}
          onDismiss={handleDismiss}
        />,
      );
    });

    expect(screen.getByText('混合舰队 (Local Brain + Remote Executor)')).toBeInTheDocument();
    expect(screen.getByText('Local Brain (Privacy & Memory)')).toBeInTheDocument();
    expect(screen.getByText('Remote Executor (24/7 Cloud Sandbox)')).toBeInTheDocument();
    expect(screen.getByText('mf-handoff-test-01')).toBeInTheDocument();
    expect(screen.getByText('持续抓取竞品动态并编译分析周报')).toBeInTheDocument();

    const closeBtn = screen.getByRole('button', { name: '关闭' });
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('dispatches a task from Local Brain to Remote Executor', async () => {
    await act(async () => {
      render(
        <MixedFleetPresetCard
          chatId="chat-mixed-test-01"
          initialSnapshot={mockSnapshot}
        />,
      );
    });

    const textarea = screen.getByPlaceholderText('输入需要远端 24/7 不间断执行的长耗时任务...');
    fireEvent.change(textarea, { target: { value: '分析 GitHub 仓库提交趋势' } });

    const filesInput = screen.getByPlaceholderText('附加本地上下文文件 (逗号分隔)');
    fireEvent.change(filesInput, { target: { value: 'repos.json, tokens.txt' } });

    const dispatchBtn = screen.getByRole('button', { name: /派发/ });
    await act(async () => {
      fireEvent.click(dispatchBtn);
    });

    expect(screen.getByText('任务已成功派发至 24/7 Remote Executor')).toBeInTheDocument();
  });

  it('syncs latest remote progress when sync button clicked', async () => {
    await act(async () => {
      render(
        <MixedFleetPresetCard
          chatId="chat-mixed-test-01"
          initialSnapshot={mockSnapshot}
        />,
      );
    });

    const syncBtn = screen.getByRole('button', { name: '拉取同步' });
    await act(async () => {
      fireEvent.click(syncBtn);
    });

    expect(screen.getByText('已同步最新工件进展')).toBeInTheDocument();
  });

  it('toggles remote executor online status via heartbeat', async () => {
    await act(async () => {
      render(
        <MixedFleetPresetCard
          chatId="chat-mixed-test-01"
          initialSnapshot={mockSnapshot}
        />,
      );
    });

    const toggleBtn = screen.getByTitle('切换在线状态');
    await act(async () => {
      fireEvent.click(toggleBtn);
    });

    expect(screen.getByText('Remote Executor 已切为离线')).toBeInTheDocument();
  });

  it('simulates remote execution completion', async () => {
    await act(async () => {
      render(
        <MixedFleetPresetCard
          chatId="chat-mixed-test-01"
          initialSnapshot={mockSnapshot}
        />,
      );
    });

    const completeBtn = screen.getByRole('button', { name: '演练完成' });
    await act(async () => {
      fireEvent.click(completeBtn);
    });

    expect(screen.getByText('远端执行器已提交完成工件')).toBeInTheDocument();
  });
});
