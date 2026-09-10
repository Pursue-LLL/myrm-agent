// @vitest-environment jsdom
// @bun-test-dom
'use client';

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => {
    const messages: Record<string, string> = {
      missingNotice: 'Active skills require unconfigured connectors',
      connectAction: 'Connect Now',
      narrowScopeAction: 'Narrow Scope',
    };
    return messages[key] ?? key;
  },
}));

import useChatStore from '@/store/useChatStore';
import { useSkillStore } from '@/store/skill';
import useConfigStore from '@/store/useConfigStore';
import { SkillRequiredConnectorsPreflightBanner } from '../context-strip/SkillRequiredConnectorsPreflightBanner';

describe('SkillRequiredConnectorsPreflightBanner', () => {
  beforeEach(() => {
    useChatStore.setState({
      agentConfig: {
        agentId: 'default',
        name: 'Default Agent',
        description: 'Test',
        systemPrompt: '',
        selectedSkillIds: ['google-workspace'],
      },
      turnCapabilitySelection: null,
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
          is_active: true,
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
          is_active: true,
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
});
