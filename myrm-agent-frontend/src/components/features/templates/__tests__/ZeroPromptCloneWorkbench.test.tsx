import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { ZeroPromptCloneWorkbench } from '../ZeroPromptCloneWorkbench';
import { useTemplateMarketplaceStore } from '../useTemplateMarketplaceStore';
import type { AgentTemplateItem } from '../templateTypes';

describe('ZeroPromptCloneWorkbench', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useTemplateMarketplaceStore.setState({
      activeTemplateForClone: null,
      isCloneWorkbenchOpen: false,
      isCloning: false,
      cloneError: null,
    });
  });

  const mockTemplate: AgentTemplateItem = {
    id: 'frontend_development_expert',
    name: '前端开发专家',
    agent_type: 'individual',
    category: 'engineering',
    wiki_blueprint: ['architecture/', 'benchmarks/'],
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

  it('renders nothing when closed or no active template', () => {
    const { container } = render(<ZeroPromptCloneWorkbench />);
    expect(container.firstChild).toBeNull();
  });

  it('renders modal with preset capabilities and wiki blueprint when open', () => {
    useTemplateMarketplaceStore.setState({
      activeTemplateForClone: mockTemplate,
      isCloneWorkbenchOpen: true,
    });

    render(<ZeroPromptCloneWorkbench />);

    expect(screen.getByTestId('zero-prompt-clone-workbench')).toBeInTheDocument();
    expect(screen.getByText(/前端开发专家/)).toBeInTheDocument();
    expect(screen.getByText('architecture/')).toBeInTheDocument();
    expect(screen.getByText('benchmarks/')).toBeInTheDocument();
    expect(screen.getByText('Sandbox Ready')).toBeInTheDocument();
  });

  it('submits instant clone with custom name and triggers onSuccess', async () => {
    const mockOnSuccess = vi.fn();
    const instantiateSpy = vi.fn().mockResolvedValue({ id: 'agent_abc', name: 'My New Coder' });

    useTemplateMarketplaceStore.setState({
      activeTemplateForClone: mockTemplate,
      isCloneWorkbenchOpen: true,
      instantiateTemplate: instantiateSpy,
    });

    render(<ZeroPromptCloneWorkbench onSuccess={mockOnSuccess} />);

    const input = screen.getByPlaceholderText('前端开发专家');
    fireEvent.change(input, { target: { value: 'My New Coder' } });

    const confirmBtn = screen.getByTestId('confirm-clone-btn');
    await act(async () => {
      fireEvent.click(confirmBtn);
    });

    expect(instantiateSpy).toHaveBeenCalledWith({
      templateId: 'frontend_development_expert',
      customName: 'My New Coder',
      initWikiBlueprint: true,
    });
    expect(mockOnSuccess).toHaveBeenCalledWith({ id: 'agent_abc', name: 'My New Coder' });
  });

  it('closes modal when cancel button is clicked', () => {
    useTemplateMarketplaceStore.setState({
      activeTemplateForClone: mockTemplate,
      isCloneWorkbenchOpen: true,
    });

    render(<ZeroPromptCloneWorkbench />);

    const cancelBtn = screen.getAllByRole('button', { name: /cancel/i })[0];
    fireEvent.click(cancelBtn);

    expect(useTemplateMarketplaceStore.getState().isCloneWorkbenchOpen).toBe(false);
  });
});
