import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  CreatorModeStudioModal,
  AgentPresetDraftData,
} from '../CreatorModeStudioModal';

describe('CreatorModeStudioModal', () => {
  const sampleDraft: AgentPresetDraftData = {
    preset_id: 'preset_test_01',
    name: 'SecurityReviewerBot',
    role: 'code_auditor',
    description: 'Read-only security review agent',
    system_prompt: 'You are SecurityReviewerBot. Strict read-only mode.',
    allowed_tools: ['file_read', 'web_search'],
    denied_tools: ['file_write', 'root_shell', 'bash_command'],
    guardrails: { read_only: true, least_privilege: true },
  };

  it('renders creator mode studio modal header and input', () => {
    render(<CreatorModeStudioModal chatId="chat_01" />);

    expect(screen.getByText(/Creator Mode Studio/i)).toBeInTheDocument();
    expect(screen.getByText(/P0 Metaprogramming/i)).toBeInTheDocument();
    expect(
      screen.getByLabelText(/Describe Desired Agent Scope & Safety Boundaries/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /synthesize agent preset/i }),
    ).toBeInTheDocument();
  });

  it('synthesizes preset draft on button click and renders tool boundaries', () => {
    render(<CreatorModeStudioModal chatId="chat_01" />);

    const synthesizeBtn = screen.getByRole('button', { name: /synthesize agent preset/i });
    fireEvent.click(synthesizeBtn);

    expect(screen.getByTestId('preset-draft-preview')).toBeInTheDocument();
    expect(screen.getByText('CodeAuditorBot')).toBeInTheDocument();
    expect(screen.getByText(/Authorized Whitelist/i)).toBeInTheDocument();
    expect(screen.getByText(/Strictly Prohibited/i)).toBeInTheDocument();
    expect(screen.getByText('file_read')).toBeInTheDocument();
    expect(screen.getByText('root_shell')).toBeInTheDocument();
  });

  it('executes defensive sandbox verification and shows certified badge', async () => {
    vi.useFakeTimers();
    render(<CreatorModeStudioModal chatId="chat_01" initialDraft={sampleDraft} />);

    const verifyBtn = screen.getByRole('button', { name: /verify preset in defensive sandbox/i });
    fireEvent.click(verifyBtn);

    act(() => {
      vi.runAllTimers();
    });

    expect(screen.getByTestId('sandbox-report-banner')).toBeInTheDocument();
    expect(screen.getByText(/Sandbox Defense Certified \(100% Safe\)/i)).toBeInTheDocument();
    expect(screen.getByText(/6\/6 Passed/i)).toBeInTheDocument();

    vi.useRealTimers();
  });

  it('triggers multi-platform roaming synchronization with auto-healing indicator', async () => {
    vi.useFakeTimers();
    render(<CreatorModeStudioModal chatId="chat_01" initialDraft={sampleDraft} />);

    // First trigger verify to enable roaming button
    const verifyBtn = screen.getByRole('button', { name: /verify preset in defensive sandbox/i });
    fireEvent.click(verifyBtn);
    act(() => {
      vi.runAllTimers();
    });

    const roamBtn = screen.getByRole('button', { name: /broadcast preset to roaming platforms/i });
    expect(roamBtn).not.toBeDisabled();
    fireEvent.click(roamBtn);

    act(() => {
      vi.runAllTimers();
    });

    expect(screen.getByTestId('roaming-records-list')).toBeInTheDocument();
    expect(screen.getByText(/Multi-Platform Roaming SSOT/i)).toBeInTheDocument();
    expect(screen.getByText('desktop_tauri')).toBeInTheDocument();
    expect(screen.getByText('cloud')).toBeInTheDocument();
    expect(screen.getByText('Healed')).toBeInTheDocument();

    vi.useRealTimers();
  });

  it('calls external callbacks when provided', () => {
    const handleSynthesize = vi.fn();
    const handleVerify = vi.fn();
    const handleRoaming = vi.fn();
    const handleDismiss = vi.fn();

    render(
      <CreatorModeStudioModal
        chatId="chat_01"
        initialDraft={sampleDraft}
        onSynthesize={handleSynthesize}
        onVerifySandbox={handleVerify}
        onSyncRoaming={handleRoaming}
        onDismiss={handleDismiss}
      />,
    );

    const synthesizeBtn = screen.getByRole('button', { name: /synthesize agent preset/i });
    fireEvent.click(synthesizeBtn);
    expect(handleSynthesize).toHaveBeenCalledTimes(1);

    const verifyBtn = screen.getByRole('button', { name: /verify preset in defensive sandbox/i });
    fireEvent.click(verifyBtn);
    expect(handleVerify).toHaveBeenCalledWith(sampleDraft);

    const dismissBtn = screen.getByRole('button', { name: /close creator mode studio/i });
    fireEvent.click(dismissBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });
});
