import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  WorkspaceTeamBlueprintBar,
  WorkspaceBlueprintBindingData,
  WorkspaceBlueprintResolutionData,
} from '../WorkspaceTeamBlueprintBar';

describe('WorkspaceTeamBlueprintBar', () => {
  const sampleBinding: WorkspaceBlueprintBindingData = {
    workspace_id: 'ws_core_api',
    blueprint_id: 'bp_trio_dev',
    team_name: 'Fullstack Core Trio',
    auto_reuse_policy: 'prompt_reuse',
    member_count: 3,
    total_budget_tokens: 150000,
    project_label: 'Core REST Microservices',
  };

  const sampleResolution: WorkspaceBlueprintResolutionData = {
    workspace_id: 'ws_core_api',
    binding: sampleBinding,
    can_auto_instantiate: false,
    status_label: 'prompt_candidate',
    resolution_rationale: "Workspace 'ws_core_api' has bound team 'Fullstack Core Trio'. Prompt user to confirm reuse.",
  };

  it('renders bound team details with policy badge and rationale', () => {
    render(
      <WorkspaceTeamBlueprintBar
        workspaceId="ws_core_api"
        resolution={sampleResolution}
      />,
    );

    expect(screen.getByText(/Project Team Blueprint/i)).toBeInTheDocument();
    expect(screen.getByText('ws_core_api')).toBeInTheDocument();
    expect(screen.getByText(/Core REST Microservices/i)).toBeInTheDocument();
    expect(screen.getByText('Fullstack Core Trio')).toBeInTheDocument();
    expect(screen.getByText(/3 Members • 150,000 Tokens Budget/i)).toBeInTheDocument();
    expect(screen.getByText(/Auto Reuse: Confirm/i)).toBeInTheDocument();
  });

  it('triggers onInstantiateTeam callback when Reuse Team button is clicked', () => {
    const handleInstantiate = vi.fn();

    render(
      <WorkspaceTeamBlueprintBar
        workspaceId="ws_core_api"
        resolution={sampleResolution}
        onInstantiateTeam={handleInstantiate}
      />,
    );

    const reuseBtn = screen.getByRole('button', { name: /Reuse Team/i });
    fireEvent.click(reuseBtn);
    expect(handleInstantiate).toHaveBeenCalledWith(sampleBinding);
    expect(screen.getByText(/Team Reused!/i)).toBeInTheDocument();
  });

  it('allows policy reconfiguration and triggers onSavePolicy', () => {
    const handleSavePolicy = vi.fn();

    render(
      <WorkspaceTeamBlueprintBar
        workspaceId="ws_core_api"
        resolution={sampleResolution}
        onSavePolicy={handleSavePolicy}
      />,
    );

    // Open policy editing dropdown
    const configBtn = screen.getByRole('button', { name: /Configure Policy/i });
    fireEvent.click(configBtn);

    const select = screen.getByLabelText(/Select auto-reuse policy/i);
    fireEvent.change(select, { target: { value: 'always_reuse' } });

    expect(handleSavePolicy).toHaveBeenCalledWith('ws_core_api', 'always_reuse');
  });

  it('triggers onUnbind when unbind button is clicked', () => {
    const handleUnbind = vi.fn();

    render(
      <WorkspaceTeamBlueprintBar
        workspaceId="ws_core_api"
        resolution={sampleResolution}
        onUnbind={handleUnbind}
      />,
    );

    const unbindBtn = screen.getByRole('button', { name: /Unbind/i });
    fireEvent.click(unbindBtn);
    expect(handleUnbind).toHaveBeenCalledWith('ws_core_api');
  });

  it('renders recommendation state and triggers adoption', () => {
    const handleInstantiate = vi.fn();
    const recommendedResolution: WorkspaceBlueprintResolutionData = {
      workspace_id: 'ws_brand_new',
      binding: sampleBinding,
      can_auto_instantiate: false,
      status_label: 'unbound_recommend_recent',
      resolution_rationale: "Recommending recent team 'Fullstack Core Trio' from 'ws_core_api'.",
    };

    render(
      <WorkspaceTeamBlueprintBar
        workspaceId="ws_brand_new"
        resolution={recommendedResolution}
        onInstantiateTeam={handleInstantiate}
      />,
    );

    expect(screen.getByText(/Recommended Team from Previous Workspace/i)).toBeInTheDocument();
    const adoptBtn = screen.getByRole('button', { name: /Adopt & Reuse Team/i });
    fireEvent.click(adoptBtn);
    expect(handleInstantiate).toHaveBeenCalledWith(sampleBinding);
  });

  it('renders empty state when workspace is unbound with no history', () => {
    const emptyResolution: WorkspaceBlueprintResolutionData = {
      workspace_id: 'ws_empty_repo',
      binding: null,
      can_auto_instantiate: false,
      status_label: 'unbound_no_template',
      resolution_rationale: 'No bound blueprint or history.',
    };

    render(
      <WorkspaceTeamBlueprintBar
        workspaceId="ws_empty_repo"
        resolution={emptyResolution}
      />,
    );

    expect(screen.getByText(/No Bound Team Blueprint/i)).toBeInTheDocument();
  });

  it('triggers onDismiss when close button is clicked', () => {
    const handleDismiss = vi.fn();

    render(
      <WorkspaceTeamBlueprintBar
        workspaceId="ws_core_api"
        resolution={sampleResolution}
        onDismiss={handleDismiss}
      />,
    );

    const closeBtn = screen.getByRole('button', { name: /Dismiss Blueprint Bar/i });
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });
});
