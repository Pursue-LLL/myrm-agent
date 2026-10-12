/** @vitest-environment jsdom */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TemplateListItem } from '@/services/agent';
import { AgentSettingsPreviewGate } from '../AgentSettingsPreviewGate';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, values?: { fallback?: string }) => values?.fallback ?? key,
  useLocale: () => 'en',
}));

describe('AgentSettingsPreviewGate', () => {
  const fullTemplate: TemplateListItem = {
    id: 'full-agent',
    name: '全栈架构专家',
    description: '负责系统架构设计与代码实现',
    agent_type: 'individual',
    settings_preview: {
      enabled_builtin_tools: ['bash', 'file_ops', 'web_search'],
      skill_ids: ['system-architect'],
      prebuilt_skill_ids: ['office-document'],
      mcp_ids: ['chrome-devtools-mcp', 'sqlite-mcp'],
      memory_preset: 'dual_layer',
      deploy_mode: 'sandbox',
      sandbox_bound_note: '受控容器沙箱：高危命令被系统级安全拦截',
      prompt_mode: 'full',
      personality_style: 'professional',
    },
  };

  const minimalTemplate: TemplateListItem = {
    id: 'minimal-agent',
    name: '轻量助理',
    agent_type: 'individual',
  };

  const teamTemplate: TemplateListItem = {
    id: 'team-squad',
    name: '研发协作战队',
    agent_type: 'team',
    settings_preview: {
      enabled_builtin_tools: [],
      skill_ids: [],
      prebuilt_skill_ids: [],
      mcp_ids: [],
      memory_preset: 'dual_layer',
      deploy_mode: 'sandbox',
      prompt_mode: 'lean',
      personality_style: 'collaborative',
    },
  };

  it('renders full settings matrix with all 5 dimensions', () => {
    const handleConfirm = vi.fn();
    const handleBack = vi.fn();

    render(
      <AgentSettingsPreviewGate
        template={fullTemplate}
        onConfirm={handleConfirm}
        onBack={handleBack}
      />,
    );

    // Header & identity
    expect(screen.getByText('全栈架构专家')).toBeInTheDocument();
    expect(screen.getByText('Individual')).toBeInTheDocument();

    // 1. Built-in tools
    expect(screen.getByTestId('preview-matrix-builtin-tools')).toBeInTheDocument();
    expect(screen.getByText('bash')).toBeInTheDocument();
    expect(screen.getByText('file_ops')).toBeInTheDocument();
    expect(screen.getByText('web_search')).toBeInTheDocument();

    // 2. Skills
    expect(screen.getByTestId('preview-matrix-skills')).toBeInTheDocument();
    expect(screen.getByText('system-architect')).toBeInTheDocument();
    expect(screen.getByText('office-document')).toBeInTheDocument();

    // 3. MCP Connectors
    expect(screen.getByTestId('preview-matrix-mcp')).toBeInTheDocument();
    expect(screen.getByText('chrome-devtools-mcp')).toBeInTheDocument();
    expect(screen.getByText('sqlite-mcp')).toBeInTheDocument();

    // 4. Memory Architecture
    expect(screen.getByTestId('preview-matrix-memory')).toBeInTheDocument();
    expect(screen.getByText('dual_layer')).toBeInTheDocument();

    // 5. Deploy Mode & Sandbox Bounds
    expect(screen.getByTestId('preview-matrix-sandbox')).toBeInTheDocument();
    expect(screen.getByText('受控容器沙箱：高危命令被系统级安全拦截')).toBeInTheDocument();

    // Meta Specs Pill Bar
    expect(screen.getByText('Pre-flight verified')).toBeInTheDocument();
    expect(screen.getByText('full')).toBeInTheDocument();
    expect(screen.getByText('professional')).toBeInTheDocument();
  });

  it('renders fallback copy for minimal templates without settings_preview', () => {
    render(
      <AgentSettingsPreviewGate
        template={minimalTemplate}
        onConfirm={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    expect(screen.getByText('Standard workspace primitives inherited')).toBeInTheDocument();
    expect(screen.getByText('No extra skills pre-mounted')).toBeInTheDocument();
    expect(screen.getByText('Zero external MCP protocol bindings')).toBeInTheDocument();
  });

  it('renders team badge when template agent_type is team', () => {
    render(
      <AgentSettingsPreviewGate
        template={teamTemplate}
        onConfirm={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    expect(screen.getByText('Team')).toBeInTheDocument();
  });

  it('triggers onBack when back button is clicked', () => {
    const handleBack = vi.fn();
    render(
      <AgentSettingsPreviewGate
        template={fullTemplate}
        onConfirm={vi.fn()}
        onBack={handleBack}
      />,
    );

    const backBtn = screen.getByRole('button', { name: /Back/i });
    fireEvent.click(backBtn);
    expect(handleBack).toHaveBeenCalledTimes(1);
  });

  it('triggers onConfirm when confirm button is clicked', () => {
    const handleConfirm = vi.fn();
    render(
      <AgentSettingsPreviewGate
        template={fullTemplate}
        onConfirm={handleConfirm}
        onBack={vi.fn()}
      />,
    );

    const confirmBtn = screen.getByTestId('confirm-instantiate-agent-btn');
    fireEvent.click(confirmBtn);
    expect(handleConfirm).toHaveBeenCalledTimes(1);
  });

  it('disables buttons when isCreating is true', () => {
    render(
      <AgentSettingsPreviewGate
        template={fullTemplate}
        onConfirm={vi.fn()}
        onBack={vi.fn()}
        isCreating
      />,
    );

    expect(screen.getByRole('button', { name: /Back/i })).toBeDisabled();
    expect(screen.getByTestId('confirm-instantiate-agent-btn')).toBeDisabled();
    expect(screen.getByText('Creating…')).toBeInTheDocument();
  });
});
