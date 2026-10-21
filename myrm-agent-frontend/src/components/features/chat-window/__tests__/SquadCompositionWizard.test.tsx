import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  SquadCompositionWizard,
  SquadBlueprintData,
  MaterializedSquadData,
} from '../SquadCompositionWizard';

describe('SquadCompositionWizard', () => {
  const sampleBlueprint: SquadBlueprintData = {
    squad_id: 'squad_test_101',
    goal_description: 'Refactor router and add integration tests',
    total_budget_tokens: 150000,
    total_max_cost_usd: 2.0,
    max_descendants_per_run: 8,
    members: [
      {
        role_key: 'orchestrator',
        display_name: 'Squad Conductor',
        handle: '@conductor',
        role_tier: 'orchestrator',
        role_description: 'Decomposes goal and verifies delivery',
        soul_system_prompt: '# SOUL Profile: Squad Conductor\nLead task decomposition.',
        budget_tokens: 60000,
        max_cost_usd: 0.8,
        stop_condition: { max_turns: 15, max_tool_calls: 40 },
        suggested_model_tier: 'reasoning',
      },
      {
        role_key: 'coder',
        display_name: 'Core Engineer',
        handle: '@engineer',
        role_tier: 'coder',
        role_description: 'Implements code and fixes',
        soul_system_prompt: '# SOUL Profile: Core Engineer\nImplement concrete features.',
        budget_tokens: 60000,
        max_cost_usd: 0.8,
        stop_condition: { max_turns: 12, max_tool_calls: 30 },
        suggested_model_tier: 'balanced',
      },
      {
        role_key: 'reviewer',
        display_name: 'Quality Guardian',
        handle: '@guardian',
        role_tier: 'reviewer',
        role_description: 'Audits correctness and coverage',
        soul_system_prompt: '# SOUL Profile: Quality Guardian\nAudit code and safety.',
        budget_tokens: 30000,
        max_cost_usd: 0.4,
        stop_condition: { max_turns: 8, max_tool_calls: 20 },
        suggested_model_tier: 'fast',
      },
    ],
  };

  const sampleMaterialized: MaterializedSquadData = {
    squad_id: 'squad_mat_202',
    orchestrator_bot_id: 'bot_orch_999',
    total_budget_tokens: 150000,
    total_max_cost_usd: 2.0,
    status: 'active',
    members: [
      {
        role_key: 'orchestrator',
        bot_id: 'bot_orch_999',
        handle: '@conductor',
        display_name: 'Squad Conductor',
        role_tier: 'orchestrator',
        selected_model_id: 'gpt-4o',
        allocated_budget_tokens: 60000,
        allocated_max_cost_usd: 0.8,
      },
      {
        role_key: 'coder',
        bot_id: 'bot_coder_888',
        handle: '@engineer',
        display_name: 'Core Engineer',
        role_tier: 'coder',
        selected_model_id: 'claude-3-5-sonnet',
        allocated_budget_tokens: 60000,
        allocated_max_cost_usd: 0.8,
      },
    ],
  };

  it('renders goal input form and triggers onComposeBlueprint callback', () => {
    const handleCompose = vi.fn();
    render(<SquadCompositionWizard onComposeBlueprint={handleCompose} />);

    expect(screen.getByText('智能战队自动组队向导')).toBeInTheDocument();
    expect(screen.getByText('Model-Deferred 两阶段')).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText(/重构多智能体信箱路由/);
    fireEvent.change(textarea, {
      target: { value: 'Build high-performance search service' },
    });

    const submitBtn = screen.getByRole('button', { name: /自动推导蓝图/ });
    fireEvent.click(submitBtn);

    expect(handleCompose).toHaveBeenCalledWith('Build high-performance search service');
  });

  it('renders blueprint review phase with members, budget badges, and roles', () => {
    render(<SquadCompositionWizard blueprint={sampleBlueprint} />);

    expect(screen.getByText(/Refactor router and add integration tests/)).toBeInTheDocument();
    expect(screen.getByText('150,000 Tokens')).toBeInTheDocument();
    expect(screen.getByText('$2.00 USD')).toBeInTheDocument();
    expect(screen.getByText('Max 8 衍生')).toBeInTheDocument();
    expect(screen.getByText('3 位战队成员')).toBeInTheDocument();

    expect(screen.getByText('Squad Conductor')).toBeInTheDocument();
    expect(screen.getByText('Core Engineer')).toBeInTheDocument();
    expect(screen.getByText('Quality Guardian')).toBeInTheDocument();
    expect(screen.getByText('总控编排')).toBeInTheDocument();
    expect(screen.getByText('核心研发')).toBeInTheDocument();
    expect(screen.getByText('质量卫士')).toBeInTheDocument();
  });

  it('expands and collapses SOUL system prompt upon click', () => {
    render(<SquadCompositionWizard blueprint={sampleBlueprint} />);

    const soulButtons = screen.getAllByText('查看 SOUL Prompt');
    expect(soulButtons.length).toBe(3);

    fireEvent.click(soulButtons[0]);
    expect(screen.getByText(/Lead task decomposition/)).toBeInTheDocument();

    const collapseButton = screen.getByText('收起 SOUL Prompt');
    fireEvent.click(collapseButton);
    expect(screen.queryByText(/Lead task decomposition/)).not.toBeInTheDocument();
  });

  it('handles model selection and triggers onMaterializeSquad callback', () => {
    const handleMaterialize = vi.fn();
    render(
      <SquadCompositionWizard
        blueprint={sampleBlueprint}
        onMaterializeSquad={handleMaterialize}
      />,
    );

    const coderSelect = screen.getByDisplayValue('Claude 3.5 Sonnet (架构与代码)');
    fireEvent.change(coderSelect, { target: { value: 'gpt-4o' } });

    const materializeBtn = screen.getByRole('button', { name: /物化战队并启动/ });
    fireEvent.click(materializeBtn);

    expect(handleMaterialize).toHaveBeenCalledWith(
      'squad_test_101',
      expect.arrayContaining([
        expect.objectContaining({
          role_key: 'coder',
          selected_model_id: 'gpt-4o',
        }),
      ]),
    );
  });

  it('renders materialized squad view with success banner', () => {
    render(
      <SquadCompositionWizard
        blueprint={sampleBlueprint}
        materializedSquad={sampleMaterialized}
      />,
    );

    expect(screen.getByText('战队物化成功！已就绪自治执行')).toBeInTheDocument();
    expect(screen.getByText('squad_mat_202')).toBeInTheDocument();
    expect(screen.getByText('bot_orch_999')).toBeInTheDocument();
  });

  it('triggers onClose when close button is clicked', () => {
    const handleClose = vi.fn();
    render(<SquadCompositionWizard onClose={handleClose} />);

    const closeBtn = screen.getByLabelText('Close Wizard');
    fireEvent.click(closeBtn);

    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
