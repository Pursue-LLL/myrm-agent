import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  SkillBundleWarmupModal,
  SkillBundleData,
} from '../SkillBundleWarmupModal';

describe('SkillBundleWarmupModal', () => {
  const customBundles: SkillBundleData[] = [
    {
      bundle_id: 'bundle_sec_audit',
      name: 'Security Audit & Compliance Suite',
      description: 'Automated vulnerability scanning and secret leakage detection.',
      category: 'security',
      skills: [
        {
          skill_id: 'secret-scanner',
          name: 'Secret Scanner',
          description: 'Detects committed API keys and passwords.',
          required_env_vars: [],
          required_tools: [],
          is_optional: false,
        },
        {
          skill_id: 'cve-lookup',
          name: 'CVE Vulnerability Lookup',
          description: 'Queries NIST database for known package exploits.',
          required_env_vars: ['NIST_API_KEY'],
          required_tools: [],
          is_optional: false,
        },
      ],
      author: 'sec-ops',
      version: '2.0.0',
      tags: ['security', 'compliance'],
    },
    {
      bundle_id: 'bundle_frontend_fast',
      name: 'Frontend Rapid Prototyping',
      description: 'Tailwind and React component generator.',
      category: 'coding',
      skills: [
        {
          skill_id: 'react-scaffolder',
          name: 'React Scaffolder',
          description: 'Generates boilerplates.',
          required_env_vars: [],
          required_tools: [],
          is_optional: false,
        },
      ],
      author: 'ui-team',
      version: '1.0.0',
      tags: ['react', 'tailwind'],
    },
  ];

  it('renders modal header, bundle cards, and default categories cleanly', () => {
    const handleDismiss = vi.fn();
    render(
      <SkillBundleWarmupModal
        chatId="chat-modal-1"
        bundles={customBundles}
        onDismiss={handleDismiss}
      />
    );

    expect(
      screen.getByText('Scenario Skill Bundles & Warmup Manager')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Security Audit & Compliance Suite')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Frontend Rapid Prototyping')
    ).toBeInTheDocument();
    expect(screen.getByText('2 available')).toBeInTheDocument();
  });

  it('filters bundles when category chip clicked', () => {
    render(
      <SkillBundleWarmupModal
        chatId="chat-modal-filter"
        bundles={customBundles}
        onDismiss={vi.fn()}
      />
    );

    expect(
      screen.getByText('Security Audit & Compliance Suite')
    ).toBeInTheDocument();
    expect(
      screen.getByText('Frontend Rapid Prototyping')
    ).toBeInTheDocument();

    // Click 'coding' filter chip
    const codingChip = screen.getByRole('button', { name: /^coding$/i });
    fireEvent.click(codingChip);

    expect(
      screen.getByText('Frontend Rapid Prototyping')
    ).toBeInTheDocument();
    expect(
      screen.queryByText('Security Audit & Compliance Suite')
    ).not.toBeInTheDocument();
  });

  it('expands skills list when chevron button clicked', () => {
    render(
      <SkillBundleWarmupModal
        chatId="chat-modal-expand"
        bundles={customBundles}
        onDismiss={vi.fn()}
      />
    );

    expect(screen.queryByText('secret-scanner')).not.toBeInTheDocument();

    const expandButtons = screen.getAllByRole('button', { name: /Expand/i });
    fireEvent.click(expandButtons[0]);

    expect(screen.getByText('secret-scanner')).toBeInTheDocument();
    expect(screen.getByText(/env: NIST_API_KEY/)).toBeInTheDocument();
  });

  it('triggers onActivateBundle with force parameter when activate button clicked', async () => {
    const handleActivate = vi.fn().mockResolvedValue(undefined);
    render(
      <SkillBundleWarmupModal
        chatId="chat-modal-activate"
        bundles={customBundles}
        onActivateBundle={handleActivate}
        onDismiss={vi.fn()}
      />
    );

    // Toggle force checkbox on the first bundle which requires env var
    const forceCheckbox = screen.getByRole('checkbox');
    fireEvent.click(forceCheckbox);

    const activateBtns = screen.getAllByRole('button', {
      name: /1-Click Activate/i,
    });
    await act(async () => {
      fireEvent.click(activateBtns[0]);
    });

    expect(handleActivate).toHaveBeenCalledWith('bundle_sec_audit', true);
  });

  it('triggers onDeactivateBundle when active bundle deactivate clicked', async () => {
    const handleDeactivate = vi.fn().mockResolvedValue(undefined);
    render(
      <SkillBundleWarmupModal
        chatId="chat-modal-deact"
        bundles={customBundles}
        activeBundleIds={['bundle_sec_audit']}
        onDeactivateBundle={handleDeactivate}
        onDismiss={vi.fn()}
      />
    );

    const deactivateBtn = screen.getByRole('button', {
      name: /Deactivate/i,
    });
    await act(async () => {
      fireEvent.click(deactivateBtn);
    });

    expect(handleDeactivate).toHaveBeenCalledWith('bundle_sec_audit');
  });

  it('triggers onDismiss when close button clicked', () => {
    const handleDismiss = vi.fn();
    render(
      <SkillBundleWarmupModal
        chatId="chat-modal-close"
        bundles={customBundles}
        onDismiss={handleDismiss}
      />
    );

    const closeBtn = screen.getByRole('button', { name: /Close$/i });
    fireEvent.click(closeBtn);

    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });
});
