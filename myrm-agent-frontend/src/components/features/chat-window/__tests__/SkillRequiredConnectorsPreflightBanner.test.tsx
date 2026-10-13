// @vitest-environment jsdom
// @bun-test-dom
'use client';

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

const stableT = (key: string) => {
  const messages: Record<string, string> = {
    missingNotice: 'Active skills require unconfigured connectors',
    connectAction: 'Connect Now',
    narrowScopeAction: 'Narrow Scope',
  };
  return messages[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

import useChatStore from '@/store/useChatStore';
import { useSkillStore } from '@/store/skill';
import type { Skill } from '@/store/skill/types';
import useConfigStore from '@/store/useConfigStore';
import { SkillRequiredConnectorsPreflightBanner } from '../context-strip/SkillRequiredConnectorsPreflightBanner';

describe('SkillRequiredConnectorsPreflightBanner', () => {
  beforeEach(() => {
    push.mockClear();
    useChatStore.setState({
      agentConfig: {
        agentId: 'default',
        agentName: 'Default Agent',
        agentDescription: 'Test',
        systemPrompt: '',
        useGlobalInstruction: true,
        autoRestoreDomains: [],
        selectedSkillIds: ['google-workspace'],
        selectedMcpNames: [],
      },
    });

    useSkillStore.setState({
      marketSkills: [
        {
          id: 'google-workspace',
          name: 'Google Workspace',
          description: 'Google Suite',
          storage_path: '',
          version: '1.0.0',
          category: 'office',
          icon_url: null,
          tags: [],
          requires: { bins: [], env: [], config: [] },
          available: false, // unavailable triggers preflight warning
          unavailable_reason: 'Missing OAuth',
          required_oauth_issuers: ['google_workspace'],
          trust: 'trusted',
          author: null,
          homepage: null,
          always: false,
          model_invocable: true,
          user_invocable: true,
          primary_env: null,
          user_trusted: true,
          evolution_locked: false,
          security: null,
          has_upstream_update: false,
          type: 'prebuilt',
          verification_steps: [],
          eval_cases: [],
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
      localSkills: [],
    });

    useConfigStore.setState({
      mcpConfigs: [],
    });
  });

  it('renders preflight banner when an active skill has unsatisfied OAuth requirements', () => {
    render(<SkillRequiredConnectorsPreflightBanner />);
    expect(screen.getByTestId('skill-connectors-preflight-banner')).toBeDefined();
    expect(screen.getByText(/Active skills require unconfigured connectors/)).toBeDefined();
    expect(screen.getByText(/Google Workspace \(google_workspace\)/)).toBeDefined();
  });

  it('hides banner when all active skills are available or satisfy dependencies', () => {
    useSkillStore.setState({
      marketSkills: [
        {
          id: 'google-workspace',
          name: 'Google Workspace',
          description: 'Google Suite',
          storage_path: '',
          version: '1.0.0',
          category: 'office',
          icon_url: null,
          tags: [],
          requires: { bins: [], env: [], config: [] },
          available: true, // available -> no missing OAuth
          unavailable_reason: null,
          required_oauth_issuers: ['google_workspace'],
          trust: 'trusted',
          author: null,
          homepage: null,
          always: false,
          model_invocable: true,
          user_invocable: true,
          primary_env: null,
          user_trusted: true,
          evolution_locked: false,
          security: null,
          has_upstream_update: false,
          type: 'prebuilt',
          verification_steps: [],
          eval_cases: [],
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
      localSkills: [],
    });

    const { container } = render(<SkillRequiredConnectorsPreflightBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('triggers onOpenCapabilityEditor when narrow scope action is clicked', () => {
    const handleOpen = vi.fn();
    render(<SkillRequiredConnectorsPreflightBanner onOpenCapabilityEditor={handleOpen} />);

    const narrowBtn = screen.getByText('Narrow Scope');
    fireEvent.click(narrowBtn);
    expect(handleOpen).toHaveBeenCalledTimes(1);
  });

  describe('connect action target', () => {
    function requireSkill(overrides: Partial<Skill>) {
      const [skill] = useSkillStore.getState().marketSkills;
      useSkillStore.setState({ marketSkills: [{ ...skill, ...overrides }] });
    }

    it('opens Credentials for an account issuer', () => {
      requireSkill({ required_oauth_issuers: ['google_workspace'] });
      render(<SkillRequiredConnectorsPreflightBanner />);

      fireEvent.click(screen.getByText('Connect Now'));

      expect(push).toHaveBeenCalledWith('/settings/credentials');
    });

    it('opens the Models page for an LLM-provider issuer', () => {
      requireSkill({ required_oauth_issuers: ['provider_openai'] });
      render(<SkillRequiredConnectorsPreflightBanner />);

      fireEvent.click(screen.getByText('Connect Now'));

      expect(push).toHaveBeenCalledWith('/settings/models');
    });

    it('opens the first missing issuer owner when several accounts are missing', () => {
      requireSkill({ required_oauth_issuers: ['provider_anthropic', 'google_workspace'] });
      render(<SkillRequiredConnectorsPreflightBanner />);

      fireEvent.click(screen.getByText('Connect Now'));

      expect(push).toHaveBeenCalledWith('/settings/models');
    });

    it('opens Skills when only MCP connectors are missing', () => {
      requireSkill({ required_oauth_issuers: [], required_mcp_server_ids: ['notion'] });
      render(<SkillRequiredConnectorsPreflightBanner />);

      fireEvent.click(screen.getByText('Connect Now'));

      expect(push).toHaveBeenCalledWith('/settings/skills');
    });
  });
});
