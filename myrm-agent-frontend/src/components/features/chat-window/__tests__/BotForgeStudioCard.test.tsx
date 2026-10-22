import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BotForgeStudioCard } from '../BotForgeStudioCard';
import { PipelineExecutionState } from '../bot-forge/types';

describe('BotForgeStudioCard', () => {
  it('renders studio header, safety envelope badge, and accessible live output', () => {
    render(<BotForgeStudioCard chatId="chat-forge-1" />);

    expect(screen.getByRole('article', { name: /Bot Forge Studio Card/i })).toBeInTheDocument();
    expect(screen.getByText(/Bot Forge & Team Studio/i)).toBeInTheDocument();
    expect(screen.getByText(/Safety Envelope Active/i)).toBeInTheDocument();
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText(/Ready to forge agents & teams with builder safety bounds/i)).toBeInTheDocument();
  });

  it('allows quick preset auto-fill and overlap analysis trigger', async () => {
    const handleCheckOverlap = vi.fn().mockResolvedValue({
      verdict: 'duplicate_name',
      conflicting_name: 'sec-auditor',
      recommendation: "Agent 'sec-auditor' exists. Suggest using 'sec-auditor-specialist'.",
    });

    render(<BotForgeStudioCard chatId="chat-forge-1" onCheckOverlap={handleCheckOverlap} />);

    // Click quick preset
    const secBtn = screen.getByRole('button', { name: /Sec Auditor/i });
    fireEvent.click(secBtn);

    const nameInput = screen.getByLabelText(/Agent Name/i) as HTMLInputElement;
    expect(nameInput.value).toBe('sec-auditor');

    // Click Analyze Duty Overlap
    const overlapBtn = screen.getByRole('button', { name: /Analyze Duty Overlap/i });
    fireEvent.click(overlapBtn);

    expect(handleCheckOverlap).toHaveBeenCalledWith('sec-auditor', expect.any(String));
    expect(await screen.findByText(/Duplicate Name Detected/i)).toBeInTheDocument();
    expect(screen.getByText(/Suggest using 'sec-auditor-specialist'/i)).toBeInTheDocument();
  });

  it('submits single agent creation pipeline and updates catalog', async () => {
    const handleCreateAgent = vi.fn().mockResolvedValue({
      pipeline_id: 'pipe-test-99',
      target_name: 'daily-digest-bot',
      is_team: false,
      current_stage: 'completed',
      created_agents: ['daily-digest-bot'],
      started_at: Date.now() - 200,
      completed_at: Date.now(),
      verification: {
        passed: true,
        severity: 'pass',
        findings: [],
        observed_state: { status: 'ready' },
      },
    });

    render(<BotForgeStudioCard chatId="chat-forge-1" onCreateAgent={handleCreateAgent} />);

    const submitBtn = screen.getByRole('button', { name: /Verify & Provision Agent/i });
    fireEvent.click(submitBtn);

    expect(handleCreateAgent).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'daily-digest-bot' }),
      false,
      false,
    );
    expect(await screen.findByText(/Agent 'daily-digest-bot' created & verified successfully/i)).toBeInTheDocument();
  });

  it('switches to Team Squad tab and submits squad with atomic rollback protection', async () => {
    const handleCreateTeam = vi.fn().mockResolvedValue({
      pipeline_id: 'pipe-team-88',
      target_name: 'fullstack-engineering-squad',
      is_team: true,
      current_stage: 'completed',
      created_agents: ['squad-architect', 'frontend-coder', 'backend-engineer'],
      started_at: Date.now() - 300,
      completed_at: Date.now(),
      verification: {
        passed: true,
        severity: 'pass',
        findings: [],
        observed_state: { squad_size: '3' },
      },
    });

    render(<BotForgeStudioCard chatId="chat-forge-1" onCreateTeam={handleCreateTeam} />);

    // Switch tab to Team Squad
    const teamTab = screen.getByRole('button', { name: /Team Squad/i });
    fireEvent.click(teamTab);

    expect(screen.getByText(/Transactional Squad Construction Pipeline/i)).toBeInTheDocument();
    expect(screen.getByText(/Squad Lead: Squad Architect/i)).toBeInTheDocument();

    const deployBtn = screen.getByRole('button', { name: /Deploy Squad with Atomic Rollback Guard/i });
    fireEvent.click(deployBtn);

    expect(handleCreateTeam).toHaveBeenCalled();
    expect(await screen.findByText(/Squad 'fullstack-engineering-squad' verified and provisioned/i)).toBeInTheDocument();
  });

  it('displays rollback details and reverted agents when execution state is rolled_back', () => {
    const rolledBackState: PipelineExecutionState = {
      pipeline_id: 'pipe-fail-1',
      target_name: 'faulty-squad',
      is_team: true,
      current_stage: 'rolled_back',
      created_agents: [],
      error: 'Model quantum-llm is not configured or ready.',
      started_at: Date.now() - 500,
      completed_at: Date.now(),
      rollback: {
        target_name: 'faulty-squad',
        reason: 'Model quantum-llm is not configured or ready.',
        reverted_agents: ['faulty-lead', 'doc-analyst'],
        reverted_crons: ['cron-faulty-1'],
        timestamp: Date.now(),
      },
    };

    render(
      <BotForgeStudioCard
        chatId="chat-forge-1"
        initialExecutionState={rolledBackState}
      />,
    );

    // Switch to Pipeline tab
    const pipelineTab = screen.getByRole('button', { name: /Pipeline/i });
    fireEvent.click(pipelineTab);

    expect(screen.getByText(/Atomic Transactional Rollback Triggered/i)).toBeInTheDocument();
    expect(screen.getByText(/Reason: Model quantum-llm is not configured or ready./i)).toBeInTheDocument();
    expect(screen.getByText(/Reverted Agents: faulty-lead, doc-analyst/i)).toBeInTheDocument();
  });
});
