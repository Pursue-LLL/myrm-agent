/** @vitest-environment jsdom */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import MemoryScopeHierarchyCard from '../cards/MemoryScopeHierarchyCard';
import MemoryScopePicker from '../cards/MemoryScopePicker';
import { MemoryDoctorPanel } from '../command-center/MemoryCommandCenterDoctorPanel';
import type { MemoryCommandCenterResponse } from '@/services/memory/commandCenter';

const mockTranslations: Record<string, string> = {
  'scopeHierarchy.cardTitle': 'Memory Scope Hierarchy',
  'scopeHierarchy.cardSubtitle': 'Visual boundary & lifecycle management for agent long-term knowledge',
  'scopeHierarchy.fourTiersBadge': '4-Tier Unified Scopes',
  'scopeHierarchy.selected': 'Selected',
  'scopeHierarchy.task.title': 'Task Scope',
  'scopeHierarchy.task.tag': 'TASK',
  'scopeHierarchy.task.lifecycle': 'Single Task Execution',
  'scopeHierarchy.task.desc': 'Ephemeral working state and intermediate deductions',
  'scopeHierarchy.conversation.title': 'Conversation Scope',
  'scopeHierarchy.conversation.tag': 'CONVERSATION',
  'scopeHierarchy.conversation.lifecycle': 'Current Chat Session',
  'scopeHierarchy.conversation.desc': 'Dialogue working set and session goals',
  'scopeHierarchy.agent.title': 'Agent Scope',
  'scopeHierarchy.agent.tag': 'AGENT',
  'scopeHierarchy.agent.lifecycle': 'Dedicated Agent Persona',
  'scopeHierarchy.agent.desc': 'Specialized skills and instructions',
  'scopeHierarchy.global.title': 'Global Scope',
  'scopeHierarchy.global.tag': 'GLOBAL',
  'scopeHierarchy.global.lifecycle': 'Universal & Permanent',
  'scopeHierarchy.global.desc': 'User identity and core habits',
  'scopePicker.label': 'Memory Scope Level',
  'scopePicker.taskLabel': 'Task',
  'scopePicker.conversationLabel': 'Chat',
  'scopePicker.agentLabel': 'Agent',
  'scopePicker.globalLabel': 'Global',
  'scopePicker.taskHint': 'Current task execution only',
  'scopePicker.conversationHint': 'Current conversation session only',
  'scopePicker.agentHint': 'Persists across all chats with this Agent',
  'scopePicker.globalHint': 'Universal memory across all agents and sessions',
  'commandCenter.doctorCheck.memory_mislayer_governance.label': 'Memory Scope Mislayer Guard',
  'commandCenter.doctorCheck.memory_mislayer_governance.evidence': 'Scans for universal coding styles or global habits wrongly trapped in ephemeral session scopes.',
  'commandCenter.doctorRepairAction.elevate_mislayered_memories': 'Elevate mislayered memories',
  'commandCenter.doctorRepairPlan.elevate_mislayered_memories.dryRun': 'Scans ephemeral conversation memories.',
  'commandCenter.doctorRepairPlan.elevate_mislayered_memories.expectedEffect': 'Prevents loss of critical preferences.',
  'commandCenter.doctorRepairRisk.safe': 'Safe',
  'commandCenter.doctorRepairExecute': 'Execute repair',
  'commandCenter.readinessStatus.warning': 'Warning',
};

const stableT = (key: string) => mockTranslations[key] ?? key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('MemoryScopeHierarchyCard', () => {
  it('renders all 4 tiers of scope hierarchy card', () => {
    render(<MemoryScopeHierarchyCard />);
    expect(screen.getByText('Memory Scope Hierarchy')).toBeInTheDocument();
    expect(screen.getByText('4-Tier Unified Scopes')).toBeInTheDocument();
    expect(screen.getByText('Task Scope')).toBeInTheDocument();
    expect(screen.getByText('Conversation Scope')).toBeInTheDocument();
    expect(screen.getByText('Agent Scope')).toBeInTheDocument();
    expect(screen.getByText('Global Scope')).toBeInTheDocument();
  });

  it('handles click events when onSelectLevel is provided', () => {
    const onSelect = vi.fn();
    render(<MemoryScopeHierarchyCard activeLevel="agent" onSelectLevel={onSelect} />);
    expect(screen.getByText('Selected')).toBeInTheDocument();

    const taskBtn = screen.getByText('Task Scope').closest('button');
    expect(taskBtn).toBeInTheDocument();
    if (taskBtn) {
      fireEvent.click(taskBtn);
      expect(onSelect).toHaveBeenCalledWith('task');
    }
  });
});

describe('MemoryScopePicker', () => {
  it('renders 4 scope selection buttons and responds to click', () => {
    const onChange = vi.fn();
    render(<MemoryScopePicker value="conversation" onChange={onChange} />);
    expect(screen.getByText('Memory Scope Level')).toBeInTheDocument();
    expect(screen.getByText('Current conversation session only')).toBeInTheDocument();

    const globalBtn = screen.getByText('Global').closest('button');
    expect(globalBtn).toBeInTheDocument();
    if (globalBtn) {
      fireEvent.click(globalBtn);
      expect(onChange).toHaveBeenCalledWith('global');
    }
  });
});

describe('MemoryDoctorPanel Mislayer Guard', () => {
  it('renders mislayer governance check item and triggers repair', () => {
    const onAction = vi.fn();
    const snapshot = {
      doctor_checks: [
        {
          id: 'memory_mislayer_governance',
          category: 'governance',
          label: 'Memory Scope Mislayer Guard',
          status: 'warning',
          evidence: 'Scans for universal coding styles or global habits wrongly trapped in ephemeral session scopes.',
          impact: 'Critical habits might be lost across chat sessions.',
          next_action: 'Elevate mislayered memories to Agent or Global scope.',
          can_auto_fix: true,
          safe_to_retry: true,
          repair_actions: ['elevate_mislayered_memories'],
          repair_plans: [
            {
              id: 'elevate_mislayered_memories',
              label: 'Elevate mislayered memories',
              risk_level: 'safe',
              dry_run_result: 'Scans ephemeral conversation memories.',
              expected_effect: 'Prevents loss of critical preferences.',
              requires_confirmation: false,
              executable: true,
            },
          ],
        },
      ],
    } as unknown as MemoryCommandCenterResponse;

    render(
      <MemoryDoctorPanel
        snapshot={snapshot}
        t={stableT as unknown as ReturnType<typeof import('next-intl').useTranslations<'memory'>>}
        actionId={null}
        diagnosticRun={null}
        diagnosticHistory={[]}
        onDoctorAction={onAction}
      />,
    );

    expect(screen.getByText('Memory Scope Mislayer Guard')).toBeInTheDocument();
    expect(screen.getByText('Elevate mislayered memories')).toBeInTheDocument();

    const repairBtn = screen.getByText('Execute repair');
    fireEvent.click(repairBtn);
    expect(onAction).toHaveBeenCalledWith('elevate_mislayered_memories');
  });
});
