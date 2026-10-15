import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import CuratorSettingsPanel from '../CuratorSettingsPanel';
import * as skillService from '@/services/skill';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: vi.fn(),
}));

describe('CuratorSettingsPanel Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders skill curator settings and health doctor diagnostics findings', async () => {
    vi.spyOn(skillService, 'getCuratorConfig').mockResolvedValue({
      enabled: true,
      interval_hours: 168,
      stale_after_days: 30,
      archive_after_days: 90,
      grace_period_days: 7,
      min_success_rate: 0.3,
      max_skills: 50,
      protect_installed_skills: true,
      consolidation_enabled: false,
      consolidation_min_cluster_size: 3,
      consolidation_similarity_threshold: 0.75,
    });

    vi.spyOn(skillService, 'getSkillDiagnostics').mockResolvedValue({
      total_skills: 5,
      active_skills: 4,
      stale_skills: 1,
      archived_skills: 0,
      pinned_skills: 1,
      findings: [
        {
          skill_name: 'toxic_crawler',
          finding_type: 'wrong_but_frequent',
          severity: 'critical',
          message: 'Skill invoked 30 times with 10% success rate',
          call_count: 30,
          success_rate: 0.1,
          pinned: true,
          recommended_action: 'unpin_and_archive',
          details: {},
        },
      ],
      health_score: 75.0,
    });

    render(<CuratorSettingsPanel />);

    await waitFor(() => {
      expect(screen.getByText('toxic_crawler')).toBeInTheDocument();
    });

    expect(screen.getByText('PINNED')).toBeInTheDocument();
    expect(screen.getByText('Score: 75/100')).toBeInTheDocument();
  });
});

describe('CuratorSettingsPanel save footer', () => {
  const baseConfig: skillService.CuratorConfigResponse = {
    enabled: true,
    interval_hours: 168,
    stale_after_days: 30,
    archive_after_days: 90,
    grace_period_days: 7,
    min_success_rate: 0.3,
    max_skills: 50,
    protect_installed_skills: true,
    consolidation_enabled: false,
    consolidation_min_cluster_size: 3,
    consolidation_similarity_threshold: 0.75,
  };

  function mockPanelServices(config: skillService.CuratorConfigResponse = baseConfig) {
    vi.spyOn(skillService, 'getCuratorConfig').mockResolvedValue(config);
    vi.spyOn(skillService, 'getSkillDiagnostics').mockResolvedValue({
      total_skills: 0,
      active_skills: 0,
      stale_skills: 0,
      archived_skills: 0,
      pinned_skills: 0,
      findings: [],
      health_score: 100,
    });
    return vi
      .spyOn(skillService, 'updateCuratorConfig')
      .mockImplementation(async (updates) => ({ ...config, ...updates }));
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('offers Save only once something has changed', async () => {
    mockPanelServices();
    const user = userEvent.setup();
    render(<CuratorSettingsPanel />);
    await screen.findByDisplayValue('30');

    expect(screen.queryByRole('button', { name: 'save' })).not.toBeInTheDocument();

    await user.click(screen.getAllByRole('switch')[0]);

    expect(screen.getByRole('button', { name: 'save' })).toBeInTheDocument();
  });

  it('saves the disabled state even though the threshold fields are hidden', async () => {
    const update = mockPanelServices();
    const user = userEvent.setup();
    render(<CuratorSettingsPanel />);
    await screen.findByDisplayValue('30');

    await user.click(screen.getAllByRole('switch')[0]);
    expect(screen.queryByDisplayValue('30')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'save' }));

    expect(update).toHaveBeenCalledWith(expect.objectContaining({ enabled: false }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'save' })).not.toBeInTheDocument());
  });

  it('clamps an out-of-range threshold before it is sent', async () => {
    const update = mockPanelServices();
    const user = userEvent.setup();
    render(<CuratorSettingsPanel />);
    const staleField = await screen.findByDisplayValue('30');

    await user.clear(staleField);
    await user.type(staleField, '0');
    await user.tab();
    expect(staleField).toHaveValue(1);

    await user.click(screen.getByRole('button', { name: 'save' }));

    expect(update).toHaveBeenCalledWith(expect.objectContaining({ stale_after_days: 1 }));
  });

  it('keeps a single Save button while the consolidation settings are open', async () => {
    mockPanelServices({ ...baseConfig, consolidation_enabled: true });
    const user = userEvent.setup();
    render(<CuratorSettingsPanel />);
    await screen.findByDisplayValue('30');

    await user.click(screen.getAllByRole('switch')[1]);

    expect(screen.getAllByRole('button', { name: 'save' })).toHaveLength(1);
  });
});
