import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AgentTemplateCard } from '../AgentTemplateCard';
import { useTemplateMarketplaceStore } from '../useTemplateMarketplaceStore';
import type { AgentTemplateItem } from '../templateTypes';

describe('AgentTemplateCard', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useTemplateMarketplaceStore.setState({
      activeTemplateForClone: null,
      isCloneWorkbenchOpen: false,
    });
  });

  const mockIndividualTemplate: AgentTemplateItem = {
    id: 'frontend_development_expert',
    name: '前端开发专家',
    description: '精通 React 与现代化 Web 前端架构',
    agent_type: 'individual',
    category: 'engineering',
    is_pareto_preset: true,
    cost_reduction_ratio: 0.35,
    use_cases: ['Web 交互开发', '页面重构'],
    settings_preview: {
      enabled_builtin_tools: ['read_file', 'write_file'],
      skill_ids: ['react-best-practices'],
      prebuilt_skill_ids: [],
      mcp_ids: [],
      memory_preset: 'dual_layer',
      deploy_mode: 'sandbox',
      prompt_mode: 'full',
      personality_style: 'professional',
    },
  };

  const mockTeamTemplate: AgentTemplateItem = {
    id: 'content_creation_squad',
    name: '内容创作小队',
    description: '写手+编辑+配图师协作',
    agent_type: 'team',
    category: 'team',
    use_cases: ['文章创作', '文案批量生产'],
    members: [
      { role: 'writer', name: '创意写手' },
      { role: 'editor', name: '资深编辑' },
    ],
  };

  it('renders individual template with badges, tools, skills, and use cases', () => {
    render(<AgentTemplateCard template={mockIndividualTemplate} />);

    expect(screen.getByText('前端开发专家')).toBeInTheDocument();
    expect(screen.getByText('精通 React 与现代化 Web 前端架构')).toBeInTheDocument();
    expect(screen.getByText('Web 交互开发')).toBeInTheDocument();
    expect(screen.getByText('-35%')).toBeInTheDocument();
    expect(screen.getByText('Pareto')).toBeInTheDocument();
  });

  it('renders team template with team badge and member count info', () => {
    render(<AgentTemplateCard template={mockTeamTemplate} />);

    expect(screen.getByText('内容创作小队')).toBeInTheDocument();
    expect(screen.getByText('2 members')).toBeInTheDocument();
  });

  it('triggers openCloneWorkbench when clone button is clicked', () => {
    render(<AgentTemplateCard template={mockIndividualTemplate} />);

    const cloneBtn = screen.getByTestId('clone-btn-frontend_development_expert');
    fireEvent.click(cloneBtn);

    const state = useTemplateMarketplaceStore.getState();
    expect(state.isCloneWorkbenchOpen).toBe(true);
    expect(state.activeTemplateForClone?.id).toBe('frontend_development_expert');
  });
});
