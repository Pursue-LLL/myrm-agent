import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
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
