import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ExternalAgentBundleManagerCard } from '../ExternalAgentBundleManagerCard';

describe('ExternalAgentBundleManagerCard', () => {
  it('renders card header, lock-free multiplexer badges, and accessible live output', () => {
    render(<ExternalAgentBundleManagerCard chatId="chat-bundle-1" />);

    expect(screen.getByRole('article', { name: /External Agent Bundle Manager Card/i })).toBeInTheDocument();
    expect(screen.getByText(/External Agent Bundle Manager/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Lock-Free Multiplexer/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Sandbox Isolated/i)).toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(
      screen.getByText(/heterogeneous CLI adapters with lock-free multiplexer active/i),
    ).toBeInTheDocument();
  });

  it('triggers probe on host environment PATH and updates bundle status', async () => {
    const handleProbe = vi.fn().mockResolvedValue({
      bundle_id: 'subagent-gemini-cli',
      binary_name: 'gemini',
      is_installed: true,
      version: '2.5.0-preview',
    });

    render(
      <ExternalAgentBundleManagerCard
        chatId="chat-bundle-1"
        onProbeBundle={handleProbe}
      />,
    );

    // Initial state: gemini CLI has Not Installed badge
    expect(screen.getByText(/Not Installed/i)).toBeInTheDocument();

    // Click probe for gemini
    const probeButtons = screen.getAllByRole('button', { name: /Probe Host/i });
    // Gemini CLI is 3rd bundle
    fireEvent.click(probeButtons[2]);

    expect(handleProbe).toHaveBeenCalledWith('subagent-gemini-cli');
    expect(await screen.findByText(/binary 'gemini' found/i)).toBeInTheDocument();
    expect(screen.getAllByText(/v2.5.0-preview/i).length).toBeGreaterThanOrEqual(1);
  });

  it('selects a bundle from catalog and switches to dispatch tab with bundle selected', () => {
    render(<ExternalAgentBundleManagerCard chatId="chat-bundle-1" />);

    const selectButtons = screen.getAllByRole('button', { name: /Use for Dispatch/i });
    // Click on 2nd bundle (Codex)
    fireEvent.click(selectButtons[1]);

    expect(screen.getByText(/Lock-Free Parallel Subagent Dispatch/i)).toBeInTheDocument();
    expect(screen.getByText(/Worker #1/i)).toBeInTheDocument();
  });

  it('adds workers, applies quick presets, and dispatches multi-agent batch', async () => {
    const handleDispatchBatch = vi.fn().mockResolvedValue({
      batch_id: 'batch-test-77',
      session_id: 'chat-bundle-1',
      total_dispatched: 2,
      dispatched_instances: [
        {
          instance_id: 'inst-twin-1',
          bundle_id: 'subagent-codex',
          session_id: 'chat-bundle-1',
          role_label: 'frontend-dev',
          status: 'running',
          pid: 51201,
          task_prompt: 'Generate unit tests for UI views',
          target_workdir: '/workspace/frontend',
          created_at: Date.now(),
          started_at: Date.now(),
          stdout_chunks: ['[frontend-dev] Test scaffold generated.'],
          artifacts: [],
        },
        {
          instance_id: 'inst-twin-2',
          bundle_id: 'subagent-codex',
          session_id: 'chat-bundle-1',
          role_label: 'backend-dev',
          status: 'running',
          pid: 51202,
          task_prompt: 'Implement DTO validation',
          target_workdir: '/workspace/backend',
          created_at: Date.now(),
          started_at: Date.now(),
          stdout_chunks: ['[backend-dev] Schema validators added.'],
          artifacts: [],
        },
      ],
    });

    render(
      <ExternalAgentBundleManagerCard
        chatId="chat-bundle-1"
        onDispatchBatch={handleDispatchBatch}
      />,
    );

    // Switch to Dispatch tab
    const dispatchTab = screen.getByRole('button', { name: /Parallel Dispatch/i });
    fireEvent.click(dispatchTab);

    // Click Twin Codex Pair preset
    const presetBtn = screen.getByRole('button', { name: /Twin Codex Pair/i });
    fireEvent.click(presetBtn);

    expect(screen.getByText(/Worker #1/i)).toBeInTheDocument();
    expect(screen.getByText(/Worker #2/i)).toBeInTheDocument();

    // Submit batch
    const submitBtn = screen.getByRole('button', { name: /Concurrently Dispatch \(2\)/i });
    fireEvent.click(submitBtn);

    expect(handleDispatchBatch).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({ role_label: 'frontend-dev' }),
        expect.objectContaining({ role_label: 'backend-dev' }),
      ]),
      undefined,
    );

    expect(await screen.findByText(/Successfully multiplexed 2 subagent instance\(s\)/i)).toBeInTheDocument();
    // Switched to Monitor tab automatically
    expect(screen.getByText(/Multiplexed Subagent Instances/i)).toBeInTheDocument();
    expect(screen.getByText(/frontend-dev/i)).toBeInTheDocument();
    expect(screen.getByText(/backend-dev/i)).toBeInTheDocument();
  });

  it('monitors instances, expands logs, and terminates running instance', async () => {
    const handleTerminate = vi.fn().mockResolvedValue({
      instance_id: 'inst-claude-202',
      terminated: true,
      status: 'terminated',
    });

    render(
      <ExternalAgentBundleManagerCard
        chatId="chat-bundle-1"
        onTerminateInstance={handleTerminate}
      />,
    );

    // Switch to Monitor tab
    const monitorTab = screen.getByRole('button', { name: /Monitor/i });
    fireEvent.click(monitorTab);

    expect(screen.getByText(/security-linter/i)).toBeInTheDocument();
    expect(screen.getByText(/frontend-refactorer/i)).toBeInTheDocument();

    // Toggle logs for security-linter
    const logButtons = screen.getAllByRole('button', { name: /Logs/i });
    fireEvent.click(logButtons[1]);

    expect(screen.getByText(/Verifying allowed_roots path containment/i)).toBeInTheDocument();

    // Terminate instance
    const haltBtn = screen.getByRole('button', { name: /Halt Instance/i });
    fireEvent.click(haltBtn);

    expect(handleTerminate).toHaveBeenCalledWith('inst-claude-202', 'user_halted');
    expect(await screen.findByText(/Subagent instance 'inst-claude-202' halted/i)).toBeInTheDocument();
  });
});
